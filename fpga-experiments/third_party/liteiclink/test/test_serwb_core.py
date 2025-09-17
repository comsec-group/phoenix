#!/usr/bin/env python3

#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest
import random

from migen import *

from litex.gen.sim import *

from litex.soc.interconnect import stream

from liteiclink.serwb import scrambler
from liteiclink.serwb.core import SERWBCore

from litex.soc.interconnect.wishbone import SRAM

# Fake Init/Serdes/PHY -----------------------------------------------------------------------------

class FakeInit(Module):
    def __init__(self):
        self.ready = Signal(reset=1)


class FakeSerdes(Module):
    def __init__(self):
        self.tx_ce = Signal()
        self.tx_k  = Signal(4)
        self.tx_d  = Signal(32)
        self.rx_ce = Signal()
        self.rx_k  = Signal(4)
        self.rx_d  = Signal(32)

        # # #

        data_ce = Signal(5, reset=0b00001)
        self.sync += data_ce.eq(Cat(data_ce[1:], data_ce[0]))

        self.comb += [
            self.tx_ce.eq(data_ce[0]),
            self.rx_ce.eq(data_ce[0])
        ]

class FakePHY(Module):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint([("data", 32)])
        self.source = source = stream.Endpoint([("data", 32)])

        # # #

        self.submodules.init   = FakeInit()
        self.submodules.serdes = FakeSerdes()

        # TX dataflow
        self.comb += [
            If(self.init.ready,
                sink.ready.eq(self.serdes.tx_ce),
                If(sink.valid,
                    self.serdes.tx_d.eq(sink.data)
                )
            )
        ]

        # RX dataflow
        self.comb += [
            If(self.init.ready,
                source.valid.eq(self.serdes.rx_ce),
                source.data.eq(self.serdes.rx_d)
            )
        ]

# DUT Scrambler ------------------------------------------------------------------------------------

class DUTScrambler(Module):
    def __init__(self):
        self.submodules.scrambler   = scrambler.Scrambler(sync_interval=16)
        self.submodules.descrambler = scrambler.Descrambler()
        self.comb += self.scrambler.source.connect(self.descrambler.sink)

# DUT Core -----------------------------------------------------------------------------------------

class DUTCore(Module):
    def __init__(self, **kwargs):
        # Wishbone slave
        phy_slave   = FakePHY()
        serwb_slave = SERWBCore(phy_slave, int(1e6), "slave")
        self.submodules += phy_slave, serwb_slave

        # Wishbone master
        phy_master   = FakePHY()
        serwb_master = SERWBCore(phy_master, int(1e6), "master")
        self.submodules += phy_master, serwb_master

        # Connect phy
        self.comb += [
            phy_master.serdes.rx_ce.eq(phy_slave.serdes.tx_ce),
            phy_master.serdes.rx_k.eq(phy_slave.serdes.tx_k),
            phy_master.serdes.rx_d.eq(phy_slave.serdes.tx_d),

            phy_slave.serdes.rx_ce.eq(phy_master.serdes.tx_ce),
            phy_slave.serdes.rx_k.eq(phy_master.serdes.tx_k),
            phy_slave.serdes.rx_d.eq(phy_master.serdes.tx_d)
        ]

        # Add wishbone sram to wishbone master
        sram = SRAM(1024, bus=serwb_master.etherbone.wishbone.bus)
        self.submodules += sram

        # Expose wishbone slave
        self.wishbone = serwb_slave.etherbone.wishbone.bus

# Test SERWB Core ----------------------------------------------------------------------------------

class TestSERWBCore(unittest.TestCase):
    def test_scrambler(self):
        def generator(dut, rand_level=50):
            # Prepare test
            prng      = random.Random(42)
            i         = 0
            last_data = -1
            # Test loop
            while i != 256:
                # Stim
                yield dut.scrambler.sink.valid.eq(1)
                if (yield dut.scrambler.sink.valid) & (yield dut.scrambler.sink.ready):
                    i += 1
                yield dut.scrambler.sink.data.eq(i)

                # Check
                yield dut.descrambler.source.ready.eq(prng.randrange(100) > rand_level)
                if (yield dut.descrambler.source.valid) & (yield dut.descrambler.source.ready):
                    current_data = (yield dut.descrambler.source.data)
                    if (current_data != (last_data + 1)):
                        dut.errors += 1
                    last_data = current_data

                # Cycle
                yield

        dut = DUTScrambler()
        dut.errors = 0
        run_simulation(dut, generator(dut))
        self.assertEqual(dut.errors, 0)

    def test_serwb(self):
        def generator(dut):
            # Prepare test
            prng        = random.Random(42)
            data_base   = 0x100
            data_length = 4
            datas_w     = [prng.randrange(2**32) for i in range(data_length)]
            datas_r     = []

            # Write
            for i in range(data_length):
                yield from dut.wishbone.write(data_base + i, datas_w[i])

            # Read
            for i in range(data_length):
                datas_r.append((yield from dut.wishbone.read(data_base + i)))

            # Check
            for i in range(data_length):
                if datas_r[i] != datas_w[i]:
                    dut.errors += 1

        dut = DUTCore()
        dut.errors = 0
        run_simulation(dut, generator(dut))
        self.assertEqual(dut.errors, 0)
