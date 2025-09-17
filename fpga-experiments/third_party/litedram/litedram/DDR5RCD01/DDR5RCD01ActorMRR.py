#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
from operator import xor
import enum
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.SimCSCADriver import SimCSCADriver
from litedram.DDR5RCD01.DDR5RCD01Decoder import DDR5RCD01Decoder
from litedram.DDR5RCD01.DDR5RCD01Actor import DDR5RCD01Actor
from litedram.DDR5RCD01.DDR5RCD01Actor import DDR5Commands
from litedram.DDR5RCD01.DDR5RCD01Actor import DDR5Opcodes


class DDR5RCD01ActorMRR(Module):
    """
        DDR5 RCD01 Actor is the module, which:

            - ...


        Module
        ------


        Parameters
        ------
        max_ui_num

        cs_n_w

        ca_w

    """

    def __init__(self,
                 trigger,
                 mrr_mra,
                 mrr_cw,
                 ):
        xfsm_mrr = FSM(reset_state="IDLE")
        self.submodules += xfsm_mrr

        xfsm_mrr.act(
            "IDLE",
            # Do not drive the Register interface
            NextState("IDLE")
        )


class TestBed(Module):
    def __init__(self):

        self.trigger = Signal()
        self.mrr_mra = Signal(DDR5Commands.MRA_W)
        self.mrr_cw = Signal()
        
        self.submodules.dut = DDR5RCD01ActorMRR(
            trigger=self.trigger,
            mrr_mra=self.mrr_mra,
            mrr_cw=self.mrr_cw,
        )


def run_test(tb):
    logging.debug('Write test')
    for i in range(10):
        yield
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    UnderConstruction
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
