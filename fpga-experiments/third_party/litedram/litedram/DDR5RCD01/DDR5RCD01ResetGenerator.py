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
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *


class DDR5RCD01ResetGenerator(Module):
    """
        DDR5 RCD01 Reset Generator

        Module
        ------
        drst_n - Host reset
        drst_pon - Reset from power-on
        drst_rw04 - Reset from RW04

        Parameters
        ------
    """

    def __init__(self, drst_n, drst_pon, drst_rw04, qrst_n):
        assert_reset = Signal(reset=~0)

        # self.sync += If(
        #     ~drst_n | drst_pon | drst_rw04,
        #     assert_reset.eq(1)
        # ).Else(
        #     assert_reset.eq(0)
        # )
        """
            Priority encoder
        """
        self.sync += If(
            drst_pon,
            assert_reset.eq(1)
        ).Else(
            If(
                drst_rw04,
                assert_reset.eq(1)
            ).Else(
                If(
                    ~drst_n,
                    assert_reset.eq(1),
                ).Else(
                    assert_reset.eq(0),
                )
            )
        )

        self.comb += If(
            assert_reset,
            qrst_n.eq(0)
        ).Else(
            qrst_n.eq(1)
        )


class TestBed(Module):
    def __init__(self):
        self.drst_n = Signal(reset=~0)
        self.drst_pon = Signal()
        self.drst_rw04 = Signal()
        self.qrst_n = Signal()
        self.submodules.dut = DDR5RCD01ResetGenerator(
            drst_n=self.drst_n,
            drst_pon=self.drst_pon,
            drst_rw04=self.drst_rw04,
            qrst_n=self.qrst_n,
        )


def run_test(tb):
    logging.debug('Write test')
    yield tb.drst_n.eq(1)
    yield tb.drst_pon.eq(0)
    yield tb.drst_rw04.eq(0)

    for i in range(5):
        yield
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
