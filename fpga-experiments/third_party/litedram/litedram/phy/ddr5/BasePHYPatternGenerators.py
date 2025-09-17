# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import or_
from functools import reduce

from migen.fhdl.structure import Signal, If, Cat, Replicate
from migen.fhdl.module import Module


class DQOePattern(Module):
    def __init__(self, nphases, wlevel_en):
        self.window = window = Signal(nphases + 2)
        self.oe = Signal(2*nphases)
        for i in range(nphases):
            self.comb += [
                If(~wlevel_en,
                    self.oe[2*i:2*i+2].eq(Cat(Replicate(reduce(or_, window[i: i+3]), 2))),
                ),
            ]


class DQSPattern(Module):
    def __init__(self, nphases, wlevel_en: Signal()):
        self.window = window = Signal(nphases + 4)
        self.o  = Signal(2*nphases)
        self.oe = Signal(2*nphases)

        # # #

        # DQS Pattern transmitted as LSB-first.
        # Always enabled in write leveling mode, else during transfers
        # Preamble is 2 cycles and postamble is 0.5 cycle

        cases = []

        for i in range(0, nphases):
            cases.extend([
                If(reduce(or_, window[i+2:i+4]),
                    self.o[2*i:2*(i+1)].eq(0b01),
                ).Else(
                    self.o[2*i:2*(i+1)].eq(0),
                ),
                If(reduce(or_, window[i:i+5]) | wlevel_en,
                    self.oe[2*i:2*(i+1)].eq(0b11),
                ).Else(
                    self.oe[2*i:2*(i+1)].eq(0),
                ),
            ])

        self.comb += [
            self.o.eq(0),
            self.oe.eq(0),
            *cases,
        ]
