#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
import numpy as np
from operator import xor
from dataclasses import dataclass
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
#
from litedram.DDR5RCD01.BusCSCAEnvironment import BusCSCAEnvironment
from litedram.DDR5RCD01.BusCSCAEnvironment import EnvironmentScenarios
from litedram.DDR5RCD01.BusCSCAMonitorDefinitions import *


class BusCSCAScoreboard(Module):
    """
        DDR5 RCD01 Scoreboard
        ---------------------
        Compare queues of 2 monitors. Currently meant for DDR and 1N

        Module
        ------

        Parameters
        ----------
        self.p.config = {
            "monitor_type": MonitorType.ONE_N,
            "ingress": False,
            "channel": "A",
            "rank": "A",
            "row": "A"
        }

    """

    def __init__(self, p, p_other):
        self.p = p
        self.p_other = p_other

        if p.config["monitor_type"] == MonitorType.DDR:
            self.q_ddr = self.p.commands
        if p_other.config["monitor_type"] == MonitorType.ONE_N:
            self.q_one_n = self.p_other.commands

        self.validate_input()

        if p_other.config["rank"] == "A":
            self.q = self.filter_q_by_dest(
                self.q_ddr, CommandDestination.RANK_A)
        if p_other.config["rank"] == "B":
            self.q = self.filter_q_by_dest(
                self.q_ddr, CommandDestination.RANK_B)
        self.q_other = self.q_one_n

        self.q = self.filter_q_by_type(self.q, MonitorCommandType.DESELECT)
        self.q_other = self.filter_q_by_type(
            self.q_other, MonitorCommandType.DESELECT)
        self.compare(self.q, self.q_other)

    def filter_q_by_dest(self, q, destination):
        """
            The deselected rank is filtered out.
        """
        if destination == CommandDestination.RANK_A:
            filter_dest = CommandDestination.RANK_B
        if destination == CommandDestination.RANK_B:
            filter_dest = CommandDestination.RANK_A

        q_out = []
        for id, item in enumerate(q):
            if item.destination_rank != filter_dest:
                q_out.append(item)
        return q_out

    def filter_q_by_type(self, q, type):
        """
            The selected type is filtered out.
        """
        q_out = []
        for id, item in enumerate(q):
            if item.command_type != type:
                q_out.append(item)
        return q_out

    def validate_input(self):
        self.check_q_boundaries(self.q_ddr)
        self.check_q_boundaries(self.q_one_n)

    @staticmethod
    def check_q_boundaries(q):
        """
            Expect the queues to start and end with deselect on the line
        """
        assert q[0].command_type == MonitorCommandType.DESELECT
        assert q[-1].command_type == MonitorCommandType.DESELECT

    @staticmethod
    def check_q_length():
        """
            Expect that the same number of commands is present on ingress and egress
        """
        assert 1 == 1

    def get_q_command_count(self):
        return len(self.q_ddr)

    @staticmethod
    def deserialize(ui0, ui1):
        return (ui1 << 7) | ui0

    @staticmethod
    def compare(q, q_other):
        """
            Assuming no commands were consumed by the RCD, the q's should be equal
        """
        assert len(q) == len(q_other)

        """
            Debug logs
        """
        logging.debug("Q")
        for commands in [q]:
            logging.debug("Commands")
            for cmd in commands:
                logging.debug(cmd)
            logging.debug("----------------")

        logging.debug("Q OTHER")
        for commands in [q_other]:
            logging.debug("Commands")
            for cmd in commands:
                logging.debug(cmd)
            logging.debug("----------------")
        """
            Compare items on list one-by-one
        """
        for id, _ in enumerate(q):
            """
                Command type should match
            """
            assert q[id].command_type == q_other[id].command_type
            logging.info("Command " + str(id) + " type match " +
                         str(q[id].command_type))
            """
                2x7-bit CA Values should match the 14 bit output
            """
            if q[id].command_type in [MonitorCommandType.SINGLE_UI, MonitorCommandType.DOUBLE_UI]:
                ui0 = q[id].dca[0]
                ui1 = q[id].dca[1]
                ui_o = BusCSCAScoreboard.deserialize(ui0, ui1)
                assert ui_o == q_other[id].dca[0]
                logging.info("DCA value " + "("+str(ui1)+"," +
                             str(ui0)+")" + " match " + str(ui_o))

            if q[id].command_type == MonitorCommandType.DOUBLE_UI:
                ui0 = q[id].dca[2]
                ui1 = q[id].dca[3]
                ui_o = BusCSCAScoreboard.deserialize(ui0, ui1)
                assert ui_o == q_other[id].dca[2]
                logging.info("DCA value " + "("+str(ui1)+"," +
                             str(ui0)+")" + " match " + str(ui_o))


class TestBed(Module):
    def __init__(self):
        pass


def run_test(tb):
    logging.debug('Write test')
    # scenario_select = EnvironmentScenarios.SIMPLE_GENERIC
    # yield from tb.env.run_env(scenario_select=scenario_select)
    # logging.debug(str(tb.monitor.monit_q))
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
