#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# from operator import xor
# from dataclasses import dataclass
# migen
from migen import *
# from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
#
from litedram.DDR5RCD01.BusCSCAEnvironment import BusCSCAEnvironment
from litedram.DDR5RCD01.BusCSCAEnvironment import EnvironmentScenarios
from litedram.DDR5RCD01.BusCSCAScoreboard import BusCSCAScoreboard
from litedram.DDR5RCD01.BusCSCAMonitorDefinitions import *
# from test.CRG import CRG
from litedram.DDR5RCD01.CRG import CRG


class Monitor(Module):
    """
        Monitor
        -------
    """

    def __init__(self,
                 sig,
                 is_sim_finished,
                 config
                 ):

        self.config = config
        self.is_sim_finished = is_sim_finished
        self.signal_list = []
        self.sig = sig

    def monitor(self):
        sig_list = []
        while not self.is_sim_finished[0]:
            sig_value = yield self.sig
            sig_list.append(sig_value)
            yield
        self.signal_list = sig_list


class TestBed(Module):
    def __init__(self):
        RESET_TIME = 1
        self.generators = {}
        self.clocks = {
            "sys":      (128, 63),
            "sys_rst":  (128, 63+4),
        }
        self.submodules.xcrg = CRG(
            clocks=self.clocks,
            reset_cnt=RESET_TIME
        )
        if_ibuf = If_ibuf()

        self.submodules.env = BusCSCAEnvironment(
            if_ibuf_o=if_ibuf,
        )
        self.submodules.monitor = Monitor(
            if_ibuf_i=if_ibuf,
            is_sim_finished=self.env.agent.sequencer.is_sim_finished
        )

        self.add_generators(
            self.generators_dict()
        )

    def generators_dict(self):
        return {
            "sys":
            [
                self.env.run_env(
                    scenario_select=EnvironmentScenarios.SIMPLE_GENERIC),
                self.monitor.monitor(),
            ]
        }

    def add_generators(self, generators):
        for key, value in generators.items():
            if key not in self.generators:
                self.generators[key] = list()
            if not isinstance(value, list):
                value = list(value)
            self.generators[key].extend(value)

    def run_test(self):
        return self.generators


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(
        tb,
        generators=tb.run_test(),
        clocks=tb.clocks,
        vcd_name=eT.wave_file_name
    )
    logging.info("<- Simulation done")
    breakpoint()
    logging.info(str(eT))
