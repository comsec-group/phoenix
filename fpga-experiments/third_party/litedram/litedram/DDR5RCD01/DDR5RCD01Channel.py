#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from migen import *
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01ControlCenter import DDR5RCD01ControlCenter
from litedram.DDR5RCD01.DDR5RCD01ResetGenerator import DDR5RCD01ResetGenerator
from litedram.DDR5RCD01.DDR5RCD01CommandLogic import DDR5RCD01CommandLogic
from litedram.DDR5RCD01.DDR5RCD01ActorMRW import DDR5RCD01ActorMRW
# from litedram.DDR5RCD01.DDR5RCD01Error import DDR5RCD01Error
from litedram.DDR5RCD01.DDR5RCD01InputBuffer import DDR5RCD01InputBuffer
from litedram.DDR5RCD01.DDR5RCD01RankBuffer import DDR5RCD01RankBuffer
from litedram.DDR5RCD01.DDR5RCD01CommandReceiveBlocker import DDR5RCD01CommandReceiveBlocker
from litedram.DDR5RCD01.DDR5RCD01CommandForwardBlocker import DDR5RCD01CommandForwardBlocker
from litedram.DDR5RCD01.DDR5RCD01DCATMAgent import DDR5RCD01DCATMAgent
from litedram.DDR5RCD01.DDR5RCD01DCSTMAgent import DDR5RCD01DCSTMAgent
from litedram.DDR5RCD01.DDR5RCD01ErrorArbiter import DDR5RCD01ErrorArbiter


class DDR5RCD01Channel(Module):
    """TODO DDR5 RCD01 Channel
        The RCD Channel implements 2 Rank Buffers

    Module
    ------
    <interface> : CS,CA,etc.
    dck, dck_pll
    """

    def __init__(self,
                 if_ibuf,
                 if_clks_i,
                 if_obuf,
                 if_sdram,
                 if_bcom,
                 if_ctrl_global,
                 if_config_global,
                 if_common,
                 if_ctrl_common,
                 if_config_common,
                 if_regs,
                 is_master=True,
                 ):
        """
            Master is the one providing global settings
        """
        if is_master:
            # Drive the ctrl and common interfaces
            # TODO
            pass
        else:
            pass

        """
            Split clock inputs
        """
        if_clk_rowA_rankA = If_ck()
        self.comb += if_clk_rowA_rankA.ck_t.eq(if_clks_i.ck_t[3])
        self.comb += if_clk_rowA_rankA.ck_c.eq(if_clks_i.ck_c[3])

        if_clk_rowB_rankA = If_ck()
        self.comb += if_clk_rowB_rankA.ck_t.eq(if_clks_i.ck_t[2])
        self.comb += if_clk_rowB_rankA.ck_c.eq(if_clks_i.ck_c[2])

        if_clk_rowA_rankB = If_ck()
        self.comb += if_clk_rowA_rankB.ck_t.eq(if_clks_i.ck_t[1])
        self.comb += if_clk_rowA_rankB.ck_c.eq(if_clks_i.ck_c[1])

        if_clk_rowB_rankB = If_ck()
        self.comb += if_clk_rowB_rankB.ck_t.eq(if_clks_i.ck_t[0])
        self.comb += if_clk_rowB_rankB.ck_c.eq(if_clks_i.ck_c[0])
        """
            Input Buffer
        """
        if_ctrl_ibuf = If_ctrl_ibuf()
        if_ibuf_o = If_ibuf()
        xibuf = DDR5RCD01InputBuffer(
            if_ib_i=if_ibuf,
            if_ib_o=if_ibuf_o,
            if_ctrl=if_ctrl_ibuf
        )
        self.submodules.xibuf = xibuf

        """
            Receive commands blocker
        """
        if_ibuf_rx_blocker_o = If_ibuf()
        if_ctrl_rx_block = If_ctrl_blocker()
        xreceive_blocker = DDR5RCD01CommandReceiveBlocker(
            if_ibuf=if_ibuf_o,
            if_ibuf_o=if_ibuf_rx_blocker_o,
            if_ctrl=if_ctrl_rx_block,
        )
        self.submodules.xreceive_blocker = xreceive_blocker
        """
            Command Logic : Rank A
        """
        if_csca_o = If_ibuf()
        if_csca_o_rank_A = If_ibuf()
        if_csca_o_rank_B = If_ibuf()

        if_ctrl_lbuf_row_A_rankA = If_ctrl_lbuf()
        if_ctrl_lbuf_row_B_rankA = If_ctrl_lbuf()

        if_ctrl_lbuf_row_A_rankB = If_ctrl_lbuf()
        if_ctrl_lbuf_row_B_rankB = If_ctrl_lbuf()

        if_register = If_registers()

        parity_error_o = Signal()
        if_ctrl_cmd_logic = If_ctrl_cmd_logic()

        xcmd_logic = DDR5RCD01CommandLogic(
            if_ibuf_i=if_ibuf_rx_blocker_o,
            if_csca_o=if_csca_o,
            if_csca_o_rank_A=if_csca_o_rank_A,
            if_csca_o_rank_B=if_csca_o_rank_B,
            if_ctrl_lbuf_rank_A_row_A=if_ctrl_lbuf_row_A_rankA,
            if_ctrl_lbuf_rank_A_row_B=if_ctrl_lbuf_row_B_rankA,
            if_ctrl_lbuf_rank_B_row_A=if_ctrl_lbuf_row_A_rankB,
            if_ctrl_lbuf_rank_B_row_B=if_ctrl_lbuf_row_B_rankB,
            if_register=if_register,
            rw_is_output_inversion_enabled=if_ctrl_cmd_logic.is_output_inversion_en,
            rw_is_parity_checking_enabled=if_ctrl_cmd_logic.is_parity_checking_en,
            parity_error=parity_error_o,
        )
        self.submodules.xcmd_logic = xcmd_logic

        """
             Rank Buffer A
        """
        if_obuf_csca_row_A_rankA = If_bus_csca_o()
        if_obuf_csca_row_B_rankA = If_bus_csca_o()

        if_ctrl_obuf_csca_row_A_rankA = If_ctrl_obuf_CSCA()
        if_ctrl_obuf_csca_row_B_rankA = If_ctrl_obuf_CSCA()
        if_ctrl_obuf_clks_row_A_rankA = If_ctrl_obuf_CLKS()
        if_ctrl_obuf_clks_row_B_rankA = If_ctrl_obuf_CLKS()

        if_obuf_clks_row_A_rankA = If_ck()
        if_obuf_clks_row_B_rankA = If_ck()

        if_csca_rank_A = If_bus_csca()

        self.comb += if_csca_rank_A.cs_n.eq(if_csca_o_rank_A.dcs_n)
        self.comb += if_csca_rank_A.ca.eq(if_csca_o_rank_A.dca)

        if_csca_rank_A_o = If_bus_csca()
        if_ctrl_fwd_block_A = If_ctrl_blocker()
        if_clk_rowA_rankA_o = If_ck()
        if_clk_rowB_rankA_o = If_ck()

        xfwd_blocker_A = DDR5RCD01CommandForwardBlocker(
            if_ibuf=if_csca_rank_A,
            if_clk_row_A=if_clk_rowA_rankA,
            if_clk_row_B=if_clk_rowB_rankA,
            if_ibuf_o=if_csca_rank_A_o,
            if_clk_row_A_o=if_clk_rowA_rankA_o,
            if_clk_row_B_o=if_clk_rowB_rankA_o,
            if_ctrl=if_ctrl_fwd_block_A,
        )
        self.submodules.xfwd_blocker_A = xfwd_blocker_A

        xrankA = DDR5RCD01RankBuffer(
            if_ibuf=if_csca_rank_A_o,
            if_clk_row_A=if_clk_rowA_rankA_o,
            if_clk_row_B=if_clk_rowB_rankA_o,
            if_obuf_csca_row_A=if_obuf_csca_row_A_rankA,
            if_obuf_csca_row_B=if_obuf_csca_row_B_rankA,
            if_obuf_clks_row_A=if_obuf_clks_row_A_rankA,
            if_obuf_clks_row_B=if_obuf_clks_row_B_rankA,
            if_ctrl_lbuf_row_A=if_ctrl_lbuf_row_A_rankA,
            if_ctrl_lbuf_row_B=if_ctrl_lbuf_row_B_rankA,
            if_ctrl_obuf_csca_row_A=if_ctrl_obuf_csca_row_A_rankA,
            if_ctrl_obuf_csca_row_B=if_ctrl_obuf_csca_row_B_rankA,
            if_ctrl_obuf_clks_row_A=if_ctrl_obuf_clks_row_A_rankA,
            if_ctrl_obuf_clks_row_B=if_ctrl_obuf_clks_row_B_rankA,
        )
        self.submodules.xrankA = xrankA

        self.comb += if_obuf.qacs_a_n.eq(if_obuf_csca_row_A_rankA.qcs_n)
        self.comb += if_obuf.qaca_a.eq(if_obuf_csca_row_A_rankA.qca)
        self.comb += if_obuf.qacs_b_n.eq(if_obuf_csca_row_B_rankA.qcs_n)
        self.comb += if_obuf.qaca_b.eq(if_obuf_csca_row_B_rankA.qca)

        self.comb += if_obuf.qack_t.eq(if_obuf_clks_row_A_rankA.ck_t)
        self.comb += if_obuf.qack_c.eq(if_obuf_clks_row_A_rankA.ck_c)

        self.comb += if_obuf.qbck_t.eq(if_obuf_clks_row_B_rankA.ck_t)
        self.comb += if_obuf.qbck_c.eq(if_obuf_clks_row_B_rankA.ck_c)

        """
            Rank B
        """

        if_ctrl_obuf_csca_row_A_rankB = If_ctrl_obuf_CSCA()
        if_ctrl_obuf_csca_row_B_rankB = If_ctrl_obuf_CSCA()
        if_ctrl_obuf_clks_row_A_rankB = If_ctrl_obuf_CLKS()
        if_ctrl_obuf_clks_row_B_rankB = If_ctrl_obuf_CLKS()

        if_obuf_csca_row_A_rankB = If_bus_csca_o()
        if_obuf_csca_row_B_rankB = If_bus_csca_o()

        if_obuf_clks_row_A_rankB = If_ck()
        if_obuf_clks_row_B_rankB = If_ck()

        if_csca_rank_B = If_bus_csca()
        self.comb += if_csca_rank_B.cs_n.eq(if_csca_o_rank_B.dcs_n)
        self.comb += if_csca_rank_B.ca.eq(if_csca_o_rank_B.dca)

        if_csca_rank_B_o = If_bus_csca()
        if_ctrl_fwd_block_B = If_ctrl_blocker()
        if_clk_rowA_rankB_o = If_ck()
        if_clk_rowB_rankB_o = If_ck()

        xfwd_blocker_B = DDR5RCD01CommandForwardBlocker(
            if_ibuf=if_csca_rank_B,
            if_clk_row_A=if_clk_rowA_rankB,
            if_clk_row_B=if_clk_rowB_rankB,
            if_ibuf_o=if_csca_rank_B_o,
            if_clk_row_A_o=if_clk_rowA_rankB_o,
            if_clk_row_B_o=if_clk_rowB_rankB_o,
            if_ctrl=if_ctrl_fwd_block_B,
        )
        self.submodules.xfwd_blocker_B = xfwd_blocker_B

        xrankB = DDR5RCD01RankBuffer(
            if_ibuf=if_csca_rank_B_o,
            if_clk_row_A=if_clk_rowA_rankB_o,
            if_clk_row_B=if_clk_rowB_rankB_o,
            if_obuf_csca_row_A=if_obuf_csca_row_A_rankB,
            if_obuf_csca_row_B=if_obuf_csca_row_B_rankB,
            if_obuf_clks_row_A=if_obuf_clks_row_A_rankB,
            if_obuf_clks_row_B=if_obuf_clks_row_B_rankB,
            if_ctrl_lbuf_row_A=if_ctrl_lbuf_row_A_rankB,
            if_ctrl_lbuf_row_B=if_ctrl_lbuf_row_B_rankB,
            if_ctrl_obuf_csca_row_A=if_ctrl_obuf_csca_row_A_rankB,
            if_ctrl_obuf_csca_row_B=if_ctrl_obuf_csca_row_B_rankB,
            if_ctrl_obuf_clks_row_A=if_ctrl_obuf_clks_row_A_rankB,
            if_ctrl_obuf_clks_row_B=if_ctrl_obuf_clks_row_B_rankB,
        )
        self.submodules.xrankB = xrankB

        self.comb += if_obuf.qbcs_a_n.eq(if_obuf_csca_row_A_rankB.qcs_n)
        self.comb += if_obuf.qbca_a.eq(if_obuf_csca_row_A_rankB.qca)
        self.comb += if_obuf.qbcs_b_n.eq(if_obuf_csca_row_B_rankB.qcs_n)
        self.comb += if_obuf.qbca_b.eq(if_obuf_csca_row_B_rankB.qca)

        self.comb += if_obuf.qcck_t.eq(if_obuf_clks_row_A_rankB.ck_t)
        self.comb += if_obuf.qcck_c.eq(if_obuf_clks_row_A_rankB.ck_c)

        self.comb += if_obuf.qdck_t.eq(if_obuf_clks_row_B_rankB.ck_t)
        self.comb += if_obuf.qdck_c.eq(if_obuf_clks_row_B_rankB.ck_c)

        """
            DCSTM Agent
        """
        dcstm_sample_o = Signal()
        if_ctrl_dcstm_agent = If_ctrl_dcstm_agent()
        xdcstm_agent = DDR5RCD01DCSTMAgent(
            if_ibuf=if_ibuf_o,
            sample_o=dcstm_sample_o,
            if_ctrl=if_ctrl_dcstm_agent,
        )
        self.submodules.xdcstm_agent = xdcstm_agent

        """
            DCATM Agent
        """
        dcatm_sample_o = Signal()
        if_ctrl_dcatm_agent = If_ctrl_dcatm_agent()

        xdcatm_agent = DDR5RCD01DCATMAgent(
            if_ibuf=if_ibuf_o,
            sample_o=dcatm_sample_o,
            if_ctrl=if_ctrl_dcatm_agent,
        )
        self.submodules.xdcatm_agent = xdcatm_agent

        """
            This is hard-connected to alert, which means that
            host training can only be done through the ALERT_n pin
            TODO reconnect to allow loopback, if needed
        """
        if_ctrl_error_arbiter = If_ctrl_error_arbiter()
        xerror_arbiter = DDR5RCD01ErrorArbiter(
            parity_error=parity_error_o,
            sdram_error=if_sdram.derror_in_n,
            dcstm_sample=dcstm_sample_o,
            dcatm_sample=dcatm_sample_o,
            error_o=if_common.derror_in_n,
            if_ctrl=if_ctrl_error_arbiter,
        )
        self.submodules.xerror_arbiter = xerror_arbiter

        """
            Control Center
        """
        drst_rw04 = Signal(reset=~0)
        drst_pon = Signal(reset=~0)

        xcontrol_center = DDR5RCD01ControlCenter(
            if_ibuf=if_ibuf_o,
            if_ctrl_ibuf=if_ctrl_ibuf,
            if_ctrl_lbuf_row_A_rankA=if_ctrl_lbuf_row_A_rankA,
            if_ctrl_lbuf_row_B_rankA=if_ctrl_lbuf_row_B_rankA,
            if_ctrl_obuf_csca_row_A_rankA=if_ctrl_obuf_csca_row_A_rankA,
            if_ctrl_obuf_csca_row_B_rankA=if_ctrl_obuf_csca_row_B_rankA,
            if_ctrl_obuf_clks_row_A_rankA=if_ctrl_obuf_clks_row_A_rankA,
            if_ctrl_obuf_clks_row_B_rankA=if_ctrl_obuf_clks_row_B_rankA,
            if_ctrl_lbuf_row_A_rankB=if_ctrl_lbuf_row_A_rankB,
            if_ctrl_lbuf_row_B_rankB=if_ctrl_lbuf_row_B_rankB,
            if_ctrl_obuf_csca_row_A_rankB=if_ctrl_obuf_csca_row_A_rankB,
            if_ctrl_obuf_csca_row_B_rankB=if_ctrl_obuf_csca_row_B_rankB,
            if_ctrl_obuf_clks_row_A_rankB=if_ctrl_obuf_clks_row_A_rankB,
            if_ctrl_obuf_clks_row_B_rankB=if_ctrl_obuf_clks_row_B_rankB,
            if_register=if_register,
            drst_rw04=drst_rw04,
            drst_pon=drst_pon,
            if_ctrl_global=if_ctrl_global,
            if_config_global=if_config_global,
            if_common=if_common,
            if_ctrl_common=if_ctrl_common,
            if_config_common=if_config_common,
            if_regs=if_regs,
            if_ctrl_rx_block=if_ctrl_rx_block,
            if_ctrl_fwd_block_A=if_ctrl_fwd_block_A,
            if_ctrl_fwd_block_B=if_ctrl_fwd_block_B,
            if_ctrl_dcstm_agent=if_ctrl_dcstm_agent,
            if_ctrl_dcatm_agent=if_ctrl_dcatm_agent,
            if_ctrl_error_arbiter=if_ctrl_error_arbiter,
            if_ctrl_cmd_logic=if_ctrl_cmd_logic,
            is_channel_A=is_master,
        )
        self.submodules.xcontrol_center = xcontrol_center

        xreset_generator = DDR5RCD01ResetGenerator(
            drst_n=if_common.qrst_n,
            drst_pon=drst_pon,
            drst_rw04=drst_rw04,
            qrst_n=if_sdram.qrst_n,
        )
        self.submodules.xreset_generator = xreset_generator


class TestBed(Module):
    def __init__(self):
        self.submodules.dut = DDR5RCD01Channel()


def run_test(dut):
    logging.debug('Write test')
    yield
    logging.debug('Yield from write test.')


def behav_write_word(data):
    yield


if __name__ == "__main__":
    raise NotSupportedException
