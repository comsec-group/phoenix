#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import unittest
import logging
# migen
from migen import *
from migen.fhdl import verilog
# RCD
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01Decoder import DDR5RCD01Decoder
from litedram.DDR5RCD01.BusCSCAEnvironment import BusCSCAEnvironment
from litedram.DDR5RCD01.BusCSCAEnvironment import EnvironmentScenarios
from litedram.DDR5RCD01.CRG import CRG


class TestBed(Module):
    def __init__(self, is_dual_channel=False):
        RESET_TIME = 1
        self.clocks = {
            "sys":      (128, 63),
            "sysx2":    (64, 31),
            "sys_rst":  (128, 63+4),
        }
        self.submodules.xcrg = CRG(
            clocks=self.clocks,
            reset_cnt=RESET_TIME
        )
        self.generators = {}

        """
            Items on the bed
        """
        self.if_ibuf_A = If_ibuf()

        self.submodules.xenvironment = ClockDomainsRenamer("sys")(
            BusCSCAEnvironment(
                if_ibuf_o=self.if_ibuf_A,
            )
        )

        qvalid = Signal()
        qvalid_A = Signal()
        qvalid_B = Signal()
        is_this_ui_odd = Signal()
        is_cmd_beginning = Signal()
        is_cw_bit_set = Signal()

        self.if_csca_o = If_ibuf()
        self.if_csca_o_rank_A = If_ibuf()
        self.if_csca_o_rank_B = If_ibuf()

        self.submodules.dut = DDR5RCD01Decoder(
            if_ibuf=self.if_ibuf_A,
            if_csca_o=self.if_csca_o,
            if_csca_o_rank_A=self.if_csca_o_rank_A,
            if_csca_o_rank_B=self.if_csca_o_rank_B,
            qvalid=qvalid,
            qvalid_A=qvalid_A,
            qvalid_B=qvalid_B,
            is_this_ui_odd=is_this_ui_odd,
            is_cmd_beginning=is_cmd_beginning,
            is_cw_bit_set=is_cw_bit_set,
        )

        """
            Validation
        """
        count_commands = Signal(16)
        self.sync += If(
            is_cmd_beginning & qvalid_A,
            count_commands.eq(count_commands+1)
        )
        count_valid = Signal(16)
        self.sync += If(
            qvalid_A,
            count_valid.eq(count_valid+1)
        )
        self.count_commands = count_commands
        self.count_valid = count_valid

        """
            Generators
        """
        self.add_generators(
            self.generators_dict()
        )

    def read_counters(self):
        while not self.xenvironment.agent.sequencer.is_sim_finished[0]:
            self.val_count_commands = yield self.count_commands
            self.val_count_valid = yield self.count_valid
            yield

    def generators_dict(self):
        return {
            "sys":
            [
                self.xenvironment.run_env(
                    scenario_select=EnvironmentScenarios.DECODER_MCA),
                self.read_counters(),
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


class DDR5RCD01DecoderTests(unittest.TestCase):

    def setUp(self):
        self.tb = TestBed(is_dual_channel=False)
        """
            Waveform file
        """
        dir_name = "./wave_ut"
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)
        file_name = self._testMethodName
        self.wave_file_name = dir_name + '/' + file_name + ".vcd"
        """
            Logging
        """
        LOG_FILE_NAME = dir_name + '/' + file_name + ".log"
        FORMAT = "[%(module)s.%(funcName)s] %(message)s"
        fileHandler = logging.FileHandler(filename=LOG_FILE_NAME, mode='w')
        fileHandler.formatter = logging.Formatter(FORMAT)
        streamHandler = logging.StreamHandler()

        logger = logging.getLogger('root')
        logger.addHandler(fileHandler)
        logger.addHandler(streamHandler)
        logger.setLevel(logging.DEBUG)

    def tearDown(self):
        del self.tb

    def test_decoder(self):
        logger = logging.getLogger('root')
        logger.debug("-"*80)
        run_simulation(
            self.tb,
            generators=self.tb.run_test(),
            clocks=self.tb.xcrg.clocks,
            vcd_name=self.wave_file_name
        )

        dut_count_commands = int(self.tb.val_count_commands)
        env_count_commands = 0
        for id, item in enumerate(self.tb.xenvironment.queue):
            if item["cs_signalling"] != "inactive":
                if item["destination_rank"] != "B":
                    env_count_commands = env_count_commands + 1
        assert env_count_commands == dut_count_commands


if __name__ == '__main__':
    unittest.main()
