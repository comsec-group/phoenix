#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2021 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from litex.build.generic_platform import *
from litex.build.xilinx import Xilinx7SeriesPlatform
from litex.build.openocd import OpenOCD

# IOs ----------------------------------------------------------------------------------------------

_io = [
    ("clk100", 0, Pins("C12"), IOStandard("LVCMOS33")),

    ("user_led", 0, Pins("D21"), IOStandard("LVCMOS33")),
    ("user_led", 1, Pins("B20"), IOStandard("LVCMOS33")),
    ("user_led", 2, Pins("B21"), IOStandard("LVCMOS33")),
    ("user_led", 3, Pins("C22"), IOStandard("LVCMOS33")),
    ("user_led", 4, Pins("E22"), IOStandard("LVCMOS33")),

    ("hot_swap_yellow", 0, Pins("A20"), IOStandard("LVCMOS33")),
    ("hot_swap_red", 0, Pins("E21"), IOStandard("LVCMOS33")),
    ("hot_swap_green", 0, Pins("D23"), IOStandard("LVCMOS33")),
    ("hot_swap_button", 0, Pins("C21"), IOStandard("LVCMOS33")),

    ("prsnt_m2c", 0, Pins("E23"), IOStandard("LVCMOS33")),
    ("fmc_sda_3v3", 0, Pins("G24"), IOStandard("LVCMOS33")),
    ("fmc_scl_3v3", 0, Pins("H22"), IOStandard("LVCMOS33")),
    ("clk_dir", 0, Pins("F24"), IOStandard("LVCMOS33")),

    ("fpga_power_cycle", 0, Pins("G26"), IOStandard("LVCMOS33")),
    ("fpga_slp_s4", 0, Pins("J26"), IOStandard("LVCMOS33")),
    ("fpga_vtt_cntl", 0, Pins("H26"), IOStandard("LVCMOS33")),

    ("serial", 0,
        Subsignal("tx", Pins("E26")),
        Subsignal("rx", Pins("F25")),
        IOStandard("LVCMOS33")
    ),

    ("spiflash4x", 0,  # clock needs to be accessed through STARTUPE2
        Subsignal("cs_n", Pins("C23")),
        Subsignal("dq",   Pins("B24", "A25", "B22", "A22")),
        IOStandard("LVCMOS33")
    ),

    # DDR4
    ("ddr4", 0,
        Subsignal("a",       Pins(
            "AF10 AC11 AD11 AD10 AC9  AD9  AB9  AF7  AE8",
            "AE7  Y12  AB7  AC7  AD13"),
            IOStandard("SSTL12_DCI")),
        Subsignal("ba",      Pins("AB11 AB10"), IOStandard("SSTL12_DCI")),
        Subsignal("bg",      Pins("AA9 AF9"),   IOStandard("SSTL12_DCI")),
        Subsignal("ras_n",   Pins("AA12"),      IOStandard("SSTL12_DCI")), # A16
        Subsignal("cas_n",   Pins("AF13"),      IOStandard("SSTL12_DCI")), # A15
        Subsignal("we_n",    Pins("AA13"),      IOStandard("SSTL12_DCI")), # A14
        Subsignal("cs_n",    Pins("V9"),        IOStandard("SSTL12_DCI")),
        Subsignal("act_n",   Pins("Y8"),        IOStandard("SSTL12_DCI")),
        Subsignal("alert_n", Pins("AE10"),      IOStandard("LVCMOS12"), Misc("PULLUP True")),
        Subsignal("par",     Pins("AE13"),      IOStandard("SSTL12_DCI")),
        Subsignal("dq",      Pins(
                "U5   V6   AB6  AC6  U7   U6   AA5  AB5",
                "U2   Y3   AC3  AC4  W4   V4   AA4  AB4",
                "V1   Y2   AC2  AE1  U1   V2   AB2  AD1",
                "AE3  AF3  AD5  AD6  AE2  AF2  AE5  AE6",
                "AF15 AE16 AF19 AF20 AF14 AD14 AF18 AE18",
                "AB14 AD19 AC16 AB15 AC14 AD16 AC19 AC17",
                "AA15 AB17 AA19 AA20 AA14 AB16 AB19 AB20",
                "V14  Y16  W19  V19  W14  Y15  W18  V18",
                ),
            IOStandard("SSTL12_T_DCI")),
        Subsignal("dqs_p",   Pins(
                "Y6 W6 AA3 V3 AB1 W1 AF5 AD4",
                "AE17 AD15 AC18 AD20 Y17 AA17 V16 W15"),
            IOStandard("DIFF_SSTL12_T_DCI")),
        Subsignal("dqs_n",   Pins(
                "Y5 W5 AA2 W3 AC1 Y1 AF4 AD3",
                "AF17 AE15 AD18 AE20 Y18 AA18 V17 W16"),
            IOStandard("DIFF_SSTL12_T_DCI")),
        Subsignal("clk_p",   Pins("AE12"), IOStandard("DIFF_SSTL12_DCI")),
        Subsignal("clk_n",   Pins("AF12"), IOStandard("DIFF_SSTL12_DCI")),
        Subsignal("cke",     Pins("AA8"), IOStandard("SSTL12_DCI")), # also AM15 for larger SODIMMs
        Subsignal("odt",     Pins("Y13"), IOStandard("SSTL12_DCI")), # also AM16 for larger SODIMMs
        Subsignal("reset_n", Pins("AF8"), IOStandard("SSTL12")),
        Subsignal("ddr_presence",Pins("AF22"), IOStandard("LVCMOS33")),
        Misc("SLEW=FAST"),
    ),
    # RGMII Ethernet
    ("eth_ref_clk", 0, Pins("AA23"), IOStandard("LVCMOS33")),
    ("eth_clocks", 0,
        Subsignal("rx", Pins("Y23")),
        Subsignal("tx", Pins("AA24")),
        IOStandard("LVCMOS33")
    ),
    ("eth", 0,
        Subsignal("rst_n",   Pins("AA22")),
        Subsignal("mdio",    Pins("AB26")),
        Subsignal("mdc",     Pins("AA25")),
        Subsignal("rx_ctl",  Pins("Y25")),
        Subsignal("rx_data", Pins("W26 W25 V26 U25")),
        Subsignal("tx_ctl",  Pins("U26")),
        Subsignal("tx_data", Pins("W24 Y26 Y22 Y21")),
        Subsignal("eth_sel", Pins("U24")),
        IOStandard("LVCMOS33")
    ),

    # HyperRAM
    ("hyperram", 0,
        Subsignal("clk", Pins("AD26")), # clk_n AE26
        Subsignal("rst_n", Pins("AC24")),
        Subsignal("cs_n",  Pins("AC26")),
        Subsignal("dq",    Pins("AE23 AD25 AF24 AE22 AF23 AF25 AE25 AD24")),
        Subsignal("rwds",  Pins("AD23")),
        IOStandard("LVCMOS33")
    ),

    # SD Card
    ("sdcard", 0,
        Subsignal("data", Pins("E10 F8 C9 D9"), Misc("PULLUP True")),
        Subsignal("cmd",  Pins("D8"), Misc("PULLUP True")),
        Subsignal("clk",  Pins("D10")),
        Subsignal("cd",   Pins("F9")),
        Misc("SLEW=FAST"),
        IOStandard("LVCMOS33"),
    ),

    # I2C
    ("i2c", 0,
        Subsignal("scl", Pins("E25")),
        Subsignal("sda", Pins("D26")),
        IOStandard("LVCMOS33"),
    ),

    # HDMI Out
    ("hdmi_out", 0,
        Subsignal("clk_p",   Pins("B15"),   IOStandard("TMDS_33")),
        Subsignal("clk_n",   Pins("A15"),   IOStandard("TMDS_33")),
        Subsignal("data0_p", Pins("B14"),   IOStandard("TMDS_33")),
        Subsignal("data0_n", Pins("A14"),   IOStandard("TMDS_33")),
        Subsignal("data1_p", Pins("A13"),  IOStandard("TMDS_33")),
        Subsignal("data1_n", Pins("A12"),  IOStandard("TMDS_33")),
        Subsignal("data2_p", Pins("B10"),  IOStandard("TMDS_33")),
        Subsignal("data2_n", Pins("A10"),  IOStandard("TMDS_33")),
    ),
]

# Platform -----------------------------------------------------------------------------------------

class Platform(Xilinx7SeriesPlatform):
    default_clk_name   = "clk100"
    default_clk_period = 1e9/100e6

    def __init__(self, device="xc7k160tffg676-3", toolchain="vivado"):
        Xilinx7SeriesPlatform.__init__(self, device, _io, toolchain=toolchain)
        self.toolchain.bitstream_commands = \
            ["set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 4 [current_design]"]
        self.toolchain.additional_commands = \
            ["write_cfgmem -force -format bin -interface spix4 -size 16 "
             "-loadbit \"up 0x0 {build_name}.bit\" -file {build_name}.bin"]
        self.add_platform_command("set_property INTERNAL_VREF 0.6 [get_iobanks 32]")
        self.add_platform_command("set_property INTERNAL_VREF 0.6 [get_iobanks 33]")
        self.add_platform_command("set_property INTERNAL_VREF 0.6 [get_iobanks 34]")
        self.add_platform_command("set_property DCI_CASCADE {{32 34}} [get_iobanks 33]")

    def create_programmer(self):
        bscan_spi = "bscan_spi_xc7k160t.bit" if "xc7k160t" in self.device else "bscan_spi_xc7k160t.bit"
        return OpenOCD("openocd_xc7_ft4232.cfg", bscan_spi)

    def do_finalize(self, fragment):
        Xilinx7SeriesPlatform.do_finalize(self, fragment)
        self.add_period_constraint(self.lookup_request("clk100", loose=True), 1e9/100e6)
