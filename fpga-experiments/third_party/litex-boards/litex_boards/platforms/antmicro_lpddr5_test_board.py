#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from litex.build.generic_platform import *
from litex.build.xilinx import Xilinx7SeriesPlatform
from litex.build.openocd import OpenOCD

# IOs ----------------------------------------------------------------------------------------------

_io = [
    ("clk100", 0, Pins("L19"), IOStandard("LVCMOS33")),

    ("user_led", 0, Pins("F8"), IOStandard("LVCMOS33")),
    ("user_led", 1, Pins("C8"), IOStandard("LVCMOS33")),
    ("user_led", 2, Pins("A8"), IOStandard("LVCMOS33")),
    ("user_led", 3, Pins("D9"), IOStandard("LVCMOS33")),
    ("user_led", 4, Pins("F9"), IOStandard("LVCMOS33")),

    ("user_btn", 0, Pins("E8"), IOStandard("LVCMOS33")),
    ("user_btn", 1, Pins("B8"), IOStandard("LVCMOS33")),
    ("user_btn", 2, Pins("C9"), IOStandard("LVCMOS33")),
    ("user_btn", 3, Pins("E9"), IOStandard("LVCMOS33")),

    ("serial", 0,
        Subsignal("tx", Pins("AB18")),
        Subsignal("rx", Pins("AA18")),
        IOStandard("LVCMOS33")
    ),
    ("serial", 1,
        Subsignal("tx", Pins("AA20")),
        Subsignal("rx", Pins("AB20")),
        IOStandard("LVCMOS33")
    ),

    ("lpddr5", 0,
        Subsignal("ck_n", Pins("Y2"), IOStandard("DIFF_HSUL_12")),
        Subsignal("ck_p", Pins("Y3"), IOStandard("DIFF_HSUL_12")),
        Subsignal("wck_n", Pins("V2"), IOStandard("DIFF_HSUL_12")), #  AB1
        Subsignal("wck_p", Pins("U2"), IOStandard("DIFF_HSUL_12")), #  AA1
        Subsignal("reset_n", Pins("AB3"), IOStandard("HSUL_12")),
        Subsignal("cs", Pins("V4 U3"), IOStandard("HSUL_12")),
        Subsignal("ca", Pins("T4 U5 W1 V3 W2 Y1 W4"), IOStandard("HSUL_12")),
        Subsignal("dq_out", Pins("K3 K2 K1 L1 N2 N5 N3 M3"), IOStandard("HSUL_12")),
        Subsignal("dq_in", Pins("P1 R1 P2 R2 T3 U1 P4 T1"), IOStandard("HSUL_12")),
        Subsignal("rdqs_n", Pins("M1"), IOStandard("DIFF_HSUL_12")), # N4
        Subsignal("rdqs_p", Pins("M2"), IOStandard("DIFF_HSUL_12")), # M5
        Subsignal("dmi_out", Pins("L3 AA3"), IOStandard("HSUL_12")),
        Subsignal("dmi_in", Pins("L5 AA4"), IOStandard("HSUL_12")),
     ),

    # RGMII Ethernet
    ("eth_ref_clk", 0, Pins("C12"), IOStandard("LVCMOS33")),
    ("eth_clocks", 0,
        Subsignal("tx", Pins("E17")),
        Subsignal("rx", Pins("C17")),
        IOStandard("LVCMOS33")
    ),
    ("eth", 0,
        Subsignal("rst_n",   Pins("E16"), IOStandard("LVCMOS33")),
        Subsignal("mdio",    Pins("C14"), IOStandard("LVCMOS33")),
        Subsignal("mdc",     Pins("B17"), IOStandard("LVCMOS33")),
        Subsignal("rx_ctl",  Pins("A16"), IOStandard("LVCMOS33")),
        Subsignal("rx_data", Pins("B16 A15 B15 A14"), IOStandard("LVCMOS33")),
        Subsignal("tx_ctl",  Pins("A13"), IOStandard("LVCMOS33")),
        Subsignal("tx_data", Pins("B21 B20 A19 A18"), IOStandard("LVCMOS33")),
    ),

    # HyperRAM
    ("hyperram", 0,
        Subsignal("clk",   Pins("AB15")),  # clk_n AB16
        Subsignal("rst_n", Pins("V17")),
        Subsignal("dq",    Pins("W15 AA15 AA14 W14 Y14 V15 Y16 W17")),
        Subsignal("cs_n",  Pins("AA16")),
        Subsignal("rwds",  Pins("Y17")),
        IOStandard("LVCMOS33")
    ),

    # SD Card
    ("sdcard", 0,
        Subsignal("data", Pins("D20 D19 C22 D21"), Misc("PULLUP True")),
        Subsignal("cmd",  Pins("C20"), Misc("PULLUP True")),
        Subsignal("clk",  Pins("D22")),
        Subsignal("cd",   Pins("B22")),
        Misc("SLEW=FAST"),
        IOStandard("LVCMOS33"),
    ),
]

# Platform -----------------------------------------------------------------------------------------

class Platform(Xilinx7SeriesPlatform):
    default_clk_name   = "clk100"
    default_clk_period = 1e9/100e6

    def __init__(self, device="xc7k70tfbg484-3", toolchain="vivado"):
        Xilinx7SeriesPlatform.__init__(self, device, _io, toolchain=toolchain)
        self.toolchain.bitstream_commands = \
            ["set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]"]
        self.toolchain.additional_commands = \
            ["write_cfgmem -force -format bin -interface spix4 -size 16 "
             "-loadbit \"up 0x0 {build_name}.bit\" -file {build_name}.bin"]

    def create_programmer(self):
        return OpenOCD("openocd_xc7_ft4232.cfg", "bscan_spi_xc7k70t.bit")

    def do_finalize(self, fragment):
        Xilinx7SeriesPlatform.do_finalize(self, fragment)
        self.add_period_constraint(self.lookup_request("clk100", loose=True), 1e9/100e6)
