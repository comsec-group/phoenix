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


class DDR5RCD01OutBuf(Module):
    """ OutBuf is a simple circuit with output enable and output inversion enable.
    The output inversion is a bitwise NOT. The parameter sig_disable_level can be used
    to select which state is supposed to be presented on the output while the output
    enable is deasserted.
    """

    def __init__(self, d, q, oe, o_inv_en, tie_high, tie_low, sig_disable_level=0):
        self.comb += If(
            tie_high,
            q.eq(~0),
        ).Elif(
            tie_low,
            q.eq(0),
        ).Else(
            If(oe,
               If(o_inv_en,
                  q.eq(~d)
                  ).Else(q.eq(d))
               ).Else(q.eq(sig_disable_level))
        )


class TestBed(Module):
    def __init__(self):

        self.d = Signal()
        self.q = Signal()
        self.oe = Signal()
        self.o_inv_en = Signal()

        self.submodules.dut = DDR5RCD01OutBuf(
            self.d, self.q, self.oe, self.o_inv_en)
        # print(verilog.convert(self.dut))


def run_test(tb):
    logging.debug('Write test')
    yield from tb_init(tb)
    d = [0, 1, 0, 1, 0]
    yield from tb_seq(tb, d)

    logging.debug('Yield from write test.')


def tb_init(tb):
    yield tb.d.eq(0)
    yield tb.oe.eq(0)
    yield tb.o_inv_en.eq(0)


def tb_seq(tb, d):
    CONTROL_VALUES = [[0, 0], [0, 1], [1, 0], [1, 1]]
    for oe, o_inv_en in CONTROL_VALUES:
        logging.debug("oe = " + str(oe) + " o_inv_en = " + str(o_inv_en))
        yield tb.oe.eq(oe)
        yield tb.o_inv_en.eq(o_inv_en)
        for data in d:
            yield tb.d.eq(data)
            yield


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
