#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
import numpy as np
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
from litedram.DDR5RCD01.BusCSCAMonitorDev import BusCSCAMonitorDev
from litedram.DDR5RCD01.BusCSCAMonitorDefinitions import *
# from test.CRG import CRG
from litedram.DDR5RCD01.CRG import CRG


class BusCSCACommand:
    """
        Bus CS CA Command
        -----------------
    """

    def __init__(self, csca_list):
        self.dcs_n = csca_list[0]
        self.dca = csca_list[1]
        self.set_metadata()

    def set_metadata(self):
        self.command_type = None
        if all(dcs == CSEncoding.DESELECT for dcs in self.dcs_n):
            self.command_type = MonitorCommandType.DESELECT
        elif len(self.dcs_n) == 2:
            self.command_type = MonitorCommandType.SINGLE_UI
        elif len(self.dcs_n) == 4:
            self.command_type = MonitorCommandType.DOUBLE_UI

        self.destination_rank = None
        if self.dcs_n[0] == CSEncoding.SELECT_RANK_AB:
            self.destination_rank = CommandDestination.RANK_AB
        elif self.dcs_n[0] == CSEncoding.SELECT_RANK_A:
            self.destination_rank = CommandDestination.RANK_A
        elif self.dcs_n[0] == CSEncoding.SELECT_RANK_B:
            self.destination_rank = CommandDestination.RANK_B

    def __str__(self):
        s = "\r\n"
        s += "\tType = " + str(self.command_type) + "\r\n"
        s += "\tDest = " + str(self.destination_rank) + "\r\n"
        s += "\tDcs  = " + str(self.dcs_n) + "\r\n"
        s += "\tDca  = " + str(self.dca) + " "
        return s


class BusCSCAMonitorPostProcessor(Module):
    """
        BusCSCAMonitorPostProcessor
        ---------------------------
        This implementation operates in DDR
    """

    def __init__(self,
                 signal_list,
                 config,
                 sim_state_list,
                 sim_state_config,
                 ):
        self.signal_list = signal_list
        self.config = config
        self.sim_state_list = sim_state_list
        self.sim_state_config = sim_state_config
        self.commands = []

    def post_process(self):
        self.trim_abnormal_states()
        command_groups = self.convert_to_command_groups()
        cmds = []
        for command_group in command_groups:
            logging.debug("Multi-command")
            logging.debug(command_group)
            logging.debug("-"*20)
            multi_command = self.split_multicommands(command_group)
            for sub_cmd in multi_command:
                cmd = BusCSCACommand(sub_cmd)
                cmds.append(cmd)
            logging.debug(multi_command)
            logging.debug("-"*20)
            logging.debug("\r\n")
        self.commands = cmds

    def trim_abnormal_states(self):
        """
            {dcs_n,dca} order by convention
        """
        dcs_n = self.signal_list[0]
        dca = self.signal_list[1]
        dca_np = np.array(dca)
        dcs_n_np = np.array(dcs_n)

        id_normal = self.sim_state_config.index('NORMAL')
        normal_mask = []
        for state in self.sim_state_list:
            normal_mask.append(state[id_normal])
        normal_mask_np = np.array(normal_mask)
        id = np.where(normal_mask_np == 1)[0]
        q_dcs = np.array(dcs_n_np)[id]
        q_dca = np.array(dca_np)[id]

        q_dcs = q_dcs.tolist()
        q_dca = q_dca.tolist()
        self.signal_list[0] = q_dcs
        self.signal_list[1] = q_dca


    def split_multicommands(self, command_group):
        dcs_n = command_group[0]
        dca = command_group[1]
        dcs_n_np = np.array(dcs_n)
        dca_np = np.array(dca)

        if all(dcs_n_np == CSEncoding.DESELECT):
            return [command_group]

        evens = np.tile([1, 0], int(dca_np.shape[0]/2))
        for id, _ in enumerate(dca):
            if id < (len(dca)-2):
                if not (id % 2):
                    if evens[id]:
                        is_cw_bit_set = ((dca[id] & 0x02) == 0x02)
                        if not is_cw_bit_set:
                            evens[id+2] = 0

        index = np.where(evens == 1)[0]
        DCS_split = np.array_split(dcs_n_np, index)
        DCA_split = np.array_split(dca_np, index)
        DCS_split = self.sanitize_list(DCS_split)
        DCA_split = self.sanitize_list(DCA_split)

        command_groups = list(zip(DCS_split, DCA_split))
        return command_groups

    def __str__(self):
        s = ""
        for cmd in self.commands:
            s += str(cmd)
            s += "\r\n"
        s += "\r\n"
        return s

    def convert_to_command_groups(self):
        """
            {dcs_n,dca} order by convention
        """
        dcs_n = self.signal_list[0]
        dca = self.signal_list[1]
        dca_np = np.array(dca)
        dcs_n_np = np.array(dcs_n)

        """
            Find where value changes
        """
        dcs_n_np_mask = dcs_n_np != CSEncoding.DESELECT
        diff = np.diff(dcs_n_np_mask)
        diff_indices = np.where(diff)[0]
        DCS = diff_indices+1

        """
            DDR
            Take every other index in DCS
            Look at 2 UIs previous
            Check if CW bit is set
            If not set, then add 2 to the index to include next 2uis
        """
        DCS[1::2] += 2*((dca_np[DCS[1::2]-2] & 0x02) == 0x00)
        DCS_split = np.array_split(dcs_n_np, DCS)
        DCA_split = np.array_split(dca_np, DCS)
        logging.debug(DCS_split)
        logging.debug(DCA_split)
        """
            *_split matrices contain bus dcs,dca information split into commands.
            Multi-commands are grouped together at this point
        """
        DCS_split = self.sanitize_list(DCS_split)
        DCA_split = self.sanitize_list(DCA_split)

        command_groups = list(zip(DCS_split, DCA_split))
        return command_groups

    def sanitize_list(self, L):
        L = [l.tolist() for l in L]
        L = list(filter(None, L))
        return L


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

        self.config_monitor = {
            "monitor_type": MonitorType.DDR,
            "ingress": True,
            "channel": "A",
            "rank": None,
            "row": None
        }

        self.submodules.monitor = BusCSCAMonitorDev(
            if_ibuf_i=if_ibuf,
            is_sim_finished=self.env.agent.sequencer.is_sim_finished,
            config=self.config_monitor
        )

        self.add_generators(
            self.generators_dict()
        )

    def generators_dict(self):
        return {
            "sys":
            [
                self.env.run_env(
                    # scenario_select=EnvironmentScenarios.SIMPLE_GENERIC),
                    scenario_select=EnvironmentScenarios.DECODER_MCA),
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

    xprocessor = BusCSCAMonitorPostProcessor(tb.monitor.signal_list)
    xprocessor.post_process()
    commands = xprocessor.commands
    for cmd in commands:
        logging.debug(cmd)
        logging.debug("----------------")

    # xscoreboard = BusCSCAScoreboard(
    #     q1=tb.monitor.monitor_q,
    #     q2=tb.monitor.monitor_q
    # )

    logging.info(str(eT))
