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


class DDR5RCD01DCATMAgent(Module):
    """
        DDR5 RCD DCA Training Mode Agent

        RCD model operates with doubled frequency (DDR mode by default).
        This implementation of the DCATM is meant for XOR of both edges
        Module
        ------

        Parameters
        ------
        if_ctrl.enable
    """

    def __init__(self,
                 if_ibuf: If_ibuf,
                 sample_o: Signal,
                 if_ctrl: If_ctrl_dcatm_agent):
        """
           TODO confirm: in DCATM, always DCS_n[0] is used?
        """
        dcs_n = Signal()
        self.comb += dcs_n.eq(if_ibuf.dcs_n[0])
        dcs_n_d = Signal()
        self.sync += dcs_n_d.eq(dcs_n)

        dca_w = len(if_ibuf.dca)
        dca = Signal(dca_w)
        self.comb += dca.eq(if_ibuf.dca)
        dca_d = Signal(dca_w)
        self.sync += dca_d.eq(dca)

        dpar_w = len(if_ibuf.dpar)
        dpar = Signal(dpar_w)
        self.comb += dpar.eq(if_ibuf.dpar)
        dpar_d = Signal(dpar_w)
        self.sync += dpar_d.eq(dpar)

        """
            If DCS_n[0] is asserted, capture the XOR value
            Output sample calculation logic
        """
        sample = Signal()
        # If both edges are used
        self.comb += If(
            (dcs_n == 0) &
            (dcs_n_d == 0),
            sample.eq(reduce(xor, Cat(dpar, dca, dpar_d, dca_d)))
        )

        """
            It is assumed that this block is connected to Alert block in Common.
            It is expected that Alert block is configured in static mode.
            The alert block expects positive logic.
        """
        self.sync += If(
            if_ctrl.enable,
            If(
                (dcs_n == 0) &
                (dcs_n_d == 0),
                sample_o.eq(~sample),)
            .Else(
                sample_o.eq(sample_o)
            )
        ).Else(
            sample_o.eq(0),
        )

        """
            "If dcs is asserted for 2 or more cycles, exit the mode."
            4 clocks of DDR in the simulation.
            Model ignores "limited to 8 cycles" behavior
        """
        # TODO re-enable
        # dcs_n_d = Signal()
        # exit_dcatm_mode = Signal()
        # self.sync += dcs_n_d.eq(dcs_n)
        # self.comb += If(
        #     (dcs_n == 0) &
        #     (dcs_n_d == 0),
        #     exit_dcatm_mode.eq(1)
        # ).Else(
        #     exit_dcatm_mode.eq(0)
        # )
        self.comb += if_ctrl.exit_dcatm.eq(0)


class TestBed(Module):
    def __init__(self):
        self.submodules.dut = DDR5RCD01DCATMAgent()


def run_test(tb):
    logging.debug('Write test')
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
