#!/usr/bin/env python3

#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import sys
import argparse

from migen import *
from migen.genlib.io import CRG

from litex_boards.platforms import kcu105

from litex.build.generic_platform import *

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.cores.code_8b10b import K

from liteiclink.serdes.gth_ultrascale import GTHChannelPLL, GTHQuadPLL, GTH

# IOs ----------------------------------------------------------------------------------------------

_transceiver_io = [
    # PCIe
    ("pcie_tx", 0,
        Subsignal("p", Pins("AC3")),
        Subsignal("n", Pins("AC4"))
    ),
    ("pcie_rx", 0,
        Subsignal("p", Pins("AB2")),
        Subsignal("n", Pins("AB1"))
    ),
    # SFP0
    ("sfp0_tx", 0,
        Subsignal("p", Pins("U4")),
        Subsignal("n", Pins("U3"))
    ),
    ("sfp0_rx", 0,
        Subsignal("p", Pins("T2")),
        Subsignal("n", Pins("T1"))
    ),
    # SFP1
    ("sfp1_tx", 0,
        Subsignal("p", Pins("W4")),
        Subsignal("n", Pins("W3"))
    ),
    ("sfp1_rx", 0,
        Subsignal("p", Pins("V2")),
        Subsignal("n", Pins("V1"))
    ),
    # SMA
    ("sma_tx", 0,
        Subsignal("p", Pins("R4")),
        Subsignal("n", Pins("R3"))
    ),
    ("sma_rx", 0,
        Subsignal("p", Pins("P2")),
        Subsignal("n", Pins("P1"))
    ),
]

# GTXTestSoC ---------------------------------------------------------------------------------------

class GTHTestSoC(SoCMini):
    def __init__(self, platform, connector="pcie", linerate=2.5e9):
        assert connector in ["pcie", "sfp0", "sfp1", "sma"]
        sys_clk_freq = int(125e6)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, sys_clk_freq, ident="LiteICLink bench on KCU105")

        # UARTBone ---------------------------------------------------------------------------------
        self.add_uartbone()

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("clk125"), platform.request("cpu_reset"))
        platform.add_period_constraint(self.crg.cd_sys.clk, 1e9/125e6)

        # 125Mhz clock -> user_sma --> user_sma_mgt_refclk -----------------------------------------
        user_sma_clock_pads = platform.request("user_sma_clock")
        user_sma_clock      = Signal()
        self.specials += Instance("ODDRE1",
            i_D1 = 0,
            i_D2 = 1,
            i_SR = 0,
            i_C  = ClockSignal(),
            o_Q  = user_sma_clock)
        self.specials += Instance("OBUFDS",
            i_I  = user_sma_clock,
            o_O  = user_sma_clock_pads.p,
            o_OB = user_sma_clock_pads.n)

        # GTH RefClk -------------------------------------------------------------------------------
        refclk      = Signal()
        refclk_pads = platform.request("user_sma_mgt_refclk")
        self.specials += Instance("IBUFDS_GTE3",
            i_CEB = 0,
            i_I   = refclk_pads.p,
            i_IB  = refclk_pads.n,
            o_O   = refclk)

        # GTH PLL ----------------------------------------------------------------------------------
        cpll = GTHChannelPLL(refclk, 125e6, linerate)
        print(cpll)
        self.submodules += cpll

        # GTH --------------------------------------------------------------------------------------
        tx_pads = platform.request(connector + "_tx")
        rx_pads = platform.request(connector + "_rx")
        self.submodules.serdes0 = serdes0 = GTH(cpll, tx_pads, rx_pads, sys_clk_freq,
            tx_buffer_enable = True,
            rx_buffer_enable = True,
            clock_aligner    = False)
        serdes0.add_stream_endpoints()
        serdes0.add_controls()
        serdes0.add_clock_cycles()

        platform.add_period_constraint(serdes0.cd_tx.clk, 1e9/serdes0.tx_clk_freq)
        platform.add_period_constraint(serdes0.cd_rx.clk, 1e9/serdes0.rx_clk_freq)
        self.platform.add_false_path_constraints(self.crg.cd_sys.clk, serdes0.cd_tx.clk, serdes0.cd_rx.clk)

        if connector == "sfp0":
            self.comb += platform.request("sfp_tx_disable_n", 0).eq(1)
        if connector == "sfp1":
            self.comb += platform.request("sfp_tx_disable_n", 1).eq(1)

        # Test -------------------------------------------------------------------------------------
        counter = Signal(32)
        self.sync.tx += counter.eq(counter + 1)

        # K28.5 and slow counter --> TX
        self.comb += [
            serdes0.sink.valid.eq(1),
            serdes0.sink.ctrl.eq(0b1),
            serdes0.sink.data[:8].eq(K(28, 5)),
            serdes0.sink.data[8:].eq(counter[26:]),
        ]

        # RX (slow counter) --> Leds
        for i in range(4):
            self.comb += platform.request("user_led", 4 + i).eq(serdes0.source.data[i])

        # Leds -------------------------------------------------------------------------------------
        sys_counter = Signal(32)
        self.sync.sys += sys_counter.eq(sys_counter + 1)
        self.comb += platform.request("user_led", 0).eq(sys_counter[26])

        tx_counter = Signal(32)
        self.sync.tx += tx_counter.eq(tx_counter + 1)
        self.comb += platform.request("user_led", 1).eq(tx_counter[26])

        rx_counter = Signal(32)
        self.sync.rx += rx_counter.eq(rx_counter + 1)
        self.comb += platform.request("user_led", 2).eq(rx_counter[26])

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteICLink transceiver example on KCU105")
    parser.add_argument("--build",     action="store_true", help="Build bitstream")
    parser.add_argument("--load",      action="store_true", help="Load bitstream (to SRAM)")
    parser.add_argument("--connector", default="pcie",      help="Connector: pcie (default), sfp0, sfp1 or sma")
    parser.add_argument("--linerate",  default="2.5e9",     help="Linerate (default: 2.5e9)")
    args = parser.parse_args()

    platform = kcu105.Platform()
    platform.add_extension(_transceiver_io)
    soc = GTHTestSoC(platform,
        connector = args.connector,
        linerate  = float(args.linerate)
    )
    builder = Builder(soc, csr_csv="kcu105.csv")
    builder.build(run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

if __name__ == "__main__":
    main()
