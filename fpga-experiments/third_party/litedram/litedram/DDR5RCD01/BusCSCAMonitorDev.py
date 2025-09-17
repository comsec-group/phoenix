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


class BusCSCAMonitorDev(Module):
    """
        DDR5 RCD01 Monitor

        cmd_len : bit width of this signal should be large enough
        to count all clock cycles of the simulation.
        Hard to assess how much array depth is required, this
        is related to environment setup. The longer the simulation,
        the longer the array.

        Module
        ------

        Parameters
        ------

        Sample output:
            - inactive for n clocks
            - 1 ui message
            - inactive for 1 clock
            - 2 ui message
            - 1 ui message
            - inactive

        Data structure to hold this:
        List would be best. migen style list is an Array

        I think that squashing inactives together is useful and would free some memory,
        array width {CSCA  bus capture, metadata}
        single entry
        is_active, cmd_len (cmd id),ui_n,{command_payload}
        []

        if cmd is inactive:
            increase inactive counter

        if cmd is active:
            save(inactive counter state)
            check if cmd is 1 ui or 2 ui
            UI length is based on CA1:
                CA1==HIGH => CMD is 1 UI
                CA1==LOW  => CMD is 2 UI
            save(next 1/2ui)

        reset(counters)

        post_process():
            read():
            analyze():

        cmd_type = {INACTIVE, SINGLE_UI, DOUBLE_UI}

        self.config = {
            "monitor_type" : MonitorType.DDR,
            "ingress" : True,
            "channel" : "A",
            "rank" : "A",
            "row" : "A"
        }
    """

    def __init__(self,
                 if_ibuf_i,
                 is_sim_finished,
                 config
                 ):

        self.config = config
        self.is_sim_finished = is_sim_finished
        self.signal_list = []
        if isinstance(if_ibuf_i, If_ibuf):
            self.is_type = MonitorType.DDR

            dcs_n_w = len(if_ibuf_i.dcs_n)
            dcs_n = Signal(dcs_n_w)
            self.dcs_n = dcs_n

            dca_w = len(if_ibuf_i.dca)
            dca = Signal(dca_w)
            self.dca = dca
            dpar = Signal()
            dpar_w = len(dpar)

            self.comb += dcs_n.eq(if_ibuf_i.dcs_n)
            self.comb += dca.eq(if_ibuf_i.dca)
            self.comb += dpar.eq(if_ibuf_i.dpar)
        elif isinstance(if_ibuf_i, If_bus_csca_o):
            self.is_type = MonitorType.ONE_N

            dcs_n_w = len(if_ibuf_i.qcs_n)
            dcs_n = Signal(dcs_n_w)
            self.dcs_n = dcs_n

            dca_w = len(if_ibuf_i.qca)
            dca = Signal(dca_w)
            self.dca = dca

            self.comb += dcs_n.eq(if_ibuf_i.qcs_n)
            self.comb += dca.eq(if_ibuf_i.qca)
        else:
            raise TypeError(
                "Monitor received an interface, which is not supported. Expected=[If_ibuf, if_bus_csca_o]")

    def monitor(self):
        dcs_list = []
        dca_list = []
        while not self.is_sim_finished[0]:
            dcs_n = yield self.dcs_n
            dcs_list.append(dcs_n)
            dca = yield self.dca
            dca_list.append(dca)
            yield
        self.signal_list = [dcs_list, dca_list]


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
        self.submodules.monitor = BusCSCAMonitorDev(
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
