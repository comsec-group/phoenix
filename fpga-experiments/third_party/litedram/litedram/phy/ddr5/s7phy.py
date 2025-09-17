#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import and_
from functools import reduce

from migen import *
from migen.genlib.fifo import _FIFOInterface
from migen.genlib.cdc import PulseSynchronizer, MultiReg

from litex.soc.interconnect.csr import *

from litedram.common import *
from litedram.phy.dfi import *

from litedram.phy.utils import delayed, Latency
from litedram.phy.ddr5.basephy import DDR5PHY

from litedram.phy.s7common import S7Common

class Xilinx7SeriesAsyncFIFO(Module):
    LATENCY=4 # 3 to pass through memory and 1 for output register
    WCL_LATENCY=5

    def __init__(self, wclk, rclk, width=72):
        assert type(wclk) == str
        assert type(rclk) == str
        assert width in [4, 9, 18, 36, 72], f"Xilinx 7 Sereis FIFO primitive supports widtths: "\
            "4,9,18,36, or 72, you tried {width}"

        self.width = width
        self.DI = Signal(width)
        self.WREN = Signal()
        self.FULL = Signal()

        self.DO = Signal(width)
        self.RDEN = Signal()
        self.EMPTY = Signal()
        self._rst  = Signal()

        fifo_primitive = "FIFO18E1"
        fifo_mode = "FIFO18"
        if width ==36:
            fifo_mode = "FIFO18_36"
        if width > 36:
            fifo_mode = "FIFO36_72"
            fifo_primitive = "FIFO36E1"

        r_done = Signal()
        r_finished = Signal()
        r_ready = PulseSynchronizer(rclk, wclk)
        self.submodules += r_ready
        self.comb += [
            r_ready.i.eq(r_done),
            r_finished.eq(r_ready.o),
        ]

        w_done = Signal()
        w_finished = Signal()
        w_ready = PulseSynchronizer(wclk, rclk)
        self.submodules += w_ready
        self.comb += [
            w_ready.i.eq(w_done),
            w_finished.eq(w_ready.o),
        ]

        i_cd = getattr(self.sync, wclk)
        w_cnt = Signal(4, reset=15)
        i_cd += [
            If(r_finished,
                w_cnt.eq(0),
            ).Elif(w_cnt<10,
                w_cnt.eq(w_cnt+1),
            ).Elif(w_cnt == 10,
                w_cnt.eq(w_cnt+1),
                w_done.eq(1),
            ).Else(
                w_done.eq(0),
            ),
        ]

        o_cd = getattr(self.sync, rclk)
        r_rst = Signal(reset=1)
        r_cnt = Signal(4)
        o_cd += [
            If(self._rst,
                r_cnt.eq(0),
                r_rst.eq(1),
            ).Elif(r_cnt<10,
                r_cnt.eq(r_cnt+1),
            ).Elif(r_cnt == 10,
                r_done.eq(1),
                r_cnt.eq(r_cnt+1),
            ).Else(
                r_done.eq(0),
            ),
            If(w_finished,
                r_rst.eq(0),
            ),
        ]

        self.specials += Instance(
            fifo_primitive,
            p_EN_SYN        = "FALSE",
            p_DO_REG        = 1,
            p_FIFO_MODE     = fifo_mode,
            p_DATA_WIDTH    = width,
            i_RST           = r_rst,
            i_WRCLK         = ClockSignal(wclk),
            i_WREN          = self.WREN,
            o_FULL          = self.FULL,
            i_DI            = self.DI[:(7*width)//8+1],
            i_DIP           = self.DI[(7*width)//8+1:],
            i_RDEN          = self.RDEN,
            i_RDCLK         = ClockSignal(rclk),
            o_EMPTY         = self.EMPTY,
            o_DO            = self.DO[:(7*width)//8+1],
            o_DOP           = self.DO[(7*width)//8+1:],
        )


class Xilinx7SeriesAsyncFIFOWrap(Module, _FIFOInterface):
    LATENCY     = Xilinx7SeriesAsyncFIFO.LATENCY
    WCL_LATENCY = Xilinx7SeriesAsyncFIFO.WCL_LATENCY
    _rst        = None

    def __init__(self, wclk, rclk, i_dw, o_dw, name=None):
        _FIFOInterface.__init__(self, max(i_dw, o_dw), 512)
        self.rclk = rclk
        width = max(i_dw, o_dw)
        fifo_72 = (width+71)//72
        self.cdcs = cdcs = [Xilinx7SeriesAsyncFIFO(wclk, rclk) for _ in range(fifo_72)]
        self.submodules += cdcs

        intermediate_din  = Signal(width)
        intermediate_dout = Signal(width)
        do_read           = Signal(reset=1)
        do_write          = Signal(reset=1)
        assert max(i_dw, o_dw)//min(i_dw, o_dw) in [1,2]
        w_cnt               = Signal()
        r_cnt               = Signal()
        r_cnt_i             = Signal()
        i_cd = getattr(self.sync, wclk)
        o_cd = getattr(self.sync, rclk)

        self.comb += [
            self.readable.eq(reduce(and_, [~cdc.EMPTY for cdc in cdcs]) | r_cnt),
            *[cdc.RDEN.eq(self.re & do_read) for cdc in cdcs],
            self.writable.eq(reduce(and_, [~cdc.FULL for cdc in cdcs])),
            *[cdc.WREN.eq(self.we & do_write) for cdc in cdcs],
            *[cdc.DI.eq(intermediate_din[i*72:(i+1)*72]) for i, cdc in enumerate(cdcs)],
            *[intermediate_dout[i*72:(i+1)*72].eq(cdc.DO) for i, cdc in enumerate(cdcs)],
        ]
        if i_dw < width:
            self.comb += self.dout.eq(intermediate_dout)
            reg = Signal(i_dw)
            self.comb += intermediate_din.eq(Cat(reg, self.din[:i_dw]))
            self.comb += do_write.eq((w_cnt == 1))
            i_cd += [
                If((w_cnt == 1),
                    w_cnt.eq(0),
                ).Elif(self.we,
                    reg.eq(self.din[:i_dw]),
                    w_cnt.eq(1),
                )
            ]
        elif o_dw < width:
            self.comb += intermediate_din.eq(self.din)
            self.comb += self.dout.eq(intermediate_dout.part(r_cnt_i*o_dw, o_dw))
            self.comb += do_read.eq((r_cnt == 0) & self.re)
            o_cd += [
                If((r_cnt == 0) & self.re,
                    r_cnt.eq(1),
                    r_cnt_i.eq(0),
                ).Else(
                    r_cnt.eq(0),
                    r_cnt_i.eq(1),
                )
            ]

    def do_finalize(self):
        for cdc in self.cdcs:
            self.comb += cdc._rst.eq(self._rst(self.rclk))



class S7DDR5PHY(DDR5PHY, S7Common):
    def __init__(self, pads, *, iodelay_clk_freq, with_odelay, crg,
                 with_idelay=True, with_per_dq_idelay=False,
                 with_sub_channels=False, pin_domains=None, pin_banks=None,
                 **kwargs):

        self.iodelay_clk_freq = iodelay_clk_freq
        assert pin_domains is not None
        assert pin_banks is not None

        def cdc_any(target):
            def new_cdc(i):
                o = Signal()
                psync = PulseSynchronizer("sys", target)
                self.submodules += psync
                self.comb += [
                    psync.i.eq(i),
                    o.eq(psync.o),
                ]
                return o
            return new_cdc
        self.cdc_any = cdc_any

        self.prefixes = prefixes = [""] if not with_sub_channels else ["A_", "B_"]

        ca_domain = None
        per_pin_ca_domain = {}
        ca_bank = {}
        for prefix in prefixes:
            for func in ["ca", "cs_n", "par"]:
                if prefix+func in pin_domains:
                    assert ca_domain is None or ca_domain == pin_domains[prefix+func][0][0]
                    ca_domain = pin_domains[prefix+func][0][0]
                    if pin_banks[prefix+func][0] not in ca_bank:
                        ca_bank[pin_banks[prefix+func][0]] = 0
                    ca_bank[pin_banks[prefix+func][0]] += 1
                    per_pin_ca_domain[prefix+func] = [f"{ca_domain}_{bank}" for bank in pin_banks[prefix+func]]

        if "reset_n" in pin_domains:
            per_pin_ca_domain["reset_n"] = [f"{ca_domain}_{bank}" for bank in pin_banks["reset_n"]]

        _max = ("", -1)
        for bank, count in ca_bank.items():
            if count > _max[1]:
                _max = (bank, count)
        ca_domain = f"{ca_domain}_{_max[0]}"

        wr_dqs_domains = {}
        for prefix in prefixes:
            if prefix+"dqs_t" in pin_domains:
                wr_dqs_domain = pin_domains[prefix+"dqs_t"][0][0]
                wr_dqs_bank = pin_banks[prefix+"dqs_t"][0]
                assert reduce(and_, [wr_dqs_bank == bank for bank in pin_banks[prefix+"dqs_t"]])
                wr_dqs_domains[prefix] = f"{wr_dqs_domain}_{wr_dqs_bank}"

        dq_wr_domains = {}
        dq_rd_domains = {}
        for prefix in prefixes:
            for func in ["dq", "dm"]:
                if prefix+func in pin_domains:
                    dq_wr_domain = pin_domains[prefix+func][0][0]
                    dq_rd_domain = pin_domains[prefix+func][1][0]
                    dq_bank = pin_banks[prefix+func][0]
                    assert reduce(and_, [dq_bank == bank for bank in pin_banks[prefix+func]])
                    if prefix not in dq_wr_domains:
                        dq_wr_domains[prefix] = f"{dq_wr_domain}_{dq_bank}"
                    if prefix not in dq_rd_domains:
                        dq_rd_domains[prefix] = f"{dq_rd_domain}_{dq_bank}"
                    assert dq_wr_domains[prefix] == f"{dq_wr_domain}_{dq_bank}"
                    assert dq_rd_domains[prefix] == f"{dq_rd_domain}_{dq_bank}"

        # It's easier to add reset signals to CDCs through type
        Xilinx7SeriesAsyncFIFOWrap._rst = crg.get_rst

        # DoubleRateDDR5PHY outputs half-width signals (comparing to DDR5PHY) in sys2x domain.
        # This allows us to use 8:1 DDR OSERDESE2/ISERDESE2 to (de-)serialize the data.
        super().__init__(pads,
            ser_latency       = Latency(sys2x=1),  # OSERDESE2 4:1 DDR (2 full-rate clocks)
            des_latency       = Latency(sys=2),  # ISERDESE2 NETWORKING
            phytype           = self.__class__.__name__,
            with_sub_channels = with_sub_channels,
            ca_domain         = ca_domain,
            wr_dqs_domain     = wr_dqs_domains,
            dq_domain         = dq_wr_domains,
            per_pin_ca_domain = per_pin_ca_domain,

            csr_ca_cdc        = cdc_any(ca_domain),
            csr_dq_rd_cdc     = {prefix: cdc_any(dom) for prefix, dom in dq_rd_domains.items()},
            csr_dq_wr_cdc     = {prefix: cdc_any(dom) for prefix, dom in dq_wr_domains.items()},
            csr_dqs_cdc       = {prefix: cdc_any(dom) for prefix, dom in wr_dqs_domains.items()},

            rd_dq_rst         = {prefix: crg.get_rst(dom) for prefix, dom in dq_rd_domains.items()},
            wr_dq_rst         = {prefix: crg.get_rst(dom) for prefix, dom in dq_wr_domains.items()},
            wr_dqs_rst        = {prefix: crg.get_rst(dom) for prefix, dom in wr_dqs_domains.items()},

            out_CDC_CA_primitive_cls = Xilinx7SeriesAsyncFIFOWrap,
            ca_cdc_min_max_delay =
                (Latency(sys2x=Xilinx7SeriesAsyncFIFOWrap.LATENCY), Latency(sys2x=(Xilinx7SeriesAsyncFIFOWrap.WCL_LATENCY))),
            out_CDC_primitive_cls = Xilinx7SeriesAsyncFIFOWrap,
            wr_cdc_min_max_delay =
                (Latency(sys2x=Xilinx7SeriesAsyncFIFOWrap.LATENCY), Latency(sys2x=(Xilinx7SeriesAsyncFIFOWrap.WCL_LATENCY))),

            with_odelay        = with_odelay,
            with_idelay        = with_idelay,
            rd_extra_delay     = Latency(sys2x=3),
            with_per_dq_idelay = with_per_dq_idelay,
            SyncFIFO_cls       = SimpleSyncFIFO,
            **kwargs
        )

        # nibble to output mapping
        self.mult = self.dq_dqs_ratio//4
        max_delay_taps = math.ceil(self.tck/(1/2/32/iodelay_clk_freq))
        self.max_delay_taps = max_delay_taps

        CSRs    = self.CSRs
        CDCCSRs = self.CDCCSRs
        crg.add_rst(CSRs['_rst'].storage)
        self.crg = crg

        self.settings.delays = max_delay_taps
        self.settings.write_leveling = True
        self.settings.write_latency_calibration = True
        self.settings.write_dq_dqs_training = True
        self.settings.read_leveling = True

        # Serialization ----------------------------------------------------------------------------
        pin_csr_mapping = {
            "ck_t":    ((CSRs["ckdly_inc"].re,      CSRs["ckdly_rst"].re),      None),
            "A_ck_t":    ((CSRs["ckdly_inc"].re,      CSRs["ckdly_rst"].re),      None),
            "B_ck_t":    ((CSRs["ckdly_inc"].re,      CSRs["ckdly_rst"].re),      None),
        }
        for prefix in prefixes:
            pin_csr_mapping |= {
                f"{prefix}par":   (
                    (CSRs[f"{prefix}pardly_inc"].re,   CSRs[f"{prefix}pardly_rst"].re),
                     None),
                f"{prefix}ca":    (
                    (CSRs[f"{prefix}cadly_inc"].re,    CSRs[f"{prefix}cadly_rst"].re),
                     None),
                f"{prefix}cs_n":  (
                    (CSRs[f"{prefix}csdly_inc"].re,    CSRs[f"{prefix}csdly_rst"].re),
                     None),
                f"{prefix}dq":    (
                    (CSRs[f"{prefix}wdly_dq_inc"].re,  CSRs[f"{prefix}wdly_dq_rst"].re),
                    (CSRs[f"{prefix}rdly_dq_inc"].re,  CSRs[f"{prefix}rdly_dq_rst"].re)),
                f"{prefix}dqs_t": (
                    (CSRs[f"{prefix}wdly_dqs_inc"].re, CSRs[f"{prefix}wdly_dqs_rst"].re),
                    (CSRs[f"{prefix}rdly_dqs_inc"].re, CSRs[f"{prefix}rdly_dqs_rst"].re)),
            }

        self.pin_domains     = pin_domains
        self.pin_banks       = pin_banks
        self.pin_csr_mapping = pin_csr_mapping
        self.with_odelay     = with_odelay

        self.cdc_cache  = cdc_cache = {}
        pin_oe_cache = {}
        for pin, count in pads.layout:
            if pin in ["mir", "cai", "ca_odt"]:
                self.comb += getattr(self.pads, pin).eq(0)
                continue

            assert pin in pin_domains, (pin, pin_domains)
            assert pin in pin_banks or count == len(pin_banks[pin]), (pin, count)
            assert reduce(and_, [pin_banks[pin][0] == pin_banks[pin][i] for i in range(1, count)], 1)
            if pin[-2:] == "_c":
                continue

            _diff   = "_t" in pin
            _is_ck  = "ck" in pin
            _is_io  = reduce(or_, [pin_type in pin for pin_type in ["dq", "dm_n"]]) # dq is in dqs
            _is_out = pin_domains[pin][0] is not None
            _is_in  = pin_domains[pin][1] is not None
            suffix  = f"_{pin_banks[pin][0]}"

            for i in range(count):
                if "_c" == pin[-2:]:
                    continue
                _in, _out = self.get_domains(pin, _is_in, _is_out, suffix)

                _pin = pin
                _pin_o = _pin
                _pin_i = _pin
                _pin_base = _pin if not _diff else _pin[:-2]
                _pin_func = _pin if len(prefixes) == 1 else _pin[2:]
                _pin_prefix = "" if len(prefixes) == 1 else _pin[:2]
                _pin_oe = None
                if _is_io:
                    _pin_i  = _pin + "_i"
                    _pin_o  = _pin + "_o"
                    _pin_oe = _pin_base + "_oe"

                if _is_ck:
                    if count == 1:
                        self.handle_ck(_out, pin)
                    else:
                        self.handle_ck(_out, pin, offset=i)
                    continue

                _sig_out = None
                _sig_oe  = None
                _sig_in  = None

                if _is_out:
                    mult = 1
                    if reduce(or_, [pin_type in pin for pin_type in ["dqs", "dm_n"]]):
                        mult = self.mult
                    out_sig = getattr(self.out, _pin_o)
                    if isinstance(out_sig, list):
                        out_sig = out_sig[i*mult]
                    _sig_out = out_sig[:4]

                if _is_io:
                    mult = 1
                    if reduce(or_, [pin_type in pin for pin_type in ["dq", "dm_n"]]):
                        mult = self.mult

                    idx = i
                    if _pin_func == "dq":
                        idx //= self.dq_dqs_ratio
                    idx *= mult

                    if (_pin_oe, idx) in pin_oe_cache:
                        _sig_oe = pin_oe_cache[(_pin_oe, idx)]
                    elif _pin_func == "dm_n"  and (_pin_prefix+"dq_oe", idx) in pin_oe_cache:
                        _sig_oe = pin_oe_cache[(_pin_prefix+"dq_oe", idx)]
                    else:
                        out_sig_oe = getattr(self.out, _pin_oe)
                        if isinstance(out_sig_oe, list):
                            out_sig_oe = out_sig_oe[idx]

                        _sig_oe_t = out_sig_oe
                        _sig_oe = Signal(4)
                        self.comb += _sig_oe.eq(~_sig_oe_t[:4])
                        pin_oe_cache[(_pin_oe, idx)] = _sig_oe

                if _is_in:
                    mult = 1
                    if reduce(or_, [pin_type in pin for pin_type in ["dqs", "dm_n"]]):
                        mult = self.mult
                    _sig_in = getattr(self.out, _pin_i)
                    if isinstance(_sig_in, list):
                        _sig_in = _sig_in[i*mult]

                if _is_io:
                    offset = i if count > 1 else None
                    self.handle_io(cd_out=_out, cd_in=_in, pin=pin, offset=offset,
                                    oe_sig=_sig_oe, in_sig=_sig_in, out_sig=_sig_out)
                elif _is_in:
                    offset = i if count > 1 else None
                    self.handle_i(cd_in=_in, in_sig=_sig_in, pin=pin, offset=offset)
                else:
                    offset = i if count > 1 else None
                    self.handle_o(cd_out=_out, out_sig=_sig_out, oe_sig=_sig_oe,
                                    pin=pin, offset=offset)

    def get_domains(self, pin, is_in, is_out, suffix):
        cd_out, cd_in = self.pin_domains[pin]
        if is_out:
            cd_out = (cd_out[0]+suffix, cd_out[1]+suffix)
        if is_in:
            cd_in = (cd_in[0]+suffix, cd_in[1]+suffix)
        return cd_in, cd_out

    def handle_single_ended(self, pad, *, out_sig=None, oe_sig=None, in_sig=None):
        if in_sig is not None and out_sig is not None:
            self.iobuf(din=out_sig, dout=in_sig, tin=oe_sig, dinout=pad)
        elif in_sig is not None:
            self.comb += in_sig.eq(pad)
        else:
            self.comb += pad.eq(out_sig)

    def handle_diff(self, pad_t, pad_c, *, out_sig=None, oe_sig=None, in_sig=None):
        if in_sig is not None and out_sig is not None:
            self.iobufds(din=out_sig, dout=in_sig, tin=oe_sig, dinout=pad_t, dinout_b=pad_c)
        elif in_sig is not None:
            raise NotImplementedError()
        else:
            self.obufds(din=out_sig, dout=pad_t, dout_b=pad_c)

    def handle_oser(self, cd_out, out_sig, *, oe_sig=None, inc_sig=None, rst_sig=None):
        delay     = Signal()
        _output    = Signal()
        _tri_state = None
        _with_odelay = inc_sig is not None
        oser_method = self.oserdese2_ddr
        if oe_sig is not None:
            _tri_state = Signal()
            oser_method = self.oserdese2_ddr_with_tri

        oserdes = oser_method(
            din = out_sig,
            **(dict(dout_fb=delay) if _with_odelay else dict(dout=_output)),
            **(dict(tout=_tri_state, tin=oe_sig) if oe_sig is not None else dict()),
            clkdiv  = cd_out[0],
            clk     = cd_out[1],
            rst_sig = self.crg.get_rst(cd_out[0]),
        )
        delay_state = None
        if _with_odelay:
            delay_state = Signal(5)
            self.odelaye2(
                din  = delay,
                dout = _output,
                rst  = rst_sig,
                inc  = inc_sig,
                clk  = "sys",
                cnt_value_out = delay_state,
            )
        return _output, _tri_state, delay_state

    def handle_iser(self, cd_in, in_sig, *, inc_sig=None, rst_sig=None):
        _input = Signal()
        _delayed_input = Signal()
        delay_state = Signal(5)
        self.idelaye2(
            din  = _input,
            dout = _delayed_input,
            rst  = rst_sig,
            inc  = inc_sig,
            init = self.max_delay_taps-1,
            clk  = "sys",
            dec  = True,
            cnt_value_out = delay_state,
        )

        self.iserdese2_ddr(
            din     = _delayed_input,
            dout    = in_sig,
            clk     = cd_in[1],
            clkdiv  = cd_in[0],
            rst_sig = self.crg.get_rst(cd_in[0]),
            ce      = self.crg.get_ce(cd_in[0]),
        )
        return _input, delay_state

    def get_pads(self, pin, *, offset=None):
        if offset is None:
            offset=0
        pad_t = getattr(self.pads, pin)[offset]
        pad_c = getattr(self.pads, pin[:-2]+"_c", None)
        if pad_c is not None:
            pad_c = pad_c[offset]
        return (pad_t, pad_c)


    def get_inc_rst(self, pin, cd, not_out, offset):
        prefix, _pin_func = ("", pin) if len(self.prefixes) == 1 else (pin[:2], pin[2:])
        dq = True if _pin_func in "dq" else False
        inc = None
        rst = None
        if pin not in self.pin_csr_mapping:
            return None, None
        if (pin, not_out, cd) not in self.cdc_cache:
            if cd != "sys":
                self.cdc_cache[(pin, not_out, cd)] = (
                    self.cdc_any(cd)(self.pin_csr_mapping[pin][not_out][0]),
                    self.cdc_any(cd)(self.pin_csr_mapping[pin][not_out][1])
                )
            else:
                self.cdc_cache[(pin, not_out, cd)] = (
                    self.pin_csr_mapping[pin][not_out][0],
                    self.pin_csr_mapping[pin][not_out][1]
                )
        inc_sig, rst_sig = self.cdc_cache[(pin, not_out, cd)]
        if offset is not None:
            inc = self.get_inc(offset, inc_sig, prefix, cd, dq=dq)
            rst = self.get_rst(offset, rst_sig, prefix, cd,
                dq=dq, rst_overwrite=self.crg.get_rst(cd))
        else:
            inc  = inc_sig
            rst  = rst_sig
        return inc, rst

    def get_out_inc_rst(self, pin, *, cd, offset=None):
        return self.get_inc_rst(pin, cd, 0, offset)

    def get_in_inc_rst(self, pin, *, cd, offset=None):
        return self.get_inc_rst(pin, cd, 1, offset)

    def handle_o(self, cd_out, out_sig, pin, *, offset=None, oe_sig=None):
        pad_t, pad_c = self.get_pads(pin, offset=offset)

        prefix, _pin_func = ("", pin) if len(self.prefixes) == 1 else (pin[:2], pin[2:])

        if _pin_func == "ck_t":
            offset = None
        inc_sig, rst_sig = None, None
        if self.with_odelay and pin in self.pin_csr_mapping:
            inc_sig, rst_sig = self.get_out_inc_rst(pin, offset=offset, cd="sys")

        to_pad, to_pad_oe, delay_state = self.handle_oser(
            cd_out, out_sig, oe_sig=oe_sig, inc_sig=inc_sig, rst_sig=rst_sig)

        offset = offset if offset else 0
        if self.with_odelay:
            if "ca" == _pin_func:
                self.sync += [
                    If(self.CSRs[prefix+'dly_sel'].storage[offset],
                        self.CSRs[prefix+'cadly'].status.eq(delay_state),
                    ),
                ]
            elif "cs_n" == _pin_func:
                self.sync += [
                    If(self.CSRs[prefix+'dly_sel'].storage[offset],
                        self.CSRs[prefix+'csdly'].status.eq(delay_state),
                    ),
                ]

        if pad_c is not None:
            self.handle_diff(pad_t, pad_c, out_sig=to_pad, oe_sig=to_pad_oe)
        else:
            self.handle_single_ended(pad_t, out_sig=to_pad, oe_sig=to_pad_oe)

    def handle_i(self, cd_in, in_sig, pin, *, offset=None):
        pad_t, pad_c = self.get_pads(pin, offset=offset)

        inc_sig, rst_sig = self.get_in_inc_rst(pin, offset=offset, cd="sys")
        from_pad, delay_state = self.handle_iser(
            cd_in=cd_in, in_sig=in_sig, inc_sig=inc_sig, rst_sig=rst_sig)

        if pad_c is not None:
            self.handle_diff(pad_t, pad_c, in_sig=from_pad)
        else:
            self.handle_single_ended(pad_t, in_sig=from_pad)

    def handle_io(self, cd_out, cd_in, out_sig, oe_sig, in_sig, pin, *, offset=None):
        pad_t, pad_c = self.get_pads(pin, offset=offset)
        prefix, _pin_func = ("", pin) if len(self.prefixes) == 1 else (pin[:2], pin[2:])

        if "dqs" in _pin_func and offset:
            offset *= self.dq_dqs_ratio//4

        inc_sig, rst_sig = None, None
        if self.with_odelay and pin in self.pin_csr_mapping:
            inc_sig, rst_sig = self.get_out_inc_rst(pin, offset=offset, cd="sys")

        to_pad, to_pad_oe, odelay_state = self.handle_oser(
            cd_out=cd_out, out_sig=out_sig, oe_sig=oe_sig, inc_sig=inc_sig, rst_sig=rst_sig)

        inc_sig, rst_sig = self.get_in_inc_rst(pin, offset=offset, cd="sys")
        from_pad, idelay_state = self.handle_iser(
            cd_in=cd_in, in_sig=in_sig, inc_sig=inc_sig, rst_sig=rst_sig)

        offset = offset if offset else 0
        if "dq" == _pin_func:
            if offset%4 == 0:
                self.sync += [
                    If(self.CSRs[prefix+'dly_sel'].storage[offset//4],
                        self.CSRs[prefix+'rdly_dq'].status.eq(idelay_state),
                    ),
                ]
                if self.with_odelay:
                    self.sync += [
                        If(self.CSRs[prefix+'dly_sel'].storage[offset//4],
                            self.CSRs[prefix+'wdly_dq'].status.eq(odelay_state),
                        ),
                    ]
        elif "dqs" in _pin_func:
            self.sync += [
                If(self.CSRs[prefix+'dly_sel'].storage[offset],
                    self.CSRs[prefix+'rdly_dqs'].status.eq(idelay_state),
                ),
            ]
            if self.with_odelay:
                self.sync += [
                    If(self.CSRs[prefix+'dly_sel'].storage[offset],
                        self.CSRs[prefix+'wdly_dqs'].status.eq(odelay_state),
                    ),
                ]

        if pad_c is not None:
            self.handle_diff(pad_t, pad_c, out_sig=to_pad, oe_sig=to_pad_oe, in_sig=from_pad)
        else:
            self.handle_single_ended(pad_t, out_sig=to_pad, oe_sig=to_pad_oe, in_sig=from_pad)

    def handle_ck(self, cd_out, pin, offset=None):
        clk_sig = Signal(4)
        self.comb += clk_sig.eq(self.clk_pattern&0xF)
        self.handle_o(cd_out=cd_out, out_sig=clk_sig, pin=pin, offset=offset)


# PHY variants -------------------------------------------------------------------------------------

class V7DDR5PHY(S7DDR5PHY):
    """Xilinx Virtex7 DDR5 PHY (with odelay)"""
    def __init__(self, pads, **kwargs):
        S7DDR5PHY.__init__(self, pads, with_odelay=True, **kwargs)

class K7DDR5PHY(S7DDR5PHY):
    """Xilinx Kintex7 DDR5 PHY (with odelay)"""
    def __init__(self, pads, **kwargs):
        S7DDR5PHY.__init__(self, pads, with_odelay=True, **kwargs)

class A7DDR5PHY(S7DDR5PHY):
    """Xilinx Artix7 DDR5 PHY (without odelay)

    This variant requires generating sys4x_90 clock in CRG with a 90° phase shift vs sys4x.
    """
    def __init__(self, pads, **kwargs):
        S7DDR5PHY.__init__(self, pads, with_odelay=False, **kwargs)
