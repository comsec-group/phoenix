#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from operator import xor
from migen import *
from migen.fhdl import verilog
# RCD
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01Channel import DDR5RCD01Channel
from litedram.DDR5RCD01.DDR5RCD01Common import DDR5RCD01Common


class DDR5RCD01Core(Module):
    """DDR5 RCD01 Core
    TODO Documentation
    Primary function of the Core is to buffer the Command/Address (CA) bus, chip selects and clock
    between the host controller and the DRAMs
    In the LRDIMM use case, a BCOM bus is created to communicate with the data buffers.

    The Core consists of 2 independent channels and some common logic, e.g.: clocking.

    The term "Definition X.Y.Z" refers to the X.Y.Z section of the JEDEC Standard DDR5 Registering
    Clock Driver Definition (DDR5RCD01).

    """

    def __init__(self,
                 if_ck_rst,
                 if_sdram_A,
                 if_sdram_B,
                 if_alert_n,
                 if_ibuf_A,
                 if_ibuf_B,
                 if_obuf_A,
                 if_obuf_B,
                 if_lb,
                 if_bcom_A,
                 if_bcom_B,
                 if_regs_A,
                 if_regs_B,
                 is_dual_channel=True):

        if_pll = If_ck(n_clks=4)
        if_common_A = If_channel_sdram()
        if_common_B = If_channel_sdram()
        if_ctrl_common = If_ctrl_common()
        if_config_common = If_config_common()

        """
            Channel A is master of global configuration, chanel B is slave
        """
        is_channel_A_master = True
        if_ctrl_global = If_config_global()
        if_config_global = If_config_global()

        xchannel_A = DDR5RCD01Channel(
            if_ibuf=if_ibuf_A,
            if_clks_i=if_pll,
            if_obuf=if_obuf_A,
            if_sdram=if_sdram_A,
            if_bcom=if_bcom_A,
            if_ctrl_global=if_ctrl_global,
            if_config_global=if_config_global,
            if_common=if_common_A,
            if_ctrl_common=if_ctrl_common,
            if_config_common=if_config_common,
            if_regs=if_regs_A,
            is_master=is_channel_A_master,
        )
        self.submodules.xchannel_A = xchannel_A

        """
            Channel B
        """
        if is_dual_channel:
            is_channel_B_master = False
            xchannel_B = DDR5RCD01Channel(
                if_ibuf=if_ibuf_B,
                if_clks_i=if_pll,
                if_obuf=if_obuf_B,
                if_sdram=if_sdram_B,
                if_bcom=if_bcom_B,
                if_ctrl_global=if_ctrl_global,
                if_config_global=if_config_global,
                if_common=if_common_B,
                if_ctrl_common=None,
                if_config_common=None,
                if_regs=if_regs_B,
                is_master=is_channel_B_master,
            )
            self.submodules.xchannel_B = xchannel_B

        """
            Common
        """
        xcommon = DDR5RCD01Common(
            if_host_ck_rst=if_ck_rst,
            if_host_alert_n=if_alert_n,
            if_host_lb=if_lb,
            if_pll=if_pll,
            if_channel_A=if_common_A,
            if_channel_B=if_common_B,
            if_ctrl_common=if_ctrl_common,
            if_config_common=if_config_common,
        )
        self.submodules.xcommon = xcommon

        """
            Sideband
        """
        #TODO Implement


class TestBed(Module):
    def __init__(self):
        self.if_ck_rst = If_ck_rst()
        self.if_sdram_A = If_channel_sdram()
        self.if_sdram_B = If_channel_sdram()
        self.if_alert_n = If_alert_n()
        self.if_ibuf_A = If_ibuf()
        self.if_ibuf_B = If_ibuf()
        self.if_obuf_A = If_obuf()
        self.if_obuf_B = If_obuf()
        self.if_lb = If_lb()
        self.if_bcom_A = If_bcom()
        self.if_bcom_B = If_bcom()
        self.if_sideband = If_sideband()
        self.is_dual_channel = False

        self.submodules.dut = DDR5RCD01Core(
            if_ck_rst=self.if_ck_rst,
            if_sdram_A=self.if_sdram_A,
            if_sdram_B=self.if_sdram_B,
            if_alert_n=self.if_alert_n,
            if_ibuf_A=self.if_ibuf_A,
            if_ibuf_B=self.if_ibuf_B,
            if_obuf_A=self.if_obuf_A,
            if_obuf_B=self.if_obuf_B,
            if_lb=self.if_lb,
            if_bcom_A=self.if_bcom_A,
            if_bcom_B=self.if_bcom_B,
            if_sideband=self.if_sideband,
            is_dual_channel=self.is_dual_channel,
        )


def seq_cmds(tb):
    # TODO all commands are passed as if they were 2UIs long. To be fixed.
    # Single UI command
    yield from n_ui_dram_command(tb, nums=[0x01, 0x02], sel_cs="rank_AB")
    # 2 UI commands
    yield from n_ui_dram_command(tb, nums=[0x01, 0x02, 0x03, 0x04], sel_cs="rank_A")
    yield from n_ui_dram_command(tb, nums=[0xC0, 0xDE, 0xF0, 0x0D], sel_cs="rank_B")
    yield from n_ui_dram_command(tb, nums=[0xC0, 0xDE, 0xF0, 0x0D], sel_cs="rank_AB")
    yield from n_ui_dram_command(tb, nums=[0x0A, 0x0B, 0x0C, 0x0D], non_target_termination=True)
    yield from n_ui_dram_command(tb, nums=[0xDE, 0xAD, 0xBA, 0xBE], non_target_termination=True)
    yield from n_ui_dram_command(tb, nums=[0xC0, 0xDE, 0xF0, 0x0D], sel_cs="rank_AB")


def n_ui_dram_command(tb, nums, sel_cs="rank_AB", non_target_termination=False):
    """
    This function drives the interface with as in:
        "JEDEC 82-511 Figure 7
        One UI DRAM Command Timing Diagram"

    Nums can be any length to incorporate two, or more, UI commands

    The non target termination parameter extends the DCS assertion to the 2nd UI
    """
    if sel_cs == "rank_A":
        cs = 0b10
    elif sel_cs == "rank_B":
        cs = 0b01
    elif sel_cs == "rank_AB":
        cs = 0b00
    else:
        cs = 0b11

    SEQ_INACTIVE = [~0, 0]
    yield from drive_init(tb)
    # yield from set_parity(tb)

    sequence = [SEQ_INACTIVE]
    for id, num in enumerate(nums):
        if non_target_termination:
            if id in [0, 1, 2, 3]:
                sequence.append([cs, num])
            else:
                sequence.append([0b11, num])
        else:
            if id in [0, 1]:
                sequence.append([cs, num])
            else:
                sequence.append([0b11, num])

    sequence.append(SEQ_INACTIVE)

    for seq_cs, seq_ca in sequence:
        logging.debug(str(seq_cs) + " " + str(seq_ca))
        yield from drive_cs_ca(seq_cs, seq_ca)
    for i in range(3):
        yield


def drive_init(tb):
    yield tb.if_ck_rst.drst_n.eq(1)
    yield from drive_cs_ca(~0, 0)


def drive_cs_ca(cs, ca):
    yield tb.if_ibuf_A.dcs_n.eq(cs)
    yield tb.if_ibuf_A.dca.eq(ca)
    yield


# def set_parity(tb):
#     yield tb.pi.A_dpar.eq(reduce(xor, [tb.pi.A_dca[bit] for bit in range(len(tb.pi.A_dca))]))


def run_test(tb):
    logging.debug('Write test')
    # yield from one_ui_dram_command(tb)
    INIT_CYCLES = CW_DA_REGS_NUM + 5
    yield from drive_init(tb)
    for i in range(INIT_CYCLES):
        yield
    yield from seq_cmds(tb)
    for i in range(5):
        yield
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest(level=logging.INFO)
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready. Simulating with migen...")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
