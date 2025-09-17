#
# This file is part of LiteDRAM.
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2018 John Sully <john@csquare.ca>
# Copyright (c) 2018 bunnie <bunnie@kosagi.com>
# Copyright (c) 2020-2021 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import math
from functools import reduce
from operator import add
from collections import OrderedDict
from typing import Union, Optional

from migen import *
from migen import Signal
from migen.genlib.fifo import _FIFOInterface

from litex.soc.interconnect import stream

# Helpers ------------------------------------------------------------------------------------------

burst_lengths = {
    "SDR":    1,
    "DDR":    4,
    "LPDDR":  4,
    "DDR2":   4,
    "DDR3":   8,
    "RPC":    16,
    "DDR4":   8,
    "DDR5":   8,
    "LPDDR4": 16,
    "LPDDR5": 16,
}

def get_default_cl_cwl(memtype, tck):
    f_to_cl_cwl = OrderedDict()
    if memtype == "SDR":
        f_to_cl_cwl[100e6] = (2, None)
        f_to_cl_cwl[133e6] = (3, None)
    elif memtype == "DDR2":
        f_to_cl_cwl[400e6]  = (3, 2)
        f_to_cl_cwl[533e6]  = (4, 3)
        f_to_cl_cwl[677e6]  = (5, 4)
        f_to_cl_cwl[800e6]  = (6, 5)
        f_to_cl_cwl[1066e6] = (7, 5)
    elif memtype == "DDR3":
        f_to_cl_cwl[800e6]  = ( 6, 5)
        f_to_cl_cwl[1066e6] = ( 7, 6)
        f_to_cl_cwl[1333e6] = (10, 7)
        f_to_cl_cwl[1600e6] = (11, 8)
        f_to_cl_cwl[1866e6] = (13, 9)
    elif memtype == "DDR4":
        f_to_cl_cwl[1333e6] = (9,   9)
        f_to_cl_cwl[1600e6] = (11,  9)
        f_to_cl_cwl[1866e6] = (13, 10)
        f_to_cl_cwl[2133e6] = (15, 11)
        f_to_cl_cwl[2400e6] = (16, 12)
        f_to_cl_cwl[2666e6] = (18, 14)
    else:
        raise ValueError
    for f, (cl, cwl) in f_to_cl_cwl.items():
        m = 2 if "DDR" in memtype else 1
        if tck >= m/f:
            return cl, cwl
    raise ValueError

def get_default_cl(memtype, tck):
    cl, _ = get_default_cl_cwl(memtype, tck)
    return cl

def get_default_cwl(memtype, tck):
    _, cwl = get_default_cl_cwl(memtype, tck)
    return cwl

def get_sys_latency(nphases, cas_latency):
    return math.ceil(cas_latency/nphases)

def get_sys_phase(nphases, sys_latency, cas_latency):
    return sys_latency*nphases - cas_latency

# PHY Pads Transformers ----------------------------------------------------------------------------

class PHYPadsReducer:
    """PHY Pads Reducer

    Reduce DRAM pads to only use specific modules.

    For testing purposes, we often need to use only some of the DRAM modules. PHYPadsReducer allows
    selecting specific modules and avoid re-definining dram pins in the Platform for this.
    """
    def __init__(self, pads, modules, with_cat=False):
        self.pads     = pads
        self.modules  = modules
        self.with_cat = with_cat

    def __getattr__(self, name):
        if name in ["dq"]:
            r = Array([getattr(self.pads, name)[8*i + j]
                for i in self.modules
                for j in range(8)])
            return r if not self.with_cat else Cat(r)
        if name in ["dm", "dqs", "dqs_p", "dqs_n"]:
            r = Array([getattr(self.pads, name)[i] for i in self.modules])
            return r if not self.with_cat else Cat(r)
        else:
            return getattr(self.pads, name)

class PHYPadsCombiner:
    """PHY Pads Combiner

    Combine DRAM pads from fully dissociated chips in a unique DRAM pads structure.

    Most generally, DRAM chips are sharing command/address lines between chips (using a fly-by
    topology since DDR3). On some boards, the DRAM chips are using separate command/address lines
    and this combiner can be used to re-create a single pads structure (that will be compatible with
    LiteDRAM's PHYs) to create a single DRAM controller from multiple fully dissociated DRAMs chips.
    """
    def __init__(self, pads):
        if not isinstance(pads, list):
            self.groups = [pads]
        else:
            self.groups = pads
        self.sel = 0

    def sel_group(self, n):
        self.sel = n

    def __getattr__(self, name):
        if name in ["dm", "dq", "dqs", "dqs_p", "dqs_n"]:
            return Array([getattr(self.groups[j], name)[i]
                for i in range(len(getattr(self.groups[0], name)))
                for j in range(len(self.groups))])
        else:
            return getattr(self.groups[self.sel], name)

# BitSlip ------------------------------------------------------------------------------------------

class BitSlip(Module):
    def __init__(self, dw, i=None, o=None, rst=None, slp=None, cycles=1):
        self.i   = Signal(dw) if i is None else i
        self.o   = Signal(dw) if o is None else o
        self.rst = Signal()   if rst is None else rst
        self.slp = Signal()   if slp is None else slp
        assert cycles >= 1

        # # #

        value = Signal(max=cycles*dw, reset=cycles*dw-1)
        self.sync += If(self.slp, value.eq(value - 1))
        self.sync += If(self.rst, value.eq(value.reset))

        r = Signal((cycles+1)*dw, reset_less=True)
        self.sync += r.eq(Cat(r[dw:], self.i))
        cases = {}
        for i in range(cycles*dw):
            cases[i] = self.o.eq(r[i+1:dw+i+1])
        self.comb += Case(value, cases)

class BitSlipInv(Module):
    def __init__(self, dw, i=None, o=None, rst=None, slp=None, cycles=1):
        self.i   = Signal(dw) if i is None else i
        self.o   = Signal(dw) if o is None else o
        self.rst = Signal()   if rst is None else rst
        self.slp = Signal()   if slp is None else slp
        assert cycles >= 1

        # # #

        value = Signal(max=cycles*dw, reset=0)
        self.sync += If(self.slp, value.eq(value + 1))
        self.sync += If(self.rst, value.eq(value.reset))

        r = Signal((cycles+1)*dw, reset_less=True)
        self.sync += r.eq(Cat(r[dw:], self.i))
        cases = {}
        for i in range(cycles*dw):
            cases[i] = self.o.eq(r[i+1:dw+i+1])
        self.comb += Case(value, cases)

# TappedDelayLine ----------------------------------------------------------------------------------

class TappedDelayLine(Module):
    def __init__(self, signal=None, ntaps=1):
        self.input = Signal() if signal is None else signal
        self.taps  = Array(Signal.like(self.input) for i in range(ntaps))
        for i in range(ntaps):
            self.sync += self.taps[i].eq(self.input if i == 0 else self.taps[i-1])
        self.output = self.taps[-1]

# SimplerFIFO --------------------------------------------------------------------------------------

class SimpleSyncFIFO(Module, _FIFOInterface):
    def __init__(self, width, depth, fwft=True):
        _FIFOInterface.__init__(self, width, depth)

        cnt_bits = (depth-1).bit_length()

        w_cnt = Signal(cnt_bits+1)
        r_cnt = Signal(cnt_bits+1)
        ###

        produce = Signal(max=depth)
        consume = Signal(max=depth)
        storage = Memory(self.width, 2**cnt_bits)
        self.specials += storage

        wrport = storage.get_port(write_capable=True, has_re=True, mode=READ_FIRST)
        self.specials += wrport
        self.comb += [
            wrport.adr.eq(w_cnt),
            wrport.dat_w.eq(self.din),
            wrport.we.eq(self.we & self.writable),
            wrport.re.eq(0),
        ]
        self.sync += If(self.we & self.writable,
            w_cnt.eq(w_cnt+1))

        do_read = Signal()
        self.comb += do_read.eq(self.readable & self.re)

        rdport = storage.get_port(async_read=fwft, has_re=not fwft, mode=READ_FIRST)
        self.specials += rdport
        self.comb += [
            rdport.adr.eq(r_cnt),
            self.dout.eq(rdport.dat_r)
        ]
        if not fwft:
            self.comb += rdport.re.eq(do_read)
        self.sync += If(do_read, r_cnt.eq(r_cnt+1))

        half_way = Signal()
        self.comb += half_way.eq(w_cnt[:-1] == r_cnt[:-1])

        self.comb += [
            self.writable.eq(~(half_way & (w_cnt[-1] != r_cnt[-1]))),
            self.readable.eq(~(half_way & (w_cnt[-1] == r_cnt[-1]))),
        ]


# ShiftRegister ------------------------------------------------------------------------------------

class ShiftRegister(Module):
    class _Proxy():
        def __init__(self, parent):
            self.parent = parent

        def __getitem__(self, key):
            length = self.parent.ntaps
            width  = self.parent.width
            sr     = self.parent.shift_window
            if isinstance(key, int):
                if key > length:
                    raise IndexError
                if key < 0:
                    key += length
                return Cat([sr[i][key] for i in range(width)])
            elif isinstance(key, Signal):
                return Cat([sr[i].part(key, 1) for i in range(width)])
            else:
                raise TypeError("Cannot use type {} ({}) as key".format(
                    type(key), repr(key)))


    def __init__(self, signal=None, ntaps=1):
        self.input = Signal() if signal is None else signal
        self.ntaps = ntaps
        self.width = width = len(self.input)

        self.shift_window = shift_window = \
            [Signal(ntaps, reset_less=True) for _ in range(width)]
        for i in range(width):
            self.sync += shift_window[i].eq(Cat(self.input[i], shift_window[i]))

        rst_cnt                  = Signal(max=ntaps+1, reset=ntaps)
        self.rst_done = rst_done = Signal()
        self.sync += [
            If(~rst_done,
                rst_cnt.eq(rst_cnt - 1),
            ),
            If(rst_cnt == 0,
                rst_done.eq(1)
            )
        ]

        self.taps = ShiftRegister._Proxy(self)
        self.output = Cat([shift_window[i][-1] for _ in range(width)])

# DQS Pattern --------------------------------------------------------------------------------------

class DQSPattern(Module):
    def __init__(self, preamble=None, postamble=None, wlevel_en=0, wlevel_strobe=0, register=False):
        self.preamble  = Signal() if preamble  is None else preamble
        self.postamble = Signal() if postamble is None else postamble
        self.o = Signal(8)

        # # #

        # DQS Pattern transmitted as LSB-first.

        self.comb += [
            self.o.eq(0b01010101),
            If(self.preamble,
                self.o.eq(0b00010101)
            ),
            If(self.postamble,
                self.o.eq(0b01010100)
            ),
            If(wlevel_en,
                self.o.eq(0b00000000),
                If(wlevel_strobe,
                    self.o.eq(0b00000001)
                )
            )
        ]
        if register:
            o = Signal.like(self.o)
            self.sync += o.eq(self.o)
            self.o = o

# Settings -----------------------------------------------------------------------------------------

class Settings:
    def set_attributes(self, attributes):
        for k, v in attributes.items():
            setattr(self, k, v)


class PhySettings(Settings):
    def __init__(self,
            phytype: str,
            memtype: str,  # SDR, DDR, DDR2, ...
            databits: int,  # number of DQ lines
            dfi_databits: int,  # per-phase DFI data width
            nphases: int,  # number of DFI phases
            rdphase: Union[int, Signal],  # phase on which READ command will be issued by MC
            wrphase: Union[int, Signal],  # phase on which WRITE command will be issued by MC
            cl: int,  # latency (DRAM clk) from READ command to first data
            read_latency: int,  # latency (MC clk) from DFI.rddata_en to DFI.rddata_valid
            write_latency: int,  # latency (MC clk) from DFI.wrdata_en to DFI.wrdata
            strobes: Optional[int] = None,  # number of DQS lines
            nranks: int = 1,  # number of DRAM ranks
            cwl: Optional[int] = None,  # latency (DRAM clk) from WRITE command to first data
            cmd_latency: Optional[int] = None,  # additional command latency (MC clk)
            cmd_delay: Optional[int] = None,  # used to force cmd delay during initialization in BIOS
            bitslips: int = 0,  # number of write/read bitslip taps
            delays: int = 0,  # number of write/read delay taps
            masked_write: bool = False, # can masked writes
            with_alert: bool = False, # phy has CSRs for reading and reseting alert condition
            # Minimal delay between data being send to phy and them showing on DQ lines
            # If CLW is delay from write command to data on DQ, SW should add CLW-min_write_latency delay cycles
            min_write_latency: int = 0,
            # Minimal delay between read command being send and DQ lines being captured
            # If CL is delay from read command to data on DQ, SW should add CL-min_read_latency delay cycles
            min_read_latency: int = 0,
            # PHY training capabilities
            write_leveling: bool = False,
            write_dq_dqs_training: bool = False,
            write_latency_calibration: bool = False,
            read_leveling: bool = False,
            with_sub_channels: bool = False,
            # DDR5 specific
            nibbles: Optional[int] = None, # Number of data nibbles
            address_lines: int = 13,
            with_per_dq_idelay: bool = False,
            with_address_odelay: bool = False, # Concrete PHY has ODELAYs on all address lines
            with_clock_odelay: bool = False, # Concrete PHY has ODELAYs on clk lines
            with_odelay: bool = False, # Concrete PHY has ODELAYs on all lines: CLK, CS/CA, DQ/DQS
            with_idelay: bool = False, # Concrete PHY has IDELAYs on DQ/DQS lines
            direct_control: bool = False,
            # DFI timings
            t_ctrl_delay: int = 0,  # Time from the DFI command to its appearance on DRAM bus
            t_parin_lat: int = 0,   # Time from the DFI command to its parity
            t_cmd_lat: int = 0,     # Time from the CS to DFI command
            t_phy_wrdata: int  = 0, # Time from the wrdata_en to wrdata an wrdata_mask
            t_phy_wrlat: int = 0,   # Time from the DFI Write command to wrdata_en
            t_phy_wrcsgap: int = 0, # Additional delay when changing physical ranks (wrdata_cs/cs)
            t_phy_wrcslat: int = 0, # Time from the DFI Write command to wrdata_cs
            t_phy_rdlat: int = 0,   # Max delay from the DFI rddata_en to rddata_valid
            t_rddata_en: int = 0,   # Time from the DFI Read command to rddata_en
            t_phy_rdcsgap: int  = 0,# Additional delay when changing physical ranks (rddata_cs/cs)
            t_phy_rdcslat: int = 0, # Time from the DFI Write command to rddata_cs
            # system values
            soc_freq: Optional[int] = None,
        ):
        if strobes is None:
            strobes = databits // 8
        self.set_attributes(locals())
        self.cwl = cl if cwl is None else cwl
        self.is_rdimm = False

    # Optional DDR3/DDR4 electrical settings:
    # rtt_nom: Non-Writes on-die termination impedance
    # rtt_wr: Writes on-die termination impedance
    # ron: Output driver impedance
    # tdqs: Termination Data Strobe enable.
    def add_electrical_settings(self, rtt_nom=None, rtt_wr=None, ron=None, tdqs=None):
        assert self.memtype in ["DDR3", "DDR4"]
        if rtt_nom is not None:
            self.rtt = rtt_nom
        if rtt_wr is not None:
            self.rtt_wr = rtt_wr
        if ron is not None:
            self.ron = ron
        if tdqs is not None:
            self.tdqs = tdqs

    # Optional RDIMM configuration
    def set_rdimm(self, tck, rcd_pll_bypass, rcd_ca_cs_drive, rcd_odt_cke_drive, rcd_clk_drive):
        assert self.memtype == "DDR4"
        self.is_rdimm = True
        self.set_attributes(locals())

class GeomSettings(Settings):
    def __init__(self, bankbits, rowbits, colbits):
        self.set_attributes(locals())
        self.addressbits = max(rowbits, colbits)


class TimingSettings(Settings):
    def __init__(self, tRP, tRCD, tWR, tWTR, tREFI, tRFC, tFAW, tCCD, tCCD_WR, tRTP, tRRD, tRC, tRAS, tZQCS):
        self.set_attributes(locals())

# Layouts/Interface --------------------------------------------------------------------------------

def cmd_layout(address_width):
    return [
        ("valid",            1, DIR_M_TO_S),
        ("ready",            1, DIR_S_TO_M),
        ("we",               1, DIR_M_TO_S),
        ("addr", address_width, DIR_M_TO_S),
        ("lock",             1, DIR_S_TO_M), # only used internally

        ("wdata_ready",      1, DIR_S_TO_M),
        ("rdata_valid",      1, DIR_S_TO_M)
    ]

def data_layout(data_width):
    return [
        ("wdata",       data_width, DIR_M_TO_S),
        ("wdata_we", data_width//8, DIR_M_TO_S),
        ("rdata",       data_width, DIR_S_TO_M)
    ]

def cmd_request_layout(a, ba):
    return [
        ("a",     a),
        ("ba",   ba),
        ("cas",   1),
        ("ras",   1),
        ("we",    1)
    ]

def cmd_request_rw_layout(a, ba):
    return cmd_request_layout(a, ba) + [
        ("is_cmd", 1),
        ("is_read", 1),
        ("is_write", 1)
    ]


class LiteDRAMInterface(Record):
    def __init__(self, address_align, settings):
        rankbits = log2_int(settings.phy.nranks)
        self.address_align = address_align
        self.address_width = settings.geom.rowbits + settings.geom.colbits + rankbits - address_align
        self.data_width    = settings.phy.dfi_databits*settings.phy.nphases
        self.nbanks   = settings.phy.nranks*(2**settings.geom.bankbits)
        self.nranks   = settings.phy.nranks
        self.settings = settings

        layout = [("bank"+str(i), cmd_layout(self.address_width)) for i in range(self.nbanks)]
        layout += data_layout(self.data_width)
        Record.__init__(self, layout)

# Ports --------------------------------------------------------------------------------------------

def cmd_description(address_width):
    return [
        ("we",               1), # Write (1) or Read (0).
        ("addr", address_width)  # Address (in Controller's words).
    ]

def wdata_description(data_width):
    return [
        ("data",    data_width), # Write Data.
        ("we",   data_width//8), # Write Data byte enable.
    ]

def rdata_description(data_width):
    return [("data", data_width)] # Read Data.

class LiteDRAMNativePort(Settings):
    def __init__(self, mode, address_width, data_width, clock_domain="sys", id=0):
        self.set_attributes(locals())

        self.flush = Signal()
        self.lock  = Signal()

        self.cmd   = stream.Endpoint(cmd_description(address_width))
        self.wdata = stream.Endpoint(wdata_description(data_width))
        self.rdata = stream.Endpoint(rdata_description(data_width))

        # retro-compatibility # FIXME: remove
        self.aw = self.address_width
        self.dw = self.data_width
        self.cd = self.clock_domain

    def get_bank_address(self, bank_bits, ba_shift):
        ba_upper = ba_shift + bank_bits
        return self.cmd.addr[ba_shift:ba_upper]

    def get_row_column_address(self, bank_bits, rca_bits, cba_shift):
        cba_upper = cba_shift + bank_bits
        if cba_shift < rca_bits:
            if cba_shift:
                return Cat(self.cmd.addr[:cba_shift], self.cmd.addr[cba_upper:])
            else:
                return self.cmd.addr[cba_upper:]
        else:
            return self.cmd.addr[:cba_shift]

    def connect(self, port):
        return [
            self.cmd.connect(port.cmd),
            self.wdata.connect(port.wdata),
            port.rdata.connect(self.rdata),
            port.flush.eq(self.flush),
            self.lock.eq(port.lock),
        ]

class LiteDRAMNativeWritePort(LiteDRAMNativePort):
    def __init__(self, *args, **kwargs):
        LiteDRAMNativePort.__init__(self, "write", *args, **kwargs)


class LiteDRAMNativeReadPort(LiteDRAMNativePort):
    def __init__(self, *args, **kwargs):
        LiteDRAMNativePort.__init__(self, "read", *args, **kwargs)


# Timing Controllers -------------------------------------------------------------------------------

class tXXDController(Module):
    def __init__(self, txxd):
        self.valid = valid = Signal()
        self.ready = ready = Signal(reset=1)
        ready.attr.add("no_retiming")

        # # #

        if txxd is not None:
            count = Signal.like(txxd)
            self.sync += \
                If(valid,
                    count.eq(txxd - 1),
                    ready.eq(txxd <= 1),
                ).Elif(~ready,
                    count.eq(count - 1),
                    If(count == 1,
                        ready.eq(1)
                    )
                )


class tFAWController(Module):
    # Four active window controller
    # It requires 2**tfaw.nbits cycles after reset to work
    def __init__(self, tfaw):
        self.valid = valid = Signal()
        self.ready = ready = Signal(reset=1)
        ready.attr.add("no_retiming")

        # # #

        # TODO: base count only on incoming and outgoing bits from the shift register

        if tfaw is not None:
            count  = Signal(3)
            access = Signal.like(tfaw)
            self.sync += access.eq(tfaw-2)

            handshake = Signal()
            self.comb += handshake.eq(valid & ready)

            sr = ShiftRegister(ntaps=2**tfaw.nbits, signal=handshake)
            self.submodules.shift_register = sr

            tfaw_range_last_bit = Signal()
            tfaw_range_almost_last_bit = Signal()
            self.comb += tfaw_range_almost_last_bit.eq(sr.taps[access])
            self.sync += tfaw_range_last_bit.eq(tfaw_range_almost_last_bit)
            self.sync += ready.eq(
                (
                    (count[2] & (tfaw_range_almost_last_bit | tfaw_range_last_bit)) | \
                    ((count[0:2] == 3) & handshake & tfaw_range_last_bit) | \
                    ((count[0:2] == 3) & ~handshake) | \
                    (~count[2] & ~(count[0:2] == 3))
                ) & sr.rst_done)

            self.sync += [
                If(tfaw_range_last_bit & ~handshake,
                    count.eq(count - 1),
                ).Elif(~tfaw_range_last_bit & handshake,
                    count.eq(count + 1),
                ),
                If(~sr.rst_done,
                    count.eq(0),
                ),
            ]


class TimelineCounter(Module):
    def __init__(self, width):
        self.counter = Signal(width)
        self.target = Signal(self.counter.nbits)
        self.trigger = Signal()

        self.sync += [
            If(self.counter != 0,
                self.counter.eq(self.counter + 1)
            ).Elif(self.trigger,
                self.counter.eq(1)
            ),
            If(self.counter == self.target,
                self.counter.eq(0)
            ),
        ]
