#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.fhdl.module import Module
from migen.genlib.cdc import MultiReg

from operator import or_
from functools import reduce

class S7PHYCRG(Module):
    def __init__(self,
                 reset_clock_domain, reset_clock_90_domain,
                 source_4x, source_4x_90):

        self.rst                = Signal(reset=1)
        self.rst_set            = False
        self.reset_clock_domain = reset_clock_90_domain
        self.domain_resets      = {}
        self.domain_CEs         = {}
        self.domain_OCEs        = {}
        self.div_factors        = {}

        # BUFR with BUFMRCE reset sequence
        self.bufr_clr = bufr_clr = Signal()
        bufmrce_CE = Signal()
        bufmrce_90_CE = Signal()
        bufmrce_90_CE_1 = Signal()
        counter = Signal(8)
        self.stable_clk = Signal()

        # BUMRCE output
        self.intermediate = Signal()
        self.intermediate_90 = Signal()

        # BUFMRCE
        self.specials += Instance(
            "BUFMRCE",
            i_I=source_4x,
            o_O=self.intermediate,
            i_CE=bufmrce_CE,
        )

        self.specials += Instance(
            "BUFMRCE",
            i_I=source_4x_90,
            o_O=self.intermediate_90,
            i_CE=bufmrce_90_CE_1,
        )

        # Reset sequencer
        cd_reset = getattr(self.sync, reset_clock_90_domain)
        cd_reset += [
            If(self.rst,
                counter.eq(0),
                bufmrce_90_CE.eq(0),
                self.stable_clk.eq(0),
            ).Elif(counter != 0xFF,
                counter.eq(counter+1)
            ),
            If(counter == 0x20,
                bufr_clr.eq(1),
            ),
            If(counter == 0x40,
                bufmrce_90_CE.eq(1),
            ),
            If(counter == 0x60,
                bufmrce_90_CE.eq(0),
            ),
            If(counter == 0x80,
                bufr_clr.eq(0),
            ),
            If(counter == 0xA0,
                bufmrce_90_CE.eq(1),
            ),
            If(counter == 0xF0,
                self.stable_clk.eq(1),
            ),
            bufmrce_90_CE_1.eq(bufmrce_90_CE),
        ]
        cd_reset = getattr(self.sync, reset_clock_domain)
        cd_reset += [
            bufmrce_CE.eq(bufmrce_90_CE),
        ]


    def create_clock_domains(self, clock_domains, io_banks):
        for io_bank in io_banks:
            for clk_domain in clock_domains:
                div = 4
                buf_type = "BUFR"
                if "4x" in clk_domain:
                    buf_type="BUFIO"
                    div = None
                elif "2x" in clk_domain:
                    div = 2

                in_clk = self.intermediate
                if "90" in clk_domain:
                    in_clk = self.intermediate_90

                reset_less = True if div is None else False
                setattr(self.clock_domains,
                        f"cd_{clk_domain}_{io_bank}",
                        ClockDomain(reset_less=reset_less, name=f"{clk_domain}_{io_bank}")
                )
                clk = ClockSignal(f"{clk_domain}_{io_bank}")
                buffer_dict = dict(
                    i_I=in_clk,
                    o_O=clk,
                )
                if div is not None:
                    self.div_factors[f"{clk_domain}_{io_bank}"] = div
                    buffer_dict["p_BUFR_DIVIDE"] = str(div)
                    buffer_dict["i_CLR"] = self.bufr_clr

                special = Instance(
                    buf_type,
                    **buffer_dict
                )
                self.specials += special


    def get_rst(self, clock_domain):
        if clock_domain == "sys":
            return self._raw_reset_signal
        if clock_domain not in self.domain_resets:
            _reset = Signal()
            counter = Signal(max=(64//self.div_factors[clock_domain]))
            _counter = Signal.like(counter)
            for i in range(len(counter)):
                self.specials += Instance(
                    "FDPE",
                    p_INIT  = 1,
                    i_PRE   = self.bufr_clr,
                    i_CE    = self.stable_clk,
                    i_D     = _counter[i],
                    i_C     = ClockSignal(clock_domain),
                    o_Q     = counter[i],
                )
            self.specials += Instance(
                "FDPE",
                p_INIT  = 1,
                i_PRE   = self.bufr_clr,
                i_CE    = self.stable_clk,
                i_D     = _reset,
                i_C     = ClockSignal(clock_domain),
                o_Q     = ResetSignal(clock_domain),
            )

            self.comb += [
                If(counter != 0,
                    _counter.eq(counter - 1),
                ),
                _reset.eq(reduce(or_, counter)),
            ]
            in_rst = _reset
            for _ in range(8):
                out_rst = Signal()
                self.specials += Instance(
                    "FDPE",
                    p_INIT  = 1,
                    i_PRE   = self.bufr_clr,
                    i_CE    = self.stable_clk,
                    i_D     = in_rst,
                    i_C     = ClockSignal(clock_domain),
                    o_Q     = out_rst,
                )
                in_rst = out_rst
            self.domain_resets[clock_domain] = in_rst

        return self.domain_resets[clock_domain]


    def get_ce(self, clock_domain):
        CE = Signal()
        if clock_domain not in self.domain_CEs:
            _CE = Signal()
            counter = Signal(max=(2048//self.div_factors[clock_domain]))
            _counter = Signal.like(counter)
            for i in range(len(counter)):
                self.specials += Instance(
                    "FDPE",
                    p_INIT  = 1,
                    i_PRE   = self.bufr_clr,
                    i_CE    = ~self.get_rst(clock_domain),
                    i_D     = _counter[i],
                    i_C     = ClockSignal(clock_domain),
                    o_Q     = counter[i],
                )

            self.comb += [
                If(counter != 0,
                    _counter.eq(counter - 1),
                ),
                _CE.eq(~(reduce(or_, counter))),
            ]
            self.specials += Instance(
                "FDCE",
                p_INIT  = 0,
                i_CLR   = self.bufr_clr,
                i_CE    = ~self.get_rst(clock_domain),
                i_D     = _CE,
                i_C     = ClockSignal(clock_domain),
                o_Q     = CE,
            )
            self.domain_CEs[clock_domain] = CE

        return self.domain_CEs[clock_domain]


    def get_oce(self, clock_domain):
        CE = Signal()
        if clock_domain not in self.domain_CEs:
            _CE = Signal()
            counter = Signal(max=(2048//self.div_factors[clock_domain]))
            _counter = Signal.like(counter)
            for i in range(len(counter)):
                self.specials += Instance(
                    "FDPE",
                    p_INIT  = 1,
                    i_PRE   = self.bufr_clr,
                    i_CE    = ~self.get_rst(clock_domain),
                    i_D     = _counter[i],
                    i_C     = ClockSignal(clock_domain),
                    o_Q     = counter[i],
                )

            self.comb += [
                If(counter != 0,
                    _counter.eq(counter - 1),
                ),
                _CE.eq(~(reduce(or_, counter))),
            ]
            self.specials += Instance(
                "FDCE",
                p_INIT  = 0,
                i_CLR   = self.bufr_clr,
                i_CE    = ~self.get_rst(clock_domain),
                i_D     = _CE,
                i_C     = ClockSignal(clock_domain),
                o_Q     = CE,
            )
            self.domain_CEs[clock_domain] = CE

        if clock_domain not in self.domain_OCEs:
            CE = Signal()
            self.specials += Instance(
                "BUFH",
                i_I     = self.domain_CEs[clock_domain],
                o_O     = CE,
            )
            self.domain_OCEs[clock_domain] = CE

        return self.domain_OCEs[clock_domain]


    def add_rst(self, reset_signal):
        assert not self.rst_set
        self._raw_reset_signal = reset_signal
        self.specials += MultiReg(reset_signal, self.rst, self.reset_clock_domain, reset=1)
        self.rst_set = True


    def do_finalize(self):
        assert self.rst_set
