#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import or_, and_, xor, add
from functools import reduce

from litedram.phy.sim_utils import SimLogger, log_level_getter

from migen import *
from migen.genlib.fifo import SyncFIFO

from litex.soc.interconnect.csr import *

from litedram.common import *
from litedram.phy.dfi import *

from litedram.phy.utils import (bitpattern, delayed, Serializer, Deserializer, Latency,
    CommandsPipeline)
from litedram.phy.sim_utils import SimpleCDCWrap, SimpleCDCrWrap

from litedram.phy.ddr5.commands import DFIPhaseAdapter

from litedram.phy.ddr5.BasePHYOutput import BasePHYOutput
from litedram.phy.ddr5.BasePHYPatternGenerators import DQOePattern, DQSPattern
from litedram.phy.ddr5.BasePHYAddressSlicer import (PHYAddressSlicer, PHYAddressSlicerInput,
    PHYAddressSlicerOutput, PHYAddressSlicerRemap, PHYResetInput, PHYResetOutput)
from litedram.phy.ddr5.BasePHYCSR import BasePHYCSR
from litedram.phy.ddr5.BasePHYDQInterfaces import (
    BasePHYDQPadInput, BasePHYDQPhyOutput, BasePHYDQPhyOutputCTRL,
    BasePHYDQPadOutput, BasePHYDQPhyInput, BasePHYDQPhyInputCTRL, BasePHYDQPhyOutputBuffer)

from litedram.phy.ddr5.BasePHYDQReadPath import (BasePHYDQReadPath, BasePHYDQRetimeReadPath)

from litedram.phy.ddr5.BasePHYDQSWritePath import (BasePHYWritePathDQS, BasePHYDQSWritePathBuffer,
    BasePHYWritePathDQSInput, BasePHYWritePathDQSOutput)
from litedram.phy.ddr5.BasePHYDQWritePath import BasePHYDQWritePath
from litedram.phy.ddr5.BasePHYDMPath import BasePHYDMPath


class DDR5PHY(Module, AutoCSR):
    """Core of DDR5 PHYs.

    This class implements all the logic required to convert DFI to/from pads.
    It works in a single clock domain. Signals for DRAM pads are stored in
    BasePHYOutput (self.out). Concrete implementations of DDR5 PHYs derive
    from this class and perform (de-)serialization of BasePHYOutput to pads.

    DFI commands
    ------------
    Not all DDR5 commands map directly to DFI commands. For this reason ZQC
    is treated specially in that DFI ZQC is translated into DDR5 MPC and has
    different interpretation depending on DFI.address.

    Due to the fact that DDR5 has 256-bit Mode Register space, the DFI MRS
    command encodes both register address *and* value in DFI.address (instead
    of the default in LiteDRAM to split them between DFI.address and DFI.bank).
    The MRS command is used both for Mode Register Write and Mode Register Read.
    The command is selected based on the value of DFI.bank.

    Refer to the documentation in `commands.py` for further information.

    Parameters
    ----------
    pads : object
        Object containing DDR5 pads.
    sys_clk_freq : float
        Frequency of memory controller's clock.
    ser_latency : Latency
        Additional latency introduced due to signal serialization.
    des_latency : Latency
        Additional latency introduced during signal deserialization.
    phytype : str
        Name of the PHY (concrete implementation).
    cmd_delay : int
        Used to force cmd delay during initialization in BIOS.
    masked_write : bool
        Use masked variant of WRITE command.
    """
    def __init__(self, pads, *,
                 sys_clk_freq, ser_latency, des_latency, phytype, direct_control,
                 ca_cdc_min_max_delay, wr_cdc_min_max_delay,
                 ca_domain, wr_dqs_domain, dq_domain,
                 per_pin_ca_domain,
                 out_CDC_CA_primitive_cls=SimpleCDCWrap,
                 out_CDC_primitive_cls=SimpleCDCWrap,
                 with_sub_channels=False, cmd_delay=None, masked_write=False,
                 extended_overlaps_check=False, with_odelay=False,
                 with_clock_odelay=False, with_address_odelay=False,
                 with_idelay=False, with_per_dq_idelay=False,
                 csr_ca_cdc=None, csr_dqs_cdc=None,
                 csr_dq_rd_cdc=None, csr_dq_wr_cdc=None,
                 wr_dqs_rst=None, wr_dq_rst=None, rd_dq_rst=None,
                 rd_extra_delay=Latency(sys=0),
                 i_domain=None, i_domain_ratio=1, o_doamin=None, o_domain_ratio=1,
                 SyncFIFO_cls=SyncFIFO,
                 default_read_latency=0, default_write_latency=0, leds=None):

        self.pads        = pads
        self.memtype     = memtype     = "DDR5"
        self.nranks      = nranks      = len(pads.cs_n) if hasattr(pads, "cs_n") else len(pads.A_cs_n) if hasattr(pads, "A_cs_n") else 1
        self.databits    = databits    = len(pads.dq) if hasattr(pads, "dq") else len(pads.A_dq)
        self.strobes     = strobes     = len(pads.dqs_t) if hasattr(pads, "dqs_t") else len(pads.A_dqs_t)
        address_lines    = len(pads.ca) if hasattr(pads, "ca") else len(pads.A_ca)
        self.addressbits = addressbits = 18 # for activate row address
        self.bankbits    = bankbits    = 8  # 5 bankbits, but we use 8 for Mode Register address in MRS
        self.nphases     = nphases     = 4
        self.with_sub_channels         = with_sub_channels
        self.tck         = tck         = 1 / (nphases*sys_clk_freq)
        assert databits % 4 == 0
        assert nphases == 4, "Works for 4 phases, may not work for other"

        self.with_per_dq_idelay = with_per_dq_idelay
        self.dq_dqs_ratio = dq_dqs_ratio = databits // strobes
        nibbles = databits//4

        prefixes = [""] if not with_sub_channels else ["A_", "B_"]
        # Registers --------------------------------------------------------------------------------
        self.submodules.CSRModule = BasePHYCSR(
            prefixes,
            nphases,
            nranks,
            nibbles,
            with_clock_odelay,
            with_address_odelay,
            with_idelay,
            with_odelay,
            with_per_dq_idelay,
            databits,
            dq_dqs_ratio,
        )
        self.CSRs = CSRs = self.CSRModule.CSR_to_dict()

        def cdc_ca(i):
            if csr_ca_cdc is None:
                return i
            return csr_ca_cdc(i)

        def cdc_dq_wr(i, prefix):
            if csr_dq_wr_cdc is None or csr_dq_wr_cdc[prefix] is None:
                return i
            return csr_dq_wr_cdc[prefix](i)

        def cdc_dqs_wr(i, prefix):
            if csr_dqs_cdc is None or csr_dqs_cdc[prefix] is None:
                return i
            return csr_dqs_cdc[prefix](i)

        def cdc_dq_rd(i, prefix):
            if csr_dq_rd_cdc is None or csr_dq_rd_cdc[prefix] is None:
                return i
            return csr_dq_rd_cdc[prefix](i)

        def get_wr_dq_rst(prefix):
            if wr_dq_rst is None or wr_dq_rst[prefix] is None:
                return CSRs['_rst'].storage
            return wr_dq_rst[prefix]

        def get_wr_dqs_rst(prefix):
            if wr_dqs_rst is None or wr_dqs_rst[prefix] is None:
                return CSRs['_rst'].storage
            return wr_dqs_rst[prefix]

        def get_rd_dq_rst(prefix):
            if rd_dq_rst is None or rd_dq_rst[prefix] is None:
                return CSRs['_rst'].storage
            return rd_dq_rst[prefix]

        self.CDCCSRs = CDCCSRs = dict()

        for key, CSR in CSRs.items():
            if reduce(or_, [i in key for i in ["preamble", "wlevel_en", "dly_sel", "dq_dly_sel"]]):
                continue
            if reduce(or_, [i in key for i in ["ckdly", "cadly", "csdly", "pardly"]]):
                continue
            elif "ck_wdly" in key:
                for prefix in prefixes:
                    if prefix in key:
                        if "_inc" in key:
                            CDCCSRs[key] = cdc_dqs_wr(CSR.re, prefix)
                        elif "_rst" in key:
                            CDCCSRs[key] = cdc_dqs_wr(CSR.re, prefix) | get_wr_dqs_rst(prefix)
            elif "ck_wddly" in key:
                for prefix in prefixes:
                    if prefix in key:
                        if "_inc" in key:
                            CDCCSRs[key] = cdc_dq_wr(CSR.re, prefix)
                        elif "_rst" in key:
                            CDCCSRs[key] = cdc_dq_wr(CSR.re, prefix) | get_wr_dq_rst(prefix)
            elif "ck_rdly" in key:
                continue # use CDCs when DQ Read path is in its own domain
                #for prefix in prefixes:
                #    if prefix in key:
                #        if "_inc" in key:
                #            CDCCSRs[key] = cdc_dq_rd(CSR.re, prefix)
                #        elif "_rst" in key:
                #            CDCCSRs[key] = cdc_dq_rd(CSR.re | CSRs['_rst'].storage, prefix)

        # PHY settings -----------------------------------------------------------------------------
        combined_data_bits = databits if not with_sub_channels else 2*databits
        combined_strobes = strobes if not with_sub_channels else 2*strobes

        # Parameters -------------------------------------------------------------------------------
        def get_cl_cw(memtype, tck):
            f_to_cl_cwl = OrderedDict()
            f_to_cl_cwl[3200e6] = 22
            f_to_cl_cwl[3600e6] = 28
            f_to_cl_cwl[4000e6] = 32
            f_to_cl_cwl[4400e6] = 36
            f_to_cl_cwl[4800e6] = 40
            f_to_cl_cwl[5200e6] = 42
            f_to_cl_cwl[5600e6] = 46
            f_to_cl_cwl[6000e6] = 50
            f_to_cl_cwl[6400e6] = 54
            f_to_cl_cwl[6800e6] = 56
            for f, cl in f_to_cl_cwl.items():
                if tck > 1/f:
                    return cl
            raise ValueError

        # Commands are sent over 2 DRAM clocks (sys4x) and we count cl/cwl from last bit
        cmd_latency     = 2
        cl              = get_cl_cw(memtype, tck)
        cwl = cl - 2

        # DFI Interface ----------------------------------------------------------------------------
        self.dfi = dfi = Interface(14, 1, nranks, 2*combined_data_bits, nphases=nphases, with_sub_channels=with_sub_channels)

        # Now prepare the data by converting the sequences on adapters into sequences on the pads.
        # We have to ignore overlapping commands, and module timings have to ensure that there are
        # no overlapping commands anyway.
        self.out = BasePHYOutput(nphases, databits, nranks, nibbles, with_sub_channels, name="basephy")

        # Address path delay before serialization
        # Handle CA/CS/PAR
        addr_pre_ser_delay = self.handle_ca(prefixes, dfi, nphases, nranks, out_CDC_CA_primitive_cls, ca_domain, per_pin_ca_domain)

        self.des_latency          = des_latency
        self.ser_latency          = ser_latency
        self.rd_cdc_min_max_delay = (Latency(sys=0), Latency(sys=0))
        self.ca_cdc_min_max_delay = ca_cdc_min_max_delay
        self.wr_cdc_min_max_delay = wr_cdc_min_max_delay

        # Read latency
        # This value should be the worst case delay between sending a read cmd and
        # getting data back. The exact delay may vary based on the training result.
        self.min_read_latency, self.max_read_latency = \
            BasePHYDQReadPath.get_min_max_supported_latencies(
                nphases, addr_pre_ser_delay, 0, self.ca_cdc_min_max_delay,
                self.rd_cdc_min_max_delay, (Latency(sys=0), Latency(sys=0)),
                ser_latency, des_latency)
        read_latency = (self.max_read_latency + nphases - 1) // nphases

        # Write latency
        # Set to 0, Training PHY will align DQS and DQ for write commands
        # See write leveling training in JESD79-5A
        # Max supported latency is 64 DRAM bus cycles + 1 for 2N mode
        # WRDATA_EN buffer delay for DQS
        dqs_wr_delay = BasePHYDQSWritePathBuffer.get_delay(nphases)
        # WRDATA_EN buffer delay for DQ
        dq_wr_rd_delay = BasePHYDQPhyOutputBuffer.get_delay(nphases)
        min_write_latency, write_addjust = \
            BasePHYWritePathDQS.get_min_max_supported_latencies(
                nphases//2, addr_pre_ser_delay, dqs_wr_delay,
                self.ca_cdc_min_max_delay, self.wr_cdc_min_max_delay)

        BasePHYDQWritePath.get_min_max_supported_latencies(
            nphases//2, addr_pre_ser_delay, dq_wr_rd_delay,
            self.ca_cdc_min_max_delay, self.wr_cdc_min_max_delay)

        BasePHYDMPath.get_min_max_supported_latencies(
            nphases//2, addr_pre_ser_delay, dq_wr_rd_delay,
            self.ca_cdc_min_max_delay, self.wr_cdc_min_max_delay)

        self.settings = PhySettings(
            phytype       = phytype,
            memtype       = memtype,
            databits      = combined_data_bits,
            dfi_databits  = 2*combined_data_bits,
            nranks        = nranks,
            nphases       = nphases,
            rdphase       = CSRs['_rdphase'].storage,
            wrphase       = CSRs['_wrphase'].storage,
            cl            = cl,
            cwl           = cwl,
            masked_write  = masked_write,
            read_latency  = read_latency + 3,
            write_latency = 0,
            cmd_latency   = cmd_latency,
            cmd_delay     = cmd_delay,
            strobes       = combined_strobes,
            nibbles       = nibbles,
            address_lines       = address_lines,
            min_write_latency   = min_write_latency + write_addjust,
            min_read_latency    = 2,
            with_sub_channels   = with_sub_channels,
            with_clock_odelay   = with_clock_odelay,
            with_address_odelay = with_address_odelay,
            with_odelay         = with_odelay,
            with_idelay         = with_idelay,
            with_per_dq_idelay  = with_per_dq_idelay,
            direct_control      = direct_control,
            t_ctrl_delay        = addr_pre_ser_delay,
            soc_freq            = sys_clk_freq,
        )

        # Clocks -----------------------------------------------------------------------------------
        self.clk_pattern = bitpattern("-_-_-_-_")

        # Simple commands --------------------------------------------------------------------------
        self.comb += [phase.alert_n.eq(reduce(or_, self.out.alert_n[i*2:(i+1)*2])) for i, phase in enumerate(self.dfi.phases)]
        _alert = Signal.like(self.out.alert_n)
        self.sync += _alert.eq(self.out.alert_n)

        op = Signal()
        self._sample_memory = Signal()
        self.sync += [
            If(CSRs['reset_alert'].re,
                self._sample_memory.eq(CSRs['alert_reduce'].fields.initial_state),
                op.eq(CSRs['alert_reduce'].fields.operation),
            ).Elif(CSRs['sample_alert'].storage,
                If(op,
                    self._sample_memory.eq(self._sample_memory & reduce(and_, _alert))
                ).Else(
                    self._sample_memory.eq(self._sample_memory | reduce(or_, _alert))
                ),
            ).Else(
                CSRs['alert'].status.eq(self._sample_memory),
            )
        ]

        # Handle read/write DQ/DQS paths
        def rep(sig, cnt):
            return sig
        if nibbles % 2 == 1:
            rep = Replicate
        fifo_ready = []

        for prefix in prefixes:
            # Read Control Path --------------------------------------------------------------------
            rd_dfi_ctrl = BasePHYDQPhyInputCTRL(nphases)
            rd_fifo_re = Signal()
            rd_fifo_valid = Signal()
            rd_fifo_valids = []
            _csr = {}
            _csr['wlevel_en'] = CSRs[prefix+'wlevel_en'].storage
            _csr['discard_rd_fifo'] = CSRs[prefix+'discard_rd_fifo'].storage
            self.submodules += BasePHYDQRetimeReadPath(
                read_latency=read_latency,
                dfi=self.dfi,
                dfi_ctrl=rd_dfi_ctrl,
                rd_fifo_valid=rd_fifo_valid,
                rd_fifo_re=rd_fifo_re,
                CSRs=_csr,
                prefix=prefix,
            )
            # Write Control Path -------------------------------------------------------------------
            # DQS ----------------------------------------------------------------------------------
            wr_dqs_dfi_ctrl = BasePHYWritePathDQSInput(nphases//2)
            dfi_in    = BasePHYWritePathDQSInput(nphases)
            self.comb += [t_phase.wrdata_en.eq(getattr(s_phase, prefix).wrdata_en)
                for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)]
            dfi_inter = BasePHYWritePathDQSInput(nphases)
            self.submodules += BasePHYDQSWritePathBuffer(dfi_in, dfi_inter)

            width = len(dfi_inter.raw_bits())
            dqs_async = out_CDC_primitive_cls("sys", wr_dqs_domain[prefix],
                width, width//2)
            self.submodules += dqs_async

            input_arr = [phase.wrdata_en for phase in dfi_inter.phases]
            output_arr = [phase.wrdata_en for phase in wr_dqs_dfi_ctrl.phases]

            self.comb += [
                dqs_async.din.eq(Cat(input_arr)),
                dqs_async.we.eq(CSRs["_enable_fifos"].storage),
                Cat(output_arr).eq(dqs_async.dout),
                dqs_async.re.eq(dqs_async.readable),
            ]
            if leds is not None:
                fifo_ready.append(dqs_async.readable)
            # DQ -----------------------------------------------------------------------------------
            wr_dq_dfi_ctrl = BasePHYDQPhyOutputCTRL(nphases//2)
            wr_dq_common_start = Signal()
            self.sync += wr_dq_common_start.eq(CSRs["_enable_fifos"].storage)

            dfi_in    = BasePHYDQPhyOutputCTRL(nphases)
            self.comb += [t_phase.wrdata_en.eq(getattr(s_phase, prefix).wrdata_en)
                for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)]
            dfi_inter = BasePHYDQPhyOutputCTRL(nphases)
            self.submodules += BasePHYDQPhyOutputBuffer(dfi_in, dfi_inter)

            width = len(dfi_inter.raw_bits())
            dq_async_ctrl = out_CDC_primitive_cls("sys", dq_domain[prefix],
                width, width//2)
            self.submodules += dq_async_ctrl

            input_arr = [phase.wrdata_en for phase in dfi_inter.phases]
            output_arr = [phase.wrdata_en for phase in wr_dq_dfi_ctrl.phases]

            self.comb += [
                dq_async_ctrl.din.eq(Cat(input_arr)),
                dq_async_ctrl.we.eq(wr_dq_common_start),
                Cat(output_arr).eq(dq_async_ctrl.dout),
                dq_async_ctrl.re.eq(dq_async_ctrl.readable),
            ]
            if leds is not None:
                fifo_ready.append(dq_async_ctrl.readable)

            for nibble in range(nibbles):
                # Read Path ------------------------------------------------------------------------
                rd_dq_cnt = Signal(16)
                rd_preamble_cnt = Signal(16)
                _csr = {}
                _csr['dly_sel'] = CSRs[prefix+'dly_sel'].storage[nibble]
                _csr['ck_rdly_inc'] = CSRs[prefix+'ck_rdly_inc'].re
                _csr['ck_rdly_rst'] = CSRs[prefix+'ck_rdly_rst'].re
                _csr['ck_rddly_dq'] = rd_dq_cnt
                _csr['ck_rddly_preamble'] = rd_preamble_cnt
                _csr['preamble'] = CSRs[prefix+'preamble'].status
                _csr['wlevel_en'] = CSRs[prefix+'wlevel_en'].storage

                dq_offset = nibble*4
                dfi      = BasePHYDQPhyInput(nphases, 4)
                pads_out = BasePHYDQPadOutput(nphases, 4)

                self.comb += [t_phase.rddata_en.eq(getattr(s_phase, prefix).rddata_en)
                    for t_phase, s_phase in zip(rd_dfi_ctrl.phases, self.dfi.phases)]
                self.comb += pads_out.dqs_t_i.eq(getattr(self.out, prefix+'dqs_t_i')[nibble])
                self.comb += [getattr(pads_out, f"dq{i}_i").eq(
                    getattr(self.out, prefix+'dq_i')[dq_offset+i]) for i in range(4)]

                self.submodules += BasePHYDQReadPath(
                    dfi=dfi,
                    dfi_ctrl=rd_dfi_ctrl,
                    phy=pads_out,
                    rd_re=rd_fifo_re,
                    rd_valids=rd_fifo_valids,
                    dq_dqs_ratio=4,
                    CSRs=_csr,
                    default_read_latency=default_read_latency,
                )
                self.sync += [
                    If(CSRs[prefix+'dly_sel'].storage[nibble],
                        CSRs[prefix+'ck_rddly_dq'].status.eq(rd_dq_cnt),
                        CSRs[prefix+'ck_rddly_preamble'].status.eq(rd_preamble_cnt),
                    ),
                ]

                rddata_start = nibble*8
                rddata_end   = (nibble+1)*8
                if nibbles % 2 == 0:
                    mux_rddata = nibble//2 * 16 + (nibble%2) * 4
                    self.comb += [
                        If(CSRs[prefix+'dq_dqs_ratio'].storage[3],
                            *[getattr(t_phase, prefix).rddata[mux_rddata: mux_rddata + 4].eq(
                                s_phase.rddata[:4]) for t_phase, s_phase in zip(self.dfi.phases, dfi.phases)],
                            *[getattr(t_phase, prefix).rddata[mux_rddata + 8: mux_rddata + 12].eq(
                                s_phase.rddata[4:]) for t_phase, s_phase in zip(self.dfi.phases, dfi.phases)],
                        ).Else(
                            *[getattr(t_phase, prefix).rddata[rddata_start:rddata_end].eq(s_phase.rddata)
                              for t_phase, s_phase in zip(self.dfi.phases, dfi.phases)],
                        )
                    ]
                else:
                    self.comb += [
                        getattr(t_phase, prefix).rddata[rddata_start:rddata_end].eq(s_phase.rddata)
                        for t_phase, s_phase in zip(self.dfi.phases, dfi.phases)
                    ]

                # Write Path -----------------------------------------------------------------------
                # DQS ------------------------------------------------------------------------------
                wr_dqs_cnt = Signal(16)
                _csr = {}
                _csr['dly_sel'] = CSRs[prefix+'dly_sel'].storage[nibble]
                _csr['ck_wdly_inc'] = CDCCSRs[prefix+'ck_wdly_inc']
                _csr['ck_wdly_rst'] = CDCCSRs[prefix+'ck_wdly_rst']
                _csr['ck_wdly_dqs'] = wr_dqs_cnt
                _csr['wlevel_en'] = CSRs[prefix+'wlevel_en'].storage

                out = BasePHYWritePathDQSOutput(nphases//2)
                self.submodules += ClockDomainsRenamer(wr_dqs_domain[prefix])(
                    BasePHYWritePathDQS(
                        dfi=wr_dqs_dfi_ctrl, out=out, CSRs=_csr,
                        default_write_latency=default_write_latency,
                        SyncFIFO_cls=SyncFIFO_cls,
                   )
                )
                self.sync += [
                    If(CSRs[prefix+'dly_sel'].storage[nibble],
                        CSRs[prefix+'ck_wdly_dqs'].status.eq(wr_dqs_cnt),
                    ),
                ]

                self.comb += [
                    getattr(self.out, prefix+'dqs_t_o')[nibble].eq(out.dqs_t_o),
                    getattr(self.out, prefix+'dqs_c_o')[nibble].eq(out.dqs_c_o),
                    getattr(self.out, prefix+'dqs_oe')[nibble].eq(out.dqs_oe),
                ]

                # DQ -------------------------------------------------------------------------------
                wr_dq_cnt = Signal(16)
                _csr = {}
                _csr['dly_sel'] = CSRs[prefix+'dly_sel'].storage[nibble]
                _csr['ck_wddly_inc'] = CDCCSRs[prefix+'ck_wddly_inc']
                _csr['ck_wddly_rst'] = CDCCSRs[prefix+'ck_wddly_rst']
                _csr['ck_wdly_dq'] = wr_dq_cnt
                _csr['wlevel_en'] = CSRs[prefix+'wlevel_en'].storage

                wrdata_start = nibble*8
                wrdata_end   = (nibble+1)*8
                if nibbles % 2 == 0:
                    wrdata_m_start = nibble
                    wrdata_m_end   = nibble+2
                else:
                    wrdata_m_start = nibble
                    wrdata_m_end   = nibble+1

                dfi_in    = BasePHYDQPhyOutput(nphases, 4)
                if nibbles % 2 == 0:
                    mux_wrdata = nibble//2 * 16 + (nibble%2) * 4
                    self.comb += [
                        If(CSRs[prefix+'dq_dqs_ratio'].storage[3],
                            *[t_phase.wrdata[:4].eq(
                                getattr(s_phase, prefix).wrdata[mux_wrdata: mux_wrdata + 4])
                                for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)],
                            *[t_phase.wrdata[4:].eq(
                                getattr(s_phase, prefix).wrdata[mux_wrdata + 8: mux_wrdata + 12])
                                for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)],
                        ).Else(
                            *[t_phase.wrdata.eq(getattr(s_phase, prefix).wrdata[wrdata_start:wrdata_end])
                            for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)]
                        )
                    ]
                    self.comb += []
                    if nibble % 2 == 0:
                        self.comb += [t_phase.wrdata_mask.eq(
                            rep(getattr(s_phase, prefix).wrdata_mask[wrdata_m_start:wrdata_m_end], 2))
                            for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)]
                else:
                    self.comb += [
                        t_phase.wrdata.eq(getattr(s_phase, prefix).wrdata[wrdata_start:wrdata_end])
                        for t_phase, s_phase in zip(dfi_in.phases, self.dfi.phases)
                    ]

                dfi_inter = BasePHYDQPhyOutput(nphases, 4)
                self.submodules += BasePHYDQPhyOutputBuffer(dfi_in, dfi_inter)

                width = len(dfi_inter.raw_bits())
                dq_async = out_CDC_primitive_cls("sys", dq_domain[prefix],
                    width, width//2)
                self.submodules += dq_async

                wr_dq_dfi = BasePHYDQPhyOutput(nphases//2, 4)
                input_arr = [Cat([phase.wrdata, phase.wrdata_mask]) for phase in dfi_inter.phases]
                output_arr = [Cat([phase.wrdata, phase.wrdata_mask]) for phase in wr_dq_dfi.phases]

                self.comb += [
                    dq_async.din.eq(Cat(input_arr)),
                    dq_async.we.eq(wr_dq_common_start),
                    Cat(output_arr).eq(dq_async.dout),
                    dq_async.re.eq(dq_async.readable),
                ]
                if leds is not None:
                    fifo_ready.append(dq_async.readable)

                out = BasePHYDQPadInput(nphases//2, 4)
                self.submodules += ClockDomainsRenamer(dq_domain[prefix])(
                    BasePHYDQWritePath(
                        dfi=wr_dq_dfi, dfi_ctrl=wr_dq_dfi_ctrl, out=out, CSRs=_csr,
                        default_write_latency=default_write_latency,
                        SyncFIFO_cls=SyncFIFO_cls,
                        dq_dqs_ratio=4,
                    )
                )
                self.sync += [
                    If(CSRs[prefix+'dly_sel'].storage[nibble],
                        CSRs[prefix+'ck_wdly_dq'].status.eq(wr_dq_cnt),
                    ),
                ]

                if nibble % 2 == 0 and nibbles % 2 == 0:
                    _csr['dly_sel'] = reduce(and_, CSRs[prefix+'dly_sel'].storage[nibble:nibble+2])
                    self.submodules += ClockDomainsRenamer(dq_domain[prefix])(
                        BasePHYDMPath(
                            dfi=wr_dq_dfi, dfi_ctrl=wr_dq_dfi_ctrl, out=out, CSRs=_csr,
                            default_write_latency=default_write_latency,
                            SyncFIFO_cls=SyncFIFO_cls,
                        )
                    )

                self.comb += getattr(self.out, prefix+'dq_oe')[nibble].eq(
                    getattr(out, f'dq0_oe')),
                for bit in range(4):
                    self.comb += getattr(self.out, prefix+'dq_o')[bit + nibble*4].eq(getattr(out, f"dq{bit}_o"))
                self.comb += getattr(self.out, prefix+'dm_n_o')[nibble].eq(out.dm_n_o)

            self.comb += rd_fifo_valid.eq(reduce(and_, rd_fifo_valids))
            if leds is not None:
                self.comb += leds.eq(Cat(fifo_ready))


    def handle_ca(self, prefixes, dfi, nphases, nranks, out_CDC_primitive_cls, ca_domain, per_pin_ca_domain):
        ca_outs = []
        rst_in  = PHYResetInput(nphases)
        for t_phase, s_phase in zip(rst_in.phases, dfi.phases):
            self.comb += t_phase.reset_n.eq(s_phase.reset_n)
        rst_out = PHYResetOutput(nphases)
        for t_phase, s_phase in zip(rst_out.phases, rst_in.phases):
            self.sync += t_phase.reset_n.eq(Replicate(s_phase.reset_n, 2))

        ca_outs.append(("", rst_out))
        for prefix in prefixes:
            slicer_in  = PHYAddressSlicerInput(nphases, nranks)
            self.submodules += PHYAddressSlicerRemap(dfi, slicer_in, prefix)
            slicer_out = PHYAddressSlicerOutput(nphases, nranks)
            address_slicer = PHYAddressSlicer(slicer_out, slicer_in,
                self.CSRs['_rdimm_mode'].storage, self.CSRs[prefix+'par_enable'].storage,
                self.CSRs[prefix+'par_value'].storage,
                nphases, nranks)
            self.submodules += address_slicer
            ca_outs.append((prefix, slicer_out))

        width = reduce(add,
            [len(sig) for sig in ca_outs[1][1].flatten()]) * len(ca_outs[1:]) + \
            2 * nphases

        input_arr = []
        for i in range(nphases):
            for _, ca_out in ca_outs:
                input_arr.append(Cat(ca_out.phases[i].flatten()))

        ca_outs_intermediate = []
        inter_rst_out = PHYResetOutput(nphases//2)
        ca_outs_intermediate.append(("", inter_rst_out))
        for prefix in prefixes:
            inter_slicer_out = PHYAddressSlicerOutput(nphases//2, nranks)
            ca_outs_intermediate.append((prefix, inter_slicer_out))

        intermediate_arr = []
        for i in range(nphases//2):
            for _, inter_ca_out in ca_outs_intermediate:
                intermediate_arr.append(Cat(inter_ca_out.phases[i].flatten()))

        switch_to_fifo = Signal()
        ca_async = out_CDC_primitive_cls("sys", ca_domain, width, width//2)
        self.submodules.ca_async = ca_async

        cd_ca_dom = getattr(self.sync, ca_domain)
        cd_ca_dom += switch_to_fifo.eq(ca_async.readable)
        self.comb += [
            ca_async.din.eq(Cat(input_arr)),
            ca_async.we.eq(self.CSRs["_enable_fifos"].storage),
            If(switch_to_fifo,
                Cat(intermediate_arr).eq(ca_async.dout),
            ),
            ca_async.re.eq(ca_async.readable),
        ]

        translate = {}
        translate['reset_n'] = [Cat(phase.reset_n for phase in ca_outs_intermediate[0][1].phases)]
        for prefix, _ca_async in ca_outs_intermediate[1:]:
            for func, count in [("ca", 14), ("cs_n", nranks), ("par", 1)]:
                translate[prefix+func] = []
                for i in range(count):
                    translate[prefix+func].append(Cat([getattr(phase, func+str(i)) for phase in _ca_async.phases]))

        for func, sigs in translate.items():
            for i, sig in enumerate(sigs):
                out_sig = getattr(self.out, func)
                if isinstance(out_sig, list):
                    out_sig = out_sig[i]
                if per_pin_ca_domain is not None and func in per_pin_ca_domain and len(per_pin_ca_domain[func]) > i:
                    _cd = getattr(self.sync, per_pin_ca_domain[func][i])
                    _cd += out_sig.eq(sig)
                else:
                    cd_ca_dom += out_sig.eq(sig)

        return PHYAddressSlicerRemap.get_delay(nphases) + PHYAddressSlicer.get_delay(nphases) + nphases//2


    def get_rst(self, byte, rst, prefix="", clk="sys", dq=False, rst_overwrite=None):
        if rst_overwrite is None:
            rst_overwrite = self.CSRs['_rst'].storage
        cd_clk = getattr(self.sync, clk)
        CSRs = self.CSRs
        t = Signal()
        if not dq:
            cd_clk += t.eq((CSRs[prefix+'dly_sel'].storage[byte] & rst) | rst_overwrite)
        elif not self.with_per_dq_idelay:
            cd_clk += t.eq((CSRs[prefix+'dly_sel'].storage[byte//4] & rst) | rst_overwrite)
        else:
            cd_clk += t.eq((CSRs[prefix+'dly_sel'].storage[byte//4] &
                            CSRs[prefix+'dq_dly_sel'].storage[byte%4] & rst) |
                            rst_overwrite)
        return t

    def get_inc(self, byte, stb, prefix="", clk="sys", dq=False):
        cd_clk = getattr(self.sync, clk)
        CSRs = self.CSRs
        t = Signal()
        if not dq:
            cd_clk += t.eq(CSRs[prefix+'dly_sel'].storage[byte] & stb)
        elif not self.with_per_dq_idelay:
            cd_clk += t.eq(CSRs[prefix+'dly_sel'].storage[byte//4] & stb)
        else:
            cd_clk += t.eq(CSRs[prefix+'dly_sel'].storage[byte//4] &
                            CSRs[prefix+'dq_dly_sel'].storage[byte%4] & stb)
        return t
