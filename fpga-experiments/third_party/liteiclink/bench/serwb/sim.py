#!/usr/bin/env python3

#
# This file is part of LiteICLink.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import argparse

from migen import *

from litex.build.generic_platform import *
from litex.build.sim import SimPlatform
from litex.build.sim.config import SimConfig

from litex.soc.interconnect.csr import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *
from litex.soc.interconnect import wishbone

from liteeth.phy.model import LiteEthPHYModel
from liteeth.core import LiteEthUDPIPCore
from liteeth.frontend.etherbone import LiteEthEtherbone

from liteiclink.serwb.genphy import SERWBPHY
from liteiclink.serwb.core import SERWBCore

# IOs ----------------------------------------------------------------------------------------------

_io = [
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 0, Pins(1)),
    ("serial", 0,
        Subsignal("source_valid", Pins(1)),
        Subsignal("source_ready", Pins(1)),
        Subsignal("source_data",  Pins(8)),

        Subsignal("sink_valid", Pins(1)),
        Subsignal("sink_ready", Pins(1)),
        Subsignal("sink_data",  Pins(8)),
    ),
    ("eth", 0,
        Subsignal("source_valid", Pins(1)),
        Subsignal("source_ready", Pins(1)),
        Subsignal("source_data",  Pins(8)),

        Subsignal("sink_valid",   Pins(1)),
        Subsignal("sink_ready",   Pins(1)),
        Subsignal("sink_data",    Pins(8)),
    ),
]

# Platform -----------------------------------------------------------------------------------------

class Platform(SimPlatform):
    def __init__(self):
        SimPlatform.__init__(self, "SIM", _io)

# SerWBMinSoC --------------------------------------------------------------------------------------

class SerWBMinSoC(SoCMini):
    def __init__(self):
        platform     = Platform()
        sys_clk_freq = int(1e6)

        self.comb += platform.trace.eq(1)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        # SerWB ------------------------------------------------------------------------------------

        # Pads
        serwb_master_pads = Record([("tx", 1), ("rx", 1)])
        serwb_slave_pads  = Record([("tx", 1), ("rx", 1)])
        self.comb += serwb_slave_pads.rx.eq(serwb_master_pads.tx)
        self.comb += serwb_master_pads.rx.eq(serwb_slave_pads.tx)

        # Master
        serwb_master_phy = SERWBPHY(
            device       = platform.device,
            pads         = serwb_master_pads,
            mode         = "master",
            init_timeout = 128)
        self.submodules += serwb_master_phy

        # Slave
        serwb_slave_phy = SERWBPHY(
            device       = platform.device,
            pads         = serwb_slave_pads,
            mode         ="slave",
            init_timeout = 128)
        self.submodules += serwb_slave_phy

        # Simulation Timer
        timer = Signal(32)
        self.sync += timer.eq(timer + 1)


        # Simulation Gen/Check
        class EndpointCounterGenerator(Module):
            def __init__(self, name, ready, endpoint):
                counter = Signal(32)
                self.sync += [
                    endpoint.valid.eq(ready),
                    If(endpoint.valid & endpoint.ready,
                        endpoint.data.eq(endpoint.data + 1)
                    )
                ]

        class EndpointCounterChecker(Module):
            def __init__(self, name, ready, endpoint):
                last_data = Signal(32, reset=2**32-1)
                self.sync += [
                    endpoint.ready.eq(ready),
                    If(endpoint.valid & endpoint.ready,
                        #Display("[%08d] {} %08x".format(name), timer, endpoint.data),
                        If((endpoint.data - 1) != last_data,
                            Display("[%08d] {} check error.".format(name), timer)
                        ),
                        last_data.eq(endpoint.data),
                    )
                ]

        ready = serwb_master_phy.init.ready & serwb_slave_phy.init.ready

        # Master gen/check
        self.submodules += EndpointCounterGenerator("Master", ready=ready, endpoint=serwb_master_phy.sink)
        self.submodules += EndpointCounterChecker("Master",  ready=ready, endpoint=serwb_master_phy.source)

        # Slave gen/check
        self.submodules += EndpointCounterGenerator("Slave",  ready=ready, endpoint=serwb_slave_phy.sink)
        self.submodules += EndpointCounterChecker("Slave",  ready=ready, endpoint=serwb_slave_phy.source)


        # Simulation Status
        serwb_master_phy.init.fsm.finalize()
        serwb_slave_phy.init.fsm.finalize()
        for phy, fsm in [
            ["master",  serwb_master_phy.init.fsm],
            ["slave ",  serwb_slave_phy.init.fsm]]:
            for state, value in fsm.encoding.items():
                self.sync += [
                    If(fsm.next_state != fsm.state,
                        If(fsm.next_state == value,
                            Display("[%08d] {} entering {} state.".format(phy.upper(), state), timer)
                        )
                    )
                ]

        # Simulation End
        self.sync += If(timer > 10000, Finish())

# SerWBSoC -----------------------------------------------------------------------------------------

class SerWBSoC(SoCCore):
    def __init__(self):
        platform     = Platform()
        sys_clk_freq = int(1e6)

        self.comb += platform.trace.eq(1)

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq,
            ident         = "LiteICLink SerWB bench simulation",
            ident_version = True,
            with_uart     = True,
            uart_name     = "sim")

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        # Etherbone---------------------------------------------------------------------------------
        # phy
        self.submodules.ethphy = LiteEthPHYModel(self.platform.request("eth"))
        self.add_csr("ethphy")
        # core
        ethcore = LiteEthUDPIPCore(self.ethphy,
            mac_address = 0x10e2d5000000,
            ip_address  = "192.168.1.50",
            clk_freq    = sys_clk_freq)
        self.submodules.ethcore = ethcore
        # etherbone
        self.submodules.etherbone = LiteEthEtherbone(self.ethcore.udp, 1234, mode="master")
        self.add_wb_master(self.etherbone.wishbone.bus)

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

        # Pads
        serwb_master_pads = Record([("tx", 1), ("rx", 1)])
        serwb_slave_pads  = Record([("tx", 1), ("rx", 1)])
        self.comb += serwb_slave_pads.rx.eq(serwb_master_pads.tx)
        self.comb += serwb_master_pads.rx.eq(serwb_slave_pads.tx)

        # Master
        self.submodules.serwb_master_phy = SERWBPHY(
            device       = platform.device,
            pads         = serwb_master_pads,
            mode         = "master",
            init_timeout = 128)
        self.add_csr("serwb_master_phy")

        # Slave
        self.submodules.serwb_slave_phy = SERWBPHY(
            device       = platform.device,
            pads         = serwb_slave_pads,
            mode         ="slave",
            init_timeout = 128)
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

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SerWB LiteX/Verilator Simulation")
    parser.add_argument("--min",         action="store_true", help="Run Minimal simulation (SerSBMinSoC)")
    parser.add_argument("--trace",       action="store_true", help="Enable VCD tracing")
    parser.add_argument("--trace-start", default="0",         help="Cycle to start VCD tracing")
    parser.add_argument("--trace-end",   default="-1",        help="Cycle to end VCD tracing")
    args = parser.parse_args()

    sim_config = SimConfig()
    sim_config.add_clocker("sys_clk", freq_hz=1e6)
    if not args.min:
        sim_config.add_module("serial2console", "serial")
        sim_config.add_module("ethernet", "eth", args={"interface": "tap0", "ip": "192.168.1.100"})

    soc     = SerWBMinSoC() if args.min else SerWBSoC()
    builder = Builder(soc, csr_csv="csr.csv")
    builder.build(sim_config=sim_config,
        trace       = args.trace,
        trace_start = int(args.trace_start),
        trace_end   = int(args.trace_end),
    )

if __name__ == "__main__":
    main()
