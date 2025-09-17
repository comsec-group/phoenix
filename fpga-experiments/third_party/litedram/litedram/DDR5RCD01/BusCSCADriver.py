#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
from operator import xor
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *


class BusCSCADriver(Module):
    """
        DDR5 RCD01 Module Template

        Module
        ------


        Parameters
        ------
    """

    def __init__(self, if_ibuf_o, dcs_n_w=2, dca_w=7):
        self.dcs_n = Signal(dcs_n_w, reset=~0)
        # self.dcs_n = Signal(dcs_n_w, reset=0)
        self.dca = Signal(dca_w)

        self.dpar = Signal()
        self.comb += If(
            reduce(xor, [self.dca[bit] for bit in range(dca_w)]),
            self.dpar.eq(1)
        ).Else(
            self.dpar.eq(0)
        )
        self.comb += if_ibuf_o.dcs_n.eq(self.dcs_n)
        self.comb += if_ibuf_o.dca.eq(self.dca)
        self.comb += if_ibuf_o.dpar.eq(self.dpar)

    def drive_init(self):
        yield from self.drive_cs_ca(~0, 0)

    def drive_cs_ca(self, cs, ca):
        while (yield ResetSignal("sys")):
            yield
        yield self.dcs_n.eq(cs)
        yield self.dca.eq(ca)
        yield


class TestBed(Module):
    def __init__(self):
        if_ibuf_o = If_ibuf()
        self.submodules.dut = BusCSCADriver(if_ibuf_o=if_ibuf_o)


def run_test(tb):
    logging.debug('Write test')
    # yield from tb.dut.seq_cmds()
    yield from tb.dut.drive_init()
    yield from tb.dut.drive_cs_ca(cs=0x01, ca=0x5A)
    yield from tb.dut.drive_cs_ca(cs=0x02, ca=0x5B)
    yield from tb.dut.drive_cs_ca(cs=0x00, ca=0x5C)
    yield from tb.dut.drive_init()
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
