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

from litedram.DDR5RCD01.BusCSCADriver import BusCSCADriver


class BusCSCASequencer(Module):
    """
        DDR5 RCD01 Module Template

        Module
        ------


        Parameters
        ------
    """

    def __init__(self, if_ibuf_o, dcs_n_w=2, dca_w=7):
        self.is_sim_finished = [False]
        xBusCSCADriver = BusCSCADriver(
            if_ibuf_o=if_ibuf_o
        )
        self.submodules.xBusCSCADriver = xBusCSCADriver


    def run_sequence(self, sequence):
        for id,item in enumerate(sequence):
            cs = item[0]
            ca = item[1]
            yield from self.xBusCSCADriver.drive_cs_ca(cs, ca)
        """
            Extra ESTIMATE_RCD_LATENCY cycles are simulated to make sure
            that all commands propagated through the RCD Core. The value
            is an estimate and may be subject to change
        """
        ESTIMATE_RCD_LATENCY=16
        for _ in range(ESTIMATE_RCD_LATENCY):
            yield
        self.is_sim_finished[0] = True
        


class TestBed(Module):
    def __init__(self):
        if_ibuf_o = If_ibuf()
        xBusCSCASequencer = BusCSCASequencer(
             if_ibuf_o=if_ibuf_o
        )
        self.submodules.dut = xBusCSCASequencer

def run_test(tb):
    logging.debug('Write test')
    # yield from tb.dut.seq_cmds()
    sequence = []
    SEQ_INACTIVE = [~0, 0]
    sequence.append(SEQ_INACTIVE)
    sequence.append([0x01, 0x5A])
    sequence.append([0x02, 0x5B])
    sequence.append([0x00, 0x5C])
    sequence.append(SEQ_INACTIVE)
    logging.debug("Sequence = " + str(sequence))
    yield from tb.dut.run_sequence(sequence)
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
