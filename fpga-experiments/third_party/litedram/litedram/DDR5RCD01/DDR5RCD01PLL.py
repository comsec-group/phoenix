#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from migen import *
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *


class DDR5RCD01PLL(Module):
    """DDR5 RCD01 PLL
    TODO Documentation
    RW05 DIMM operating speed, frequency band select - test mode?
    RW06 defines the dck input clock frequency
    Do I need the x64 clock to generate fractions n/64?
    Is the main function of PLL in physical implementation to re-drive the clock?
    Then, in the model it wouldn't have to do much
    TODO current implementation is a bypass mode only (RW05.3-0 == 1111)
    Module
    ------
    dck_t,dck_c : Input clock
    qck_t,qck_c : Output clock (x1); for every rank, row, etc.
    qck64_t,qck64_c : Output clock (x64)

    """

    def __init__(self,
                 if_ck_rst,
                 if_pll,
                 if_ctrl,
                 if_config,
                 ):
        # Clock pass-through
        for i in range(4):
            self.comb += if_pll.ck_t[i].eq(if_ck_rst.dck_t)
            self.comb += if_pll.ck_c[i].eq(if_ck_rst.dck_c)

        # TODO Replace with a real PLL model
        # TODO Implement control interface handler



class TestBed(Module):
    def __init__(self):

        self.if_ck_rst = If_ck_rst()
        self.if_pll = If_ck(n_clks=4)
        self.if_common = If_common()
        self.if_ctrl_common = If_ctrl_common()
        self.if_config_common = If_config_common()

        self.comb += self.if_ck_rst.dck_c.eq(~self.if_ck_rst.dck_t)

        self.submodules.dut = DDR5RCD01PLL(
            if_ck_rst=self.if_ck_rst,
            if_pll=self.if_pll,
            if_common=self.if_common,
            if_ctrl_common=self.if_ctrl_common,
            if_config_common=self.if_config_common,
        )


def run_test(tb):
    logging.debug('Write test')
    for b in [0, 1]*5:
        yield from behav_write(b)
    logging.debug('Yield from write test.')


def behav_write(b):
    yield tb.if_ck_rst.dck_t.eq(b)
    yield


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
