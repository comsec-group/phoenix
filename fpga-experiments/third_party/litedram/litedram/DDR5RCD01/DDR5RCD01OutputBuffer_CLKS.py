#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *
#
from litedram.DDR5RCD01.DDR5RCD01OutBuf import DDR5RCD01OutBuf


class DDR5RCD01OutputBuffer_CLKS(Module):
    """DDR5 RCD01 Output Buffer
    TODO Documentation
    d         - Input : data
    oe        - Input : output enable
    o_inv_en  - Input : output inversion enable
    frac_p    - Input : Fractional (n/64) phase delay select; frac_p==0 -> no delay
    q         - Output: data
    Driver strength is not on implementation list, also: slew rate control
    """

    def __init__(self, if_i_clks, if_o_clks, if_ctrl, sig_disable_level=1):
        # Single differential clock
        xoutbuf_qck_t = DDR5RCD01OutBuf(
            d=if_i_clks.ck_t,
            q=if_o_clks.ck_t,
            oe=if_ctrl.oe_ck_t,
            o_inv_en=if_ctrl.o_inv_en_ck_t,
            tie_high = if_ctrl.tie_high_ck_t,
            tie_low = if_ctrl.tie_low_ck_t,
            sig_disable_level=sig_disable_level
        )
        self.submodules += xoutbuf_qck_t

        xoutbuf_qck_c = DDR5RCD01OutBuf(
            d=if_i_clks.ck_c,
            q=if_o_clks.ck_c,
            oe=if_ctrl.oe_ck_c,
            o_inv_en=if_ctrl.o_inv_en_ck_c,
            tie_high = if_ctrl.tie_high_ck_c,
            tie_low = if_ctrl.tie_low_ck_c,
            sig_disable_level=sig_disable_level
        )
        self.submodules += xoutbuf_qck_c

        # TODO Implement fractional delay here
        # If frac_p == xx, delay the clock by yy


class TestBed(Module):
    def __init__(self):

        self.ctrl_if = If_ctrl_obuf_CLKS()
        self.iif_clks = If_ck()
        self.oif_clks = If_ck()

        self.submodules.dut = DDR5RCD01OutputBuffer_CLKS(
            self.iif_csca, self.iif_clks, self.oif_csca, self.oif_clks, self.ctrl_if)
        # print(verilog.convert(self.dut))


def run_test(dut):
    logging.debug('Write test')
    yield from behav_rst(tb)
    yield
    yield from set_all_outs(tb, 1)
    yield
    yield from set_all_outs(tb, 0)
    yield
    yield from set_all_oe(tb, 1)
    yield
    yield from set_all_outs(tb, 1)
    yield
    yield from set_all_outs(tb, 0)
    yield
    yield from set_all_inv_en(tb, 1)
    yield
    yield from set_all_outs(tb, 1)
    yield
    yield from set_all_outs(tb, 0)
    yield

    logging.debug('Yield from write test.')


def set_all_inv_en(tb, b):
    yield tb.ctrl_if.o_inv_en_qacs_a_n.eq(b)
    yield tb.ctrl_if.o_inv_en_qaca_a.eq(b)
    yield tb.ctrl_if.o_inv_en_qacs_b_n.eq(b)
    yield tb.ctrl_if.o_inv_en_qaca_b.eq(b)
    yield tb.ctrl_if.o_inv_en_qack_t.eq(b)
    yield tb.ctrl_if.o_inv_en_qack_c.eq(b)
    yield tb.ctrl_if.o_inv_en_qbck_t.eq(b)
    yield tb.ctrl_if.o_inv_en_qbck_c.eq(b)
    yield tb.ctrl_if.o_inv_en_qcck_t.eq(b)
    yield tb.ctrl_if.o_inv_en_qcck_c.eq(b)
    yield tb.ctrl_if.o_inv_en_qdck_t.eq(b)
    yield tb.ctrl_if.o_inv_en_qdck_c.eq(b)


def set_all_oe(tb, b):
    yield tb.ctrl_if.oe_qacs_a_n.eq(b)
    yield tb.ctrl_if.oe_qaca_a.eq(b)
    yield tb.ctrl_if.oe_qacs_b_n.eq(b)
    yield tb.ctrl_if.oe_qaca_b.eq(b)
    yield tb.ctrl_if.oe_qack_t.eq(b)
    yield tb.ctrl_if.oe_qack_c.eq(b)
    yield tb.ctrl_if.oe_qbck_t.eq(b)
    yield tb.ctrl_if.oe_qbck_c.eq(b)
    yield tb.ctrl_if.oe_qcck_t.eq(b)
    yield tb.ctrl_if.oe_qcck_c.eq(b)
    yield tb.ctrl_if.oe_qdck_t.eq(b)
    yield tb.ctrl_if.oe_qdck_c.eq(b)


def set_all_outs(tb, b):
    yield tb.iif_csca.qacs_a_n.eq(b)
    yield tb.iif_csca.qaca_a.eq(b)
    yield tb.iif_csca.qacs_b_n.eq(b)
    yield tb.iif_csca.qaca_b.eq(b)
    yield tb.iif_clks.qack_t.eq(b)
    yield tb.iif_clks.qack_c.eq(b)
    yield tb.iif_clks.qbck_t.eq(b)
    yield tb.iif_clks.qbck_c.eq(b)
    yield tb.iif_clks.qcck_t.eq(b)
    yield tb.iif_clks.qcck_c.eq(b)
    yield tb.iif_clks.qdck_t.eq(b)
    yield tb.iif_clks.qdck_c.eq(b)


def behav_rst(tb):
    yield from set_all_inv_en(tb, 0)
    yield from set_all_oe(tb, 0)
    yield from set_all_outs(tb, 0)


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
