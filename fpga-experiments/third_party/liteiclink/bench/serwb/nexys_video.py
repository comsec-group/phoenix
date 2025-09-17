#!/usr/bin/env python3

#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import sys
import argparse

from migen import *
from migen.genlib.misc import WaitTimer
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *

from litex.build.generic_platform import *
from litex_boards.platforms import nexys_video as nexys

from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litex.soc.cores.clock import S7PLL, S7IDELAYCTRL
from litex.soc.interconnect import wishbone

from liteiclink.serwb.phy import SERWBPHY
from liteiclink.serwb.genphy import SERWBPHY as SERWBLowSpeedPHY
from liteiclink.serwb.core import SERWBCore

from litescope import LiteScopeAnalyzer

# IOs ----------------------------------------------------------------------------------------------

serwb_io = [
    # HDMI loopback
    ("serwb_master", 0,
        Subsignal("clk_p", Pins("T1"), IOStandard("TMDS_33")), # hdmi_out clk
        Subsignal("clk_n", Pins("U1"), IOStandard("TMDS_33")), # hdmi_out clk
        Subsignal("tx_p",  Pins("W1"), IOStandard("TMDS_33")), # hdmi_out data0
        Subsignal("tx_n",  Pins("Y1"), IOStandard("TMDS_33")), # hdmi_out data0
        Subsignal("rx_p",  Pins("W2"), IOStandard("TMDS_33")), # hdmi_in data1
        Subsignal("rx_n",  Pins("Y2"), IOStandard("TMDS_33")), # hdmi_in data1
    ),

    ("serwb_slave", 0,
        Subsignal("clk_p", Pins("V4"),  IOStandard("TMDS_33")), # hdmi_in clk
        Subsignal("clk_n", Pins("W4"),  IOStandard("TMDS_33")), # hdmi_in clk
        Subsignal("tx_p",  Pins("AA1"), IOStandard("TMDS_33")), # hdmi_out data1
        Subsignal("tx_n",  Pins("AB1"), IOStandard("TMDS_33")), # hdmi_out data1
        Subsignal("rx_p",  Pins("Y3"),  IOStandard("TMDS_33")), # hdmi_in data0
        Subsignal("rx_n",  Pins("AA3"), IOStandard("TMDS_33")), # hdmi_in data0
    ),
    ("serwb_enable", 0, Pins("R3"), IOStandard("LVCMOS33")), # hdmi_txen
]

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys       = ClockDomain()
        self.clock_domains.cd_sys4x     = ClockDomain(reset_less=True)
        self.clock_domains.cd_idelay    = ClockDomain()

        # # #

        self.submodules.pll = pll = S7PLL(speedgrade=-1)
        self.comb += pll.reset.eq(~platform.request("cpu_reset"))
        pll.register_clkin(platform.request("clk100"), 100e6)
        pll.create_clkout(self.cd_sys,       sys_clk_freq)
        pll.create_clkout(self.cd_sys4x,     4*sys_clk_freq)
        pll.create_clkout(self.cd_idelay,    200e6)

        self.submodules.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

# SerWBTestSoC ------------------------------------------------------------------------------------

class SerWBTestSoC(SoCMini):
    mem_map = {
        "serwb": 0x30000000,
    }
    mem_map.update(SoCMini.mem_map)

    def __init__(self, platform, low_speed=True, with_analyzer=True):
        sys_clk_freq = int(125e6)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, sys_clk_freq,
            csr_data_width = 32,
            ident          = "LiteICLink SerWB bench on Nexys Video",
            ident_version  = True,
            with_uart      = True,
            uart_name      = "bridge")

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)


        # SerWB ------------------------------------------------------------------------------------
        # SerWB simple test with a SerWB Master added as a Slave peripheral to the SoC and connected
        # to a SerWB Slave with a SRAM attached. Access to this SRAM is then tested from the main
        # SoC through SerWB:
        #                   +--------+    +------+    +------+    +------+
        #                   |        |    |      +-ck->      |    |      |
        #                   |  Test  +----+SerWB +-tx->SerWB +----> Test |
        #                   |   SoC  | WB |Master|    |Slave | WB | SRAM |
        #                   |        +<---+      <-rx-+      <----+      |
        #                   +--------+    +------+    +------+    +------+
        # ------------------------------------------------------------------------------------------

        # Enable
        self.comb += platform.request("serwb_enable").eq(1)

        phy_cls = SERWBLowSpeedPHY if low_speed else SERWBPHY

        # Master
        self.submodules.serwb_master_phy = phy_cls(
            device = platform.device,
            pads   = platform.request("serwb_master"),
            mode   = "master")
        self.add_csr("serwb_master_phy")

        # Slave
        self.submodules.serwb_slave_phy = phy_cls(
            device = platform.device,
            pads   = platform.request("serwb_slave"),
            mode   ="slave")
        self.add_csr("serwb_slave_phy")

        # Wishbone Slave
        serwb_master_core = SERWBCore(self.serwb_master_phy, self.clk_freq, mode="slave")
        self.submodules += serwb_master_core

        # Wishbone Master
        serwb_slave_core = SERWBCore(self.serwb_slave_phy, self.clk_freq, mode="master")
        self.submodules += serwb_slave_core

        # Wishbone SRAM
        self.submodules.serwb_sram = wishbone.SRAM(8192)
        self.bus.add_slave("serwb", serwb_master_core.bus, SoCRegion(origin=0x30000000, size=8192))
        self.comb += serwb_slave_core.bus.connect(self.serwb_sram.bus)

        # Leds -------------------------------------------------------------------------------------
        self.comb += [
            platform.request("user_led", 0).eq(self.serwb_master_phy.init.ready),
            platform.request("user_led", 1).eq(self.serwb_master_phy.init.error),
            platform.request("user_led", 2).eq(self.serwb_slave_phy.init.ready),
            platform.request("user_led", 3).eq(self.serwb_slave_phy.init.error),
        ]

        # Analyzer ---------------------------------------------------------------------------------
        if with_analyzer:
            analyzer_signals = [
                self.serwb_master_phy.init.fsm,
                self.serwb_master_phy.serdes.rx.data,
                self.serwb_master_phy.serdes.rx.comma,
                self.serwb_master_phy.serdes.rx.idle,
                self.serwb_master_phy.serdes.tx.data,
                self.serwb_master_phy.serdes.tx.comma,
                self.serwb_master_phy.serdes.tx.idle,
                self.serwb_master_phy.serdes.rx.datapath.decoder.source,

                self.serwb_slave_phy.init.fsm,
                self.serwb_slave_phy.serdes.rx.data,
                self.serwb_slave_phy.serdes.rx.comma,
                self.serwb_slave_phy.serdes.rx.idle,
                self.serwb_slave_phy.serdes.tx.data,
                self.serwb_slave_phy.serdes.tx.comma,
                self.serwb_slave_phy.serdes.tx.idle,
                self.serwb_slave_phy.serdes.rx.datapath.decoder.source,
            ]
            self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 256, csr_csv="analyzer.csv")
            self.add_csr("analyzer")

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteICLink SerWB bench on Nexys Video")
    parser.add_argument("--build",         action="store_true", help="Build bitstream")
    parser.add_argument("--load",          action="store_true", help="Load bitstream (to SRAM)")
    parser.add_argument("--low-speed",     action="store_true", help="Use Low-Speed PHY")
    parser.add_argument("--with-analyzer", action="store_true", help="Add LiteScope Analyzer")
    args = parser.parse_args()

    platform = nexys.Platform()
    platform.add_extension(serwb_io)
    soc     = SerWBTestSoC(platform, low_speed=args.low_speed, with_analyzer=args.with_analyzer)
    builder = Builder(soc, csr_csv="csr.csv")
    builder.build(run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

if __name__ == "__main__":
    main()
