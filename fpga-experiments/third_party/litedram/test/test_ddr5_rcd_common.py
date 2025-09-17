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
from litedram.DDR5RCD01.DDR5RCD01Common import DDR5RCD01Common
from litedram.DDR5RCD01.CRG import CRG
from litedram.DDR5RCD01.Monitor import Monitor
from litedram.DDR5RCD01.DDR5RCD01Alert import RCDAlertModes


class TestBed(Module):
    def __init__(self, is_dual_channel=False):
        self.is_sim_finished = [False]
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
        self.if_pll = If_ck(n_clks=4)
        self.if_host_ck_rst = If_ck_rst()
        self.if_host_alert_n = If_alert_n()
        self.if_host_lb = If_lb()
        self.if_common_A = If_channel_sdram()
        self.if_common_B = If_channel_sdram()
        self.if_ctrl_common = If_ctrl_common()
        self.if_config_common = If_config_common()

        xcommon = DDR5RCD01Common(
            if_host_ck_rst=self.if_host_ck_rst,
            if_host_alert_n=self.if_host_alert_n,
            if_host_lb=self.if_host_lb,
            if_pll=self.if_pll,
            if_channel_A=self.if_common_A,
            if_channel_B=self.if_common_B,
            if_ctrl_common=self.if_ctrl_common,
            if_config_common=self.if_config_common,
        )
        self.submodules.xcommon = xcommon

        xmonitor_alert = Monitor(
            [
                self.if_common_A.derror_in_n,
                self.if_common_B.derror_in_n,
                self.if_host_alert_n.alert_n,
            ],
            is_sim_finished=self.is_sim_finished,
            config=None
        )
        self.submodules.xmonitor_alert = xmonitor_alert

        xmonitor_pll = Monitor(
            [
                self.if_host_ck_rst.dck_t,
                self.if_host_ck_rst.dck_c,
                self.if_pll.ck_t,
                self.if_pll.ck_c,
            ],
            is_sim_finished=self.is_sim_finished,
            config=None
        )
        self.submodules.xmonitor_pll = xmonitor_pll

        xmonitor_loopback = Monitor(
            [
                self.if_common_A.dlbd,
                self.if_common_A.dlbs,
                self.if_common_B.dlbd,
                self.if_common_B.dlbs,
                self.if_host_lb.qlbs,
                self.if_host_lb.qlbd,
            ],
            is_sim_finished=self.is_sim_finished,
            config=None
        )
        self.submodules.xmonitor_loopback = xmonitor_loopback

        """
            Generators
        """
        self.add_generators(
            self.generators_dict()
        )

    def stimulus_rst(self):
        while (yield ResetSignal("sys")):
            yield
        for b in [0, 1]*5:
            yield self.if_host_ck_rst.drst_n.eq(b)
            yield

    def stimulus_pll(self):
        while (yield ResetSignal("sys")):
            yield
        for b in [0, 1]*5:
            yield self.if_host_ck_rst.dck_t.eq(b)
            yield self.if_host_ck_rst.dck_c.eq(~b)
            yield

    def stimulus_alert(self):
        while (yield ResetSignal("sys")):
            yield
        yield self.if_ctrl_common.alert_n_mode.eq(RCDAlertModes.STATIC)
        yield self.if_common_A.derror_in_n.eq(0)
        yield self.if_common_B.derror_in_n.eq(0)
        yield
        yield self.if_common_A.derror_in_n.eq(1)
        yield
        yield self.if_common_A.derror_in_n.eq(0)
        yield self.if_ctrl_common.alert_n_mode.eq(RCDAlertModes.PULSED)
        yield
        yield self.if_common_A.derror_in_n.eq(1)
        yield
        yield self.if_common_A.derror_in_n.eq(0)
        yield
        for _ in range(5):
            yield

    def stimulus_loopback(self):
        while (yield ResetSignal("sys")):
            yield
        for b in [0, 1]*2:
            yield self.if_common_A.dlbd.eq(b)
            yield self.if_common_A.dlbs.eq(~b)
            yield self.if_common_B.dlbd.eq(1)
            yield self.if_common_B.dlbs.eq(0)
            yield
        yield self.if_ctrl_common.lb_sel_channel_A_B.eq(1)
        yield
        for b in [0, 1]*2:
            yield self.if_common_A.dlbd.eq(b)
            yield self.if_common_A.dlbs.eq(~b)
            yield self.if_common_B.dlbd.eq(1)
            yield self.if_common_B.dlbs.eq(0)
            yield

    def run_sim(self):
        while (yield ResetSignal("sys")):
            yield
        for _ in range(15):
            yield
        self.is_sim_finished = [True]
        self.xmonitor_pll.is_sim_finished = [True]
        self.xmonitor_alert.is_sim_finished = [True]
        self.xmonitor_loopback.is_sim_finished = [True]

    def generators_dict(self):
        return {
            "sys":
            [
                self.run_sim(),
                self.xmonitor_pll.monitor(),
                self.xmonitor_alert.monitor(),
                self.xmonitor_loopback.monitor(),
                self.stimulus_pll(),
                self.stimulus_alert(),
                self.stimulus_loopback(),
                self.stimulus_rst()
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

        run_simulation(
            self.tb,
            generators=self.tb.run_test(),
            clocks=self.tb.xcrg.clocks,
            vcd_name=self.wave_file_name
        )

    def tearDown(self):
        del self.tb

    def test_common(self):
        logger = logging.getLogger('root')
        logger.debug("-"*80)
        # TODO Re-enable tests below and add meaningful assertions
        assert 1 == 1

    # def test_loopback(self):
    #     logger = logging.getLogger('root')
    #     logger.debug("-"*80)
    #     sim_data = self.tb.xmonitor_loopback.signal_list
    #     assert 1 == 1

    # def test_alert(self):
    #     logger = logging.getLogger('root')
    #     logger.debug("-"*80)
    #     sim_data = self.tb.xmonitor_alert.signal_list
    #     assert 1 == 1

    # def test_reset(self):
    #     logger = logging.getLogger('root')
    #     logger.debug("-"*80)
    #     sim_data = self.tb.xmonitor_pll.signal_list
    #     assert 1 == 1


if __name__ == '__main__':
    unittest.main()
