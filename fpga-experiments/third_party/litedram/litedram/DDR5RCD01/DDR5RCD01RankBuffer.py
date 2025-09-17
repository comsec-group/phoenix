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
from litedram.DDR5RCD01.RCD_utils import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01RowBuffer import DDR5RCD01RowBuffer


class DDR5RCD01RankBuffer(Module):
    """DDR5 RCD01 Rank Buffer
    TODO
    Rank buffer is a wrapper for the line buffers to encapsulate 2 rows.

    Rank Buffer:
        Line buffer row A
        Line buffer row B

    Module
    ------
    TODO Explain interfaces
    """

    def __init__(self,
                 if_ibuf,
                 if_clk_row_A,
                 if_clk_row_B,
                 if_obuf_csca_row_A,
                 if_obuf_csca_row_B,
                 if_obuf_clks_row_A,
                 if_obuf_clks_row_B,
                 if_ctrl_lbuf_row_A,
                 if_ctrl_lbuf_row_B,
                 if_ctrl_obuf_csca_row_A,
                 if_ctrl_obuf_csca_row_B,
                 if_ctrl_obuf_clks_row_A,
                 if_ctrl_obuf_clks_row_B,
                 ):

        xrowA = DDR5RCD01RowBuffer(
            if_ibuf=if_ibuf,
            if_pll_clk=if_clk_row_A,
            if_obuf_csca=if_obuf_csca_row_A,
            if_obuf_clks=if_obuf_clks_row_A,
            if_ctrl_lbuf=if_ctrl_lbuf_row_A,
            if_ctrl_obuf=if_ctrl_obuf_csca_row_A,
            if_ctrl_clk=if_ctrl_obuf_clks_row_A,
        )
        self.submodules += xrowA

        xrowB = DDR5RCD01RowBuffer(
            if_ibuf=if_ibuf,
            if_pll_clk=if_clk_row_B,
            if_obuf_csca=if_obuf_csca_row_B,
            if_obuf_clks=if_obuf_clks_row_B,
            if_ctrl_lbuf=if_ctrl_lbuf_row_B,
            if_ctrl_obuf=if_ctrl_obuf_csca_row_B,
            if_ctrl_clk=if_ctrl_obuf_clks_row_B,
        )
        self.submodules += xrowB


class TestBed(Module):
    def __init__(self):
        self.if_ibuf = If_bus_csca()
        self.if_clk_row_A = If_ck()
        self.if_clk_row_B = If_ck()
        self.if_obuf_csca_row_A = If_bus_csca_o()
        self.if_obuf_csca_row_B = If_bus_csca_o()
        self.if_obuf_clk_row_A = If_ck()
        self.if_obuf_clk_row_B = If_ck()
        self.if_ctrl_lbuf_row_A = If_ctrl_lbuf()
        self.if_ctrl_lbuf_row_B = If_ctrl_lbuf()
        self.if_ctrl_obuf_csca_row_A = If_ctrl_obuf_CSCA()
        self.if_ctrl_obuf_csca_row_B = If_ctrl_obuf_CSCA()
        self.if_ctrl_obuf_clks_row_A = If_ctrl_obuf_CLKS()
        self.if_ctrl_obuf_clks_row_B = If_ctrl_obuf_CLKS()

        self.submodules.dut = DDR5RCD01RankBuffer(
            if_ibuf=self.if_ibuf,
            if_clk_row_A=self.if_clk_row_A,
            if_clk_row_B=self.if_clk_row_B,
            if_obuf_csca_row_A=self.if_obuf_csca_row_A,
            if_obuf_csca_row_B=self.if_obuf_csca_row_B,
            if_obuf_clk_row_A=self.if_obuf_clk_row_A,
            if_obuf_clk_row_B=self.if_obuf_clk_row_B,
            if_ctrl_lbuf_row_A=self.if_ctrl_lbuf_row_A,
            if_ctrl_lbuf_row_B=self.if_ctrl_lbuf_row_B,
            if_ctrl_obuf_csca_row_A=self.if_ctrl_obuf_csca_row_A,
            if_ctrl_obuf_csca_row_B=self.if_ctrl_obuf_csca_row_B,
            if_ctrl_obuf_clks_row_A=self.if_ctrl_obuf_clks_row_A,
            if_ctrl_obuf_clks_row_B=self.if_ctrl_obuf_clks_row_B,
        )


def run_test(dut):
    logging.debug('Write test')
    # yield from dut.regfile.pretty_print_regs()
    # yield from behav_write_word(0x0,0x0,0x0)
    for i in range(5):
        yield
    logging.debug('Yield from write test.')


def behav_write_word(data):
    # yield dut.frac_p.eq(data)
    yield


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    # raise UnderConstruction()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
