# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import re
import copy
import unittest
from typing import Mapping
from functools import partial
from collections import defaultdict
from random import randrange

from migen import *

from litedram.phy.sim_utils import AsyncFIFOXilinx7

import test.phy_common

sim_clocks={
    "sys":            (64, 31),
    "sys_180":        (64, 63),
    "sys_rst":        (64, 30),
    "sys2x":          (32, 15),
    "sys2x_1":        (32, 14),
    "sys2x_90":       (32,  7),
    "sys2x_180":      (32, 31),
}
run_simulation = partial(test.phy_common.run_simulation, clocks=sim_clocks)

class AsyncFIFOXilinx7Tests(unittest.TestCase):
    SYS_CLK_FREQ = 50e6
    DATABITS = 8
    BURST_LENGTH = 8
    NPHASES = 4

    def setUp(self):
        self.dut = AsyncFIFOXilinx7("sys", "sys2x_1")

    def run_test(self, drivers, checkers=[], **kwargs):
        # pad_checkers: {clock: {sig: values}}
        dut = self.dut
        generators = defaultdict(list)
        for cd, driver in drivers:
            generators[cd].append(driver(dut))
        for cd, checker in checkers:
            generators[cd].append(checker(dut))

        class CRG(Module):
            def __init__(self, dut):
                r = Signal(2)
                self.sync.sys_rst += [If(r<3, r.eq(r+1))]
                self.submodules.dut = dut
                for clk in sim_clocks:
                    if clk == "sys_rst":
                        continue
                    setattr(self.clock_domains, "cd_{}".format(clk), ClockDomain(clk))
                    cd = getattr(self, 'cd_{}'.format(clk))
                    self.comb += cd.rst.eq(~r[1])
        dut = CRG(dut)
        run_simulation(dut, generators, **kwargs)

    @staticmethod
    def write(dut):
        cnt = 0
        yield dut.DI.eq(cnt)
        yield dut.WREN.eq(1)
        while not (yield dut.FULL):
            yield
            yield dut.DI.eq(cnt)
            yield dut.WREN.eq(1)
            cnt += 1
        yield dut.DI.eq(0)
        yield dut.WREN.eq(0)
        yield

    @staticmethod
    def read(dut):
        for i in range(1024):
            for _ in range(randrange(0, 10)):
                yield dut.RDEN.eq(0)
                yield
            while (yield dut.EMPTY):
                yield dut.RDEN.eq(0)
                yield
            yield dut.RDEN.eq(1)
            yield
        yield dut.RDEN.eq(0)
        yield

    @staticmethod
    def transfer(dut):
        yield
        for i in range(1024):
            while (yield dut.FULL):
                yield dut.DI.eq(0)
                yield dut.WREN.eq(0)
                yield
            yield dut.DI.eq(i)
            yield dut.WREN.eq(1)
            yield
        yield dut.DI.eq(0)
        yield dut.WREN.eq(0)
        yield

    def test_write_full(self):
        self.run_test(
            drivers=[("sys_180", self.write)],
            vcd_name="test_write_full.vcd"
        )

    def test_write_read(self):
        self.run_test(
            drivers=[("sys_180", self.transfer), ("sys2x_90", self.read)],
            vcd_name="test_write_read.vcd"
        )
