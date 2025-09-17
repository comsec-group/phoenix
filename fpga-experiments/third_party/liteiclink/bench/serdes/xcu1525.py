#!/usr/bin/env python3

#
# This file is part of LiteICLink.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import sys
import argparse

from migen import *
from migen.genlib.io import CRG

from litex_boards.platforms import xcu1525

from litex.build.generic_platform import *

from litex.soc.cores.clock import USPMMCM
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.cores.code_8b10b import K

from liteiclink.serdes.gty_ultrascale import GTYChannelPLL, GTYQuadPLL, GTY

# IOs ----------------------------------------------------------------------------------------------

_transceiver_io = [
    # PCIe
    ("pcie_tx", 0,
        Subsignal("p", Pins("AF7")),
        Subsignal("n", Pins("AF6"))
    ),
    ("pcie_rx", 0,
        Subsignal("p", Pins("AF2")),
        Subsignal("n", Pins("AF1"))
    ),

    # QSFP0
    ("qsfp0_refclk", 0,
        Subsignal("p", Pins("M11")),
        Subsignal("n", Pins("M10")),
    ),
    ("qsfp0_fs", 0, Pins("AT20 AU22"), IOStandard("LVCMOS12")),
    ("qsfp0_tx", 0,
        Subsignal("p", Pins("N9")),
        Subsignal("n", Pins("N8"))
    ),
    ("qsfp0_rx", 0,
        Subsignal("p", Pins("N4")),
        Subsignal("n", Pins("N3"))
    ),

    # QSFP1
    ("qsfp1_refclk", 0,
        Subsignal("p", Pins("T11")),
        Subsignal("n", Pins("T10")),
    ),
    ("qsfp1_fs", 0, Pins("AR22 AU20"), IOStandard("LVCMOS12")),
    ("qsfp1_tx", 0,
        Subsignal("p", Pins("U9")),
        Subsignal("n", Pins("U8"))
    ),
    ("qsfp1_rx", 0,
        Subsignal("p", Pins("U4")),
        Subsignal("n", Pins("U3"))
    ),
]

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys = ClockDomain()

        # # #

        # PLL
        self.submodules.pll = pll = USPMMCM(speedgrade=-2)
        pll.register_clkin(platform.request("clk300"), 300e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)

# GTYTestSoC ---------------------------------------------------------------------------------------

class GTYTestSoC(SoCMini):
    def __init__(self, platform, connector="pcie", linerate=2.5e9, use_qpll=False):
        assert connector in ["pcie", "qsfp0", "qsfp1", "qsfp0+1"]
        sys_clk_freq = int(125e6)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, sys_clk_freq, ident="LiteICLink bench on XCU1525")

        # UARTBone ---------------------------------------------------------------------------------
        self.add_uartbone()

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # GTY RefClk -------------------------------------------------------------------------------
        refclk      = Signal()
        refclk_pads = platform.request("qsfp0_refclk")
        self.specials += Instance("IBUFDS_GTE4",
            p_REFCLK_HROW_CK_SEL = 0,
            i_CEB = 0,
            i_I   = refclk_pads.p,
            i_IB  = refclk_pads.n,
            o_O   = refclk)
        if connector in ["qsfp0", "qsfp1"]:
            self.comb += platform.request(connector + "_fs").eq(0b01)
        if connector in ["qsfp0+1"]:
            self.comb += platform.request("qsfp0_fs").eq(0b01)
            self.comb += platform.request("qsfp1_fs").eq(0b01)

        if connector == "qsfp0+1":
            connectors = ["qsfp0", "qsfp1"]
        else:
            connectors = [connector]

        for i, connector in enumerate(connectors):
            # GTY PLL ----------------------------------------------------------------------------------
            if use_qpll:
                pll = GTYQuadPLL(refclk, 156.25e6, linerate)
                print(pll)
                self.submodules.pll = pll
            else:
                pll = GTYChannelPLL(refclk, 156.25e6, linerate)
                print(pll)
                self.submodules += pll

            # GTY --------------------------------------------------------------------------------------
            tx_pads = platform.request(connector + "_tx")
            rx_pads = platform.request(connector + "_rx")
            serdes = GTY(pll, tx_pads, rx_pads, sys_clk_freq,
                tx_buffer_enable = True,
                rx_buffer_enable = True,
                clock_aligner    = False)
            setattr(self.submodules, f"serdes{i}", serdes)
            serdes.add_stream_endpoints()
            serdes.add_controls()
            serdes.add_clock_cycles()

            platform.add_period_constraint(serdes.cd_tx.clk, 1e9/serdes.tx_clk_freq)
            platform.add_period_constraint(serdes.cd_rx.clk, 1e9/serdes.rx_clk_freq)
            self.platform.add_false_path_constraints(self.crg.cd_sys.clk, serdes.cd_tx.clk, serdes.cd_rx.clk)

        # Test -------------------------------------------------------------------------------------
        counter = Signal(32)
        self.sync += counter.eq(counter + 1)

        # K28.5 and slow counter --> TX
        self.comb += [
            self.serdes0.sink.valid.eq(1),
            self.serdes0.sink.ctrl.eq(0b1),
            self.serdes0.sink.data[:8].eq(K(28, 5)),
            self.serdes0.sink.data[8:].eq(counter[26:]),
        ]

        # Analyzer ---------------------------------------------------------------------------------
        from litescope import LiteScopeAnalyzer
        analyzer_signals = [
            self.serdes0.tx_init.done,
            self.serdes0.rx_init.done,
            self.serdes0.tx_init.fsm,
            self.serdes0.rx_init.fsm,
            self.serdes0.cd_tx.rst,
            self.serdes0.cd_rx.rst,
        ]
        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
            depth        = 512,
            clock_domain = "sys",
            csr_csv      = "analyzer.csv")

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteICLink transceiver example on XCU1525")
    parser.add_argument("--build",     action="store_true", help="Build bitstream")
    parser.add_argument("--load",      action="store_true", help="Load bitstream (to SRAM)")
    parser.add_argument("--connector", default="pcie",      help="Connector: pcie (default), qsfp0 , qsfp1 or qsfp0+1")
    parser.add_argument("--linerate",  default="2.5e9",     help="Linerate (default: 2.5e9)")
    parser.add_argument("--pll",       default="cpll",      help="PLL: cpll (default) or qpll")
    args = parser.parse_args()

    platform = xcu1525.Platform()
    platform.add_extension(_transceiver_io)
    soc = GTYTestSoC(platform,
        connector = args.connector,
        linerate  = float(args.linerate),
        use_qpll  = args.pll == "qpll"
    )
    builder = Builder(soc, csr_csv="xcu1525.csv")
    builder.build(run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

if __name__ == "__main__":
    main()
