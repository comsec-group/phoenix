#
# This file is part of LiteDRAM.
#
# Copyright (c) 2021 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import re

from migen import *
from migen.genlib.fifo import _FIFOInterface

from litex.build.sim import SimPlatform
from litex.build.sim.config import SimConfig
from litex.build.generic_platform import Pins, Subsignal
from litex.soc.interconnect.csr import CSRStorage, AutoCSR

from litedram.common import Settings, tXXDController, SimpleSyncFIFO
from litedram.phy.utils import Serializer, Deserializer, edge

from operator import or_, and_
from functools import reduce

# PHY ----------------------------------------------------------------------------------------------

class SimSerDesMixin:
    """Helper class for easier (de-)serialization to simulation pads."""
    def ser(self, *, i, o, clkdiv, clk, name="", **kwargs):
        assert len(o) == 1
        kwargs = dict(i=i, i_dw=len(i), o=o, o_dw=1, clk=clk, clkdiv=clkdiv,
            name=f"ser_{name}".strip("_"), **kwargs)
        self.submodules += Serializer(**kwargs)

    def des(self, *, i, o, clkdiv, clk, name="", **kwargs):
        assert len(i) == 1
        kwargs = dict(i=i, i_dw=1, o=o, o_dw=len(o), clk=clk, clkdiv=clkdiv,
            name=f"des_{name}".strip("_"), **kwargs)
        self.submodules += Deserializer(**kwargs)

# Platform -----------------------------------------------------------------------------------------

class SimPad(Settings):
    def __init__(self, name, width, io=False, granularity=-1):
        self.set_attributes(locals())


class SimulationPads(Module):
    """Pads for simulation purpose

    Tristate pads are simulated as separate input/output pins (name_i, name_o) and
    an output-enable pin (name_oe). Output pins are to be driven byt the PHY and
    input pins are to be driven by the DRAM simulator. An additional pin without
    a suffix is created and this module will include logic to set this pin to the
    actual value depending on the output-enable signal.
    """
    def layout(self, **kwargs):
        raise NotImplementedError("Simulation pads layout as a list of SimPad objects")

    def __init__(self, **kwargs):
        for pad  in self.layout(**kwargs):
            if pad.width == 0:
                continue
            if pad.io:
                o, i, oe = (f"{pad.name}_{suffix}" for suffix in ["o", "i", "oe"])
                setattr(self, pad.name, Signal(pad.width))
                setattr(self, o, Signal(pad.width, name=o))
                setattr(self, i, Signal(pad.width, name=i))
                if pad.granularity == -1:
                    setattr(self, oe, Signal(name=oe))
                    self.comb += If(getattr(self, oe),
                        getattr(self, pad.name).eq(getattr(self, o))
                    ).Else(
                        getattr(self, pad.name).eq(getattr(self, i))
                    )
                else:
                    gran = pad.granularity
                    width = pad.width
                    assert width % gran == 0, "granularity must divide width"
                    setattr(self, oe, Signal(width//gran, name=oe))
                    for it in range(width//gran):
                        start, stop = (it*gran, (it+1)*gran)
                        self.comb += [If(getattr(self, oe)[it],
                            getattr(self, pad.name)[start:stop].eq(getattr(self, o)[start:stop])
                        ).Else(
                            getattr(self, pad.name)[start:stop].eq(getattr(self, i)[start:stop])
                        )]
            else:
                setattr(self, pad.name, Signal(pad.width, name=pad.name))


class Clocks(dict):
    """Helper for definiting simulation clocks

    Dictionary format is `{name: {"freq_hz": _, "phase_deg": _}, ...}`.
    """
    def names(self):
        return list(self.keys())

    def add_io(self, io):
        for name in self.names():
            io.append((name + "_clk", 0, Pins(1)))

    def add_clockers(self, sim_config):
        for name, desc in self.items():
            sim_config.add_clocker(name + "_clk", **desc)


class CRG(Module):
    """Clock & Reset Generator for Verilator-based simulation"""
    def __init__(self, platform, clock_domains=None):
        if clock_domains is None:
            clock_domains = ["sys"]
        elif isinstance(clock_domains, Clocks):
            clock_domains = list(clock_domains.names())

        # request() before creating clock_domains to avoid signal renaming problem
        clock_domains = {name: platform.request(name + "_clk") for name in clock_domains}

        self.clock_domains.cd_por = ClockDomain(reset_less=True)
        for name in clock_domains.keys():
            setattr(self.clock_domains, "cd_" + name, ClockDomain(name=name))

        int_rst = Signal(reset=1)
        self.sync.por += int_rst.eq(0)
        self.comb += self.cd_por.clk.eq(self.cd_sys.clk)

        for name, clk in clock_domains.items():
            cd = getattr(self, "cd_" + name)
            self.comb += cd.clk.eq(clk)
            self.comb += cd.rst.eq(int_rst)


class Platform(SimPlatform):
    def __init__(self, io, clocks: Clocks):
        common_io = [
            ("sys_rst", 0, Pins(1)),

            ("serial", 0,
                Subsignal("source_valid", Pins(1)),
                Subsignal("source_ready", Pins(1)),
                Subsignal("source_data",  Pins(8)),
                Subsignal("sink_valid",   Pins(1)),
                Subsignal("sink_ready",   Pins(1)),
                Subsignal("sink_data",    Pins(8)),
            ),
        ]
        clocks.add_io(common_io)
        SimPlatform.__init__(self, "SIM", common_io + io)

# Logging ------------------------------------------------------------------------------------------

# Named regex group
def ng(name, regex):
    return r"(?P<{}>{})".format(name, regex)


class SimLogger(Module, AutoCSR):
    """Logger for use in simulation

    This module allows for easier message logging when running simulation designs.
    The logger can be used from `comb` context so it the methods can be directly
    used inside `FSM` code. It also provides logging levels that can be used to
    filter messages, either by specifying the default `log_level` or in runtime
    by driving to the `level` signal or using a corresponding CSR.

    If `clk_freq` is provided, than the logger will prepend timestamps to the
    messages (in picoseconds). This will work as long as the clock domain in which
    this module operates is always running with a constant frequency. On the other
    hand, if the frequency varies or the clock is sometimes disabled, `clk_freq_cd`
    can be specified to select a different clock domain (`clk_freq` must specify
    the frequecy of that new clock domain).
    """
    # Allows to use Display inside FSM and to filter log messages by level (statically or dynamically)
    DEBUG = 0
    INFO  = 1
    WARN  = 2
    ERROR = 3
    NONE  = 4

    # Regex pattern for parsing logs
    LOG_PATTERN = re.compile(r"\[\s*{time} ps] \[{level}]\s*{msg}".format(
        time  = ng("time", r"[0-9]+"),
        level = ng("level", r"DEBUG|INFO|WARN|ERROR"),
        msg   = ng("msg", ".*"),
    ))

    def __init__(self, log_level=INFO, clk_freq=None, clk_freq_cd=None, with_csrs=False):
        self.ops = []
        self.level = Signal(reset=log_level, max=self.NONE + 1)
        self.time_ps = None
        if clk_freq is not None:
            self.time_ps = Signal(64)
            cnt = Signal(64)
            sd_cnt = self.sync if clk_freq_cd is None else getattr(self.sync, clk_freq_cd)
            sd_cnt += cnt.eq(cnt + 1)
            self.comb += self.time_ps.eq(cnt * int(1e12/clk_freq))
        if with_csrs:
            self.add_csrs()

    def debug(self, fmt, *args, **kwargs):
        return self.log("[DEBUG] " + fmt, *args, level=self.DEBUG, **kwargs)

    def info(self, fmt, *args, **kwargs):
        return self.log("[INFO] " + fmt, *args, level=self.INFO, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        return self.log("[WARN] " + fmt, *args, level=self.WARN, **kwargs)

    def error(self, fmt, *args, **kwargs):
        return self.log("[ERROR] " + fmt, *args, level=self.ERROR, **kwargs)

    def log(self, fmt, *args, level=DEBUG, once=True):
        cond = Signal()
        if once:  # make the condition be triggered only on rising edge
            condition = edge(self, cond)
        else:
            condition = cond

        self.ops.append((level, condition, fmt, args))
        return cond.eq(1)

    def add_csrs(self):
        self._level = CSRStorage(len(self.level), reset=self.level.reset.value)
        self.comb += self.level.eq(self._level.storage)

    def do_finalize(self):
        for level, cond, fmt, args in self.ops:
            if self.time_ps is not None:
                fmt = f"[%16d ps] {fmt}"
                args = (self.time_ps, *args)
            self.sync += If((level >= self.level) & cond, Display(fmt, *args))

class SimLoggerComb(Module, AutoCSR):
    """Logger for use in simulation

    This module allows for easier message logging when running simulation designs.
    The logger can be used from `comb` context so it the methods can be directly
    used inside `FSM` code. It also provides logging levels that can be used to
    filter messages, either by specifying the default `log_level` or in runtime
    by driving to the `level` signal or using a corresponding CSR.
    """
    # Allows to use Display inside FSM and to filter log messages by level (statically or dynamically)
    DEBUG = 0
    INFO  = 1
    WARN  = 2
    ERROR = 3
    NONE  = 4

    # Regex pattern for parsing logs
    LOG_PATTERN = re.compile(r"\[\s*{time} ps] \[{level}]\s*{msg}".format(
        time  = ng("time", r"[0-9]+"),
        level = ng("level", r"DEBUG|INFO|WARN|ERROR"),
        msg   = ng("msg", ".*"),
    ))

    def __init__(self, log_level=INFO, use_time=False, with_csrs=False):
        self.ops = []
        self.level = Signal(reset=log_level, max=self.NONE + 1)
        self.use_time = use_time
        if with_csrs:
            self.add_csrs()

    def debug(self, fmt, *args, **kwargs):
        return self.log("[DEBUG] " + fmt, *args, level=self.DEBUG, **kwargs)

    def info(self, fmt, *args, **kwargs):
        return self.log("[INFO] " + fmt, *args, level=self.INFO, **kwargs)

    def warn(self, fmt, *args, **kwargs):
        return self.log("[WARN] " + fmt, *args, level=self.WARN, **kwargs)

    def error(self, fmt, *args, **kwargs):
        return self.log("[ERROR] " + fmt, *args, level=self.ERROR, **kwargs)

    def log(self, fmt, *args, level=DEBUG, once=True):
        cond = Signal()
        if once:  # make the condition be triggered only on rising edge
            condition = edge(self, cond)
        else:
            condition = cond

        self.ops.append((level, condition, fmt, args))
        return cond.eq(1)

    def add_csrs(self):
        self._level = CSRStorage(len(self.level), reset=self.level.reset.value)
        self.comb += self.level.eq(self._level.storage)

    def do_finalize(self):
        for level, cond, fmt, args in self.ops:
            if self.use_time:
                fmt = f"[%0t %s] {fmt}\", $time/1000, \"ps"
            self.comb += If((level >= self.level) & cond, Display(fmt, *args))

def log_level_getter(log_level):
    """Parse logging level description

    Log level can be presented in a simple form (e.g. `--log-level=DEBUG`) to specify
    the same level for all modules, or can set different levels for different modules
    e.g. `--log-level=all=INFO,data=DEBUG`.
    """
    def get_level(name):
        return getattr(SimLogger, name.upper())

    if "=" not in log_level:  # simple log_level, e.g. "INFO"
        return lambda _: get_level(log_level)

    # parse log_level in the per-module form, e.g. "--log-level=all=INFO,data=DEBUG"
    per_module = dict(part.split("=") for part in log_level.strip().split(","))
    return lambda module: get_level(per_module.get(module, per_module.get("all", None)))

# Simulator ----------------------------------------------------------------------------------------

class Timing(Module):
    # slight modification of tXXDController
    def __init__(self, t):
        self.valid = Signal()
        self.ready = Signal()

        if t is None:
            t = 0

        if isinstance(t, Signal):
            count = Signal.like(t)
        else:
            count = Signal(max=max(t, 2))

        self._t = t
        self._count = count

        ready = Signal()
        ready_reg = Signal()
        self.comb += [
            self.ready.eq(ready_reg | ready),
            ready.eq((t == 0) & self.valid),
        ]

        self.sync += \
            If(self.valid,
                If(t == 0,
                    ready_reg.eq(1)
                ).Else(
                    count.eq(t - 1),
                    If(t == 1,
                        ready_reg.eq(1)
                    ).Else(
                        ready_reg.eq(0)
                    )
                ),
            ).Elif(~ready,
                If(count > 1,
                    count.eq(count - 1),
                ),
                If(count == 1,
                    ready_reg.eq(1)
                )
            )

    def progress(self):
        full = self._t
        current = Signal.like(self._count)
        self.comb += current.eq(full - self._count)  # down-counting
        return (current, full)

class PulseTiming(Module):
    """Timing monitor with pulse input/output

    This module works like `tXXDController` with the following differences:

    * countdown triggered by a low to high pulse on `trigger`
    * `ready` is initially low, only after a trigger it can become high
    * provides `ready_p` which is high only for 1 cycle when `ready` becomes high
    * supports t values starting from 0, with t=0 `ready_p` will pulse in the same
      cycle in which `trigger` is high
    """
    def __init__(self, t):
        self.trigger = Signal()
        self.ready   = Signal()
        self.ready_p = Signal()

        trigger_d = Signal()
        triggered = Signal()
        self.submodules.timing = timing = Timing(t)

        self.sync += [
            If(self.trigger, triggered.eq(1)),
            trigger_d.eq(self.trigger),
        ]
        self.comb += [
            self.ready.eq((triggered & timing.ready) | ((t == 0) & self.trigger)),
            self.ready_p.eq(reduce(or_, [
                edge(self, self.ready),
                (t == 0) & edge(self, self.trigger),
                (t == 1) & edge(self, trigger_d),
            ])),
            timing.valid.eq(edge(self, self.trigger)),
        ]

    def progress(self):
        return self.timing.progress()

# CDCs

class SimpleCDC(Module):
    LATENCY=1
    register=False

    @classmethod
    def set_register(cls):
        cls.LATENCY=2
        cls.register = True

    def __init__(self, clkdiv, clk, i_dw, o_dw, *,
                    i=None, o=None, name=None, outside_reset_n=None):

        sd_clk = getattr(self.sync, clk)
        sd_clkdiv = getattr(self.sync, clkdiv)

        assert i_dw == 2*o_dw

        if i is None: i = Signal(i_dw)
        if o is None: o = Signal(o_dw)
        self.i = i
        self.o = o

        w_cnt = Signal(name='{}_w_cnt'.format(name) if name is not None else None)

        self.r_ready = r_ready = Signal(name='{}_r_ready'.format(name) if name is not None else None)
        r_row_cnt = Signal(name='{}_r_row_cnt'.format(name) if name is not None else None)
        r_col_cnt = Signal(name='{}_r_col_cnt'.format(name) if name is not None else None)

        self.i_d = i_d = Array([Signal.like(i), Signal.like(i)], name='{}_i_d'.format(name) if name is not None else None)
        reset_n = Signal(name='{}_reset_n'.format(name) if name is not None else None)

        if outside_reset_n is None:
            sd_clkdiv += [reset_n.eq(1)]
        else:
            sd_clkdiv += [reset_n.eq(outside_reset_n & ~w_cnt)]

        sd_clkdiv += [
            If(w_cnt,
                w_cnt.eq(0),
            ).Else(
                w_cnt.eq(1),
            ),
            i_d[w_cnt].eq(i),
        ]

        sd_clk += [
            If(reset_n,
                r_ready.eq(1),
            ),
            If(r_ready,
                If(r_col_cnt,
                    r_row_cnt.eq(r_row_cnt + 1),
                ),
                r_col_cnt.eq(r_col_cnt + 1),
            )
        ]

        self.o_array = o_array = Array([
            Array([i_d[0][0:o_dw], i_d[0][o_dw:]]),
            Array([i_d[1][0:o_dw], i_d[1][o_dw:]])
        ])
        if not self.register:
            self.comb += If(r_ready, o.eq(o_array[r_row_cnt][r_col_cnt]))
        else:
            sd_clk += If(r_ready, o.eq(o_array[r_row_cnt][r_col_cnt]))


class SimpleCDCr(Module):
    LATENCY=1
    register=False
    aligned=False

    @classmethod
    def set_aligned(cls):
        cls.aligned=True
        cls.LATENCY=2
        if cls.register:
            cls.LATENCY=3

    @classmethod
    def set_register(cls):
        cls.LATENCY=2
        cls.register = True
        if cls.aligned:
            cls.LATENCY=3

    def __init__(self, clkdiv, clk, i_dw, o_dw, *,
                    i=None, o=None, name=None, outside_reset_n=None):

        sd_clk = getattr(self.sync, clk)
        sd_clkdiv = getattr(self.sync, clkdiv)

        assert 2*i_dw == o_dw

        if i is None: i = Signal(i_dw)
        if o is None: o = Signal(o_dw)
        self.i = i
        self.o = o
        reset_n = Signal(name='{}_reset_n'.format(name) if name is not None else None)
        r_cnt = Signal(name='{}_w_cnt'.format(name) if name is not None else None)
        self.r_ready = r_ready = Signal(name='{}_r_ready'.format(name) if name is not None else None)
        w_row_cnt = Signal(name='{}_r_row_cnt'.format(name) if name is not None else None)
        w_col_cnt = Signal(name='{}_r_col_cnt'.format(name) if name is not None else None)
        self.i_d = i_d = Array([Array([Signal.like(i) for _ in range(2)]) for _ in range(2)],
                                name='{}_i_d'.format(name) if name is not None else None)

        if outside_reset_n is None:
            reset_n = Signal(name='{}_reset_n'.format(name) if name is not None else None)
            sd_clkdiv += [
                reset_n.eq(1),
            ]
        else:
            reset_n = outside_reset_n

        sd_clkdiv += [
            If(reset_n,
                r_ready.eq(1),
            ),
            If(r_ready,
                If(r_cnt,
                    r_cnt.eq(0),
                ).Else(
                    r_cnt.eq(1),
                ),
            ),
        ]

        sd_clk += [
            If(reset_n,
                If(w_col_cnt,
                    w_row_cnt.eq(w_row_cnt + 1),
                ),
                w_col_cnt.eq(w_col_cnt + 1),
                i_d[w_row_cnt][w_col_cnt].eq(i),
            )
        ]

        self.o_array = o_array = Array([
            Cat(i_d[0]),
            Cat(i_d[1]),
        ])
        if not self.register:
            self.comb += If(r_ready, o.eq(o_array[r_cnt]))
        else:
            sd_clkdiv += If(r_ready, o.eq(o_array[r_cnt]))


class SimpleCDCWrap(Module, _FIFOInterface):
    LATENCY = SimpleCDC.LATENCY + 2

    @classmethod
    def reset_latency(cls):
        cls.LATENCY=SimpleCDC.LATENCY + 2

    def __init__(self, clkdiv, clk, i_dw, o_dw, name=None):
        _FIFOInterface.__init__(self, i_dw, 32)
        cross = SimpleCDC(clkdiv, clk, i_dw+2, o_dw+1, name=name, outside_reset_n=self.we)
        self.submodules += cross
        _fifo = SimpleSyncFIFO(o_dw, 2, fwft=False)
        self.submodules += ClockDomainsRenamer(clk)(_fifo)
        self.comb += [
            cross.i.eq(Cat(self.din[:i_dw//2], self.we, self.din[i_dw//2:], self.we)),
            _fifo.din.eq(cross.o[:-1]),
            _fifo.we.eq(cross.o[-1]),
            self.dout.eq(_fifo.dout),
            _fifo.re.eq(self.re),
            self.readable.eq(_fifo.readable),
        ]


class SimpleCDCrWrap(Module, _FIFOInterface):
    LATENCY = SimpleCDCr.LATENCY + 1

    @classmethod
    def reset_latency(cls):
        cls.LATENCY=SimpleCDCr.LATENCY + 1

    def __init__(self, clkdiv, clk, i_dw, o_dw, name=None):
        _FIFOInterface.__init__(self, o_dw, 2)
        cross = SimpleCDCr(clkdiv, clk, i_dw+1, o_dw+2, name=name, outside_reset_n=self.we)
        self.submodules += cross
        self.comb += [
            cross.i.eq(Cat(self.din, self.we)),
            _fifo.din.eq(Cat(cross.o[:i_dw], cross.o[i_dw+1:-1])),
            _fifo.we.eq(reduce(or_(cross.o[i_dw], cross.o[-1]))),
            self.dout.eq(_fifo.dout),
            _fifo.re.eq(self.re),
            self.readable.eq(_fifo.readable),
        ]


class AsyncFIFOXilinx7(Module):
    LATENCY     = 4 # 4 to pass through memory and 1 for output register
    WCL_LATENCY = 4
    RANDOMIZE   = False

    @classmethod
    def randomize_delay(cls):
        cls.RANDOMIZE   = True
        cls.LATENCY     = 4
        cls.WCL_LATENCY = 5

    def __init__(self, wclk, rclk, randomize=False):
        delay = 4
        if self.RANDOMIZE:
            from random import random
            if 0.5 < random():
                delay += 1
        assert type(wclk) == str
        assert type(rclk) == str

        self.DI = Signal(72)
        self.WREN = Signal()
        self.FULL = Signal()

        self.DO = Signal(72)
        self.RDEN = Signal()
        self.EMPTY = Signal(reset=1)

        self._rst = Signal()

        wclk_w_cnt = Signal(10)
        rclk_r_cnt = Signal(10)

        rclk_w_cnt = [Signal(10) for _ in range(delay-1)]
        wclk_r_cnt = [Signal(10) for _ in range(delay-1)]

        mem = Memory(72, 512)
        self.specials += mem
        w_port = mem.get_port(write_capable=True, has_re=True, clock_domain=wclk)
        r_port = mem.get_port(has_re=True, clock_domain=rclk)
        self.specials += [w_port, r_port]

        self.comb += w_port.dat_w.eq(self.DI)
        self.comb += w_port.adr.eq(wclk_w_cnt[:9])
        self.comb += w_port.we.eq(self.WREN)

        self.comb += self.DO.eq(r_port.dat_r)
        self.comb += r_port.adr.eq(rclk_r_cnt[:9])
        self.comb += r_port.re.eq(self.RDEN)

        empty = Signal(reset=1)
        full  = Signal()

        self.comb += self.FULL.eq(full)
        self.comb += self.EMPTY.eq(empty)
        self.comb += [
            full[0].eq((wclk_r_cnt[-1][9] != wclk_w_cnt[9]) & (wclk_r_cnt[-1][:9] == wclk_w_cnt[:9])),
            empty[0].eq((rclk_r_cnt[9] == rclk_w_cnt[-1][9]) & (rclk_r_cnt[:9] == rclk_w_cnt[-1][:9])),
        ]

        cd_wclk = getattr(self.sync, wclk)
        cd_wclk += [
            If(self.WREN,
                wclk_w_cnt.eq(wclk_w_cnt+1),
            ).Elif(self._rst,
                wclk_w_cnt.eq(0),
            ),
            wclk_r_cnt[0].eq(rclk_r_cnt),
            *[wclk_r_cnt[i+1].eq(wclk_r_cnt[i]) for i in range(delay-2)],
        ]

        cd_rclk = getattr(self.sync, rclk)
        cd_rclk += [
            If(self.RDEN,
                rclk_r_cnt.eq(rclk_r_cnt+1),
            ).Elif(self._rst,
                rclk_r_cnt.eq(0),
            ),
            rclk_w_cnt[0].eq(wclk_w_cnt),
            *[rclk_w_cnt[i+1].eq(rclk_w_cnt[i]) for i in range(delay-2)],
        ]


class AsyncFIFOXilinx7Wrap(Module, _FIFOInterface):
    LATENCY     = AsyncFIFOXilinx7.LATENCY
    WCL_LATENCY = AsyncFIFOXilinx7.WCL_LATENCY

    @classmethod
    def reset_latency(cls):
        cls.LATENCY=AsyncFIFOXilinx7.LATENCY
        cls.WCL_LATENCY=AsyncFIFOXilinx7.WCL_LATENCY

    def __init__(self, wclk, rclk, i_dw, o_dw, name=None):
        _FIFOInterface.__init__(self, max(i_dw, o_dw), 512)
        width=max(i_dw, o_dw)
        number_of_fifos = (width + 71)//72
        cdcs = [AsyncFIFOXilinx7(wclk, rclk) for _ in range(number_of_fifos)]
        self.submodules += cdcs

        self._rst = Signal()
        for cdc in cdcs:
            self.comb += cdc._rst.eq(self._rst)

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
