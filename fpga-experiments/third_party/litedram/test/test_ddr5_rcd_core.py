#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import unittest
import logging
import numpy as np
# migen
from migen import *
from migen.fhdl import verilog
# RCD
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01Core import DDR5RCD01Core
from litedram.DDR5RCD01.BusCSCAEnvironment import BusCSCAEnvironment
from litedram.DDR5RCD01.BusCSCAEnvironment import EnvironmentScenarios
from litedram.DDR5RCD01.BusCSCAMonitor import BusCSCAMonitor
from litedram.DDR5RCD01.BusCSCAMonitorDev import BusCSCAMonitorDev
from litedram.DDR5RCD01.BusCSCAMonitorDefinitions import *
from litedram.DDR5RCD01.BusCSCAScoreboard import BusCSCAScoreboard
from litedram.DDR5RCD01.BusCSCAMonitorPostProcessor import BusCSCAMonitorPostProcessor
from litedram.DDR5RCD01.Monitor import Monitor
from litedram.DDR5RCD01.CRG import CRG
from litedram.DDR5RCD01.RCD_sim_timings import RCD_SIM_TIMINGS, t_sum
# from test.CRG import CRG


class RCDStatePS(Module):
    def __init__(self, sig_list, config):
        self.sig_list = sig_list
        self.config = config
        self.state_list = self.remove_duplicate()

    def sanitize_list(self, L):
        L = [l.tolist() for l in L]
        L = list(filter(None, L))
        return L

    def post_process(self):
        self.decode_states()

    def remove_duplicate(self):
        sig_list_np = np.array(self.sig_list)
        sig_list_np_uniq, sig_list_np_ind = np.unique(
            sig_list_np, return_inverse=True, axis=0)
        diff = np.diff(sig_list_np_ind)
        diff_indices = np.where(diff)[0]+1

        sig_list_split = np.array_split(self.sig_list, diff_indices)

        non_dp_sig_list = []
        for arr in sig_list_split:
            arr_uniq = np.unique(arr, axis=0)
            arr_uniq = self.sanitize_list(arr_uniq)
            non_dp_sig_list.append(arr_uniq[0])
        return non_dp_sig_list

    def decode_states(self):
        sim_states = []
        for state in self.state_list:
            state = np.array(state)
            state_num = np.where(state == 1)[0][0]
            sim_states.append((self.config["state_name_list"])[state_num])
        self.sim_states = sim_states


class RCDDCATMPS(Module):
    """
    Signal list:
    0 : xfsm.ongoing("DCATM")
    1 : RW02
    2 : dcs_n
    3 : dca
    4 : dpar
    5 : alert_n
    """

    def __init__(self, sig_list, config):
        self.sig_list = sig_list
        self.config = config
        self.state_list = None

    def post_process(self):
        self.trim_states()
        self.validate()

    def trim_states(self):
        """
            Remove captured signals in states other than DCATM
        """
        sig_np = np.array(self.sig_list)
        indices = np.where(sig_np[:, 0] == 1)[0]
        sig_list = []
        for i in range(sig_np.shape[1]):
            sig = sig_np[:, i]
            sig = sig[indices].tolist()
            sig_list.append(sig)
        self.sig_list = sig_list

    def validate(self):
        dcs_n = np.array(self.sig_list[2])
        dca = np.array(self.sig_list[3])
        dpar = np.array(self.sig_list[4])
        alert_n = np.array(self.sig_list[5])

        # Mask DCS0 bit
        dcs_n = np.bitwise_and(dcs_n, 0x01)

        # Expect to find "0011111" sequences in the training patterns (DDR)
        dcs_n_id = np.where(dcs_n == 0)[0]
        dcs_n_split = np.array_split(dcs_n, dcs_n_id[::2])
        dca_split = np.array_split(dca, dcs_n_id[::2])
        dpar_split = np.array_split(dpar, dcs_n_id[::2])

        # latency: dcs_n + 3, the rcd delay of 3 should be auto-calculated in the future
        alert_n_split = np.array_split(alert_n, dcs_n_id[::2]+3)

        # breakpoint()
        for id, dcs in enumerate(dcs_n_split):
            if id == (len(dcs_n_split)-2):
                break
            if id == 0:
                expected_alert_n = [1]*len(alert_n_split[0])
                simulated_alert_n = alert_n_split[0].tolist()
                assert expected_alert_n == simulated_alert_n, "DCATM Alert_n incorrrect initial sequence"
                continue
            if dcs[0:1] == 0:
                expected_alert_n = [self.reference(
                    dca_split[id][0:2], dpar_split[id][0:2])]*len(dcs)
                simulated_alert_n = alert_n_split[id].tolist()
                # breakpoint()
                assert expected_alert_n == simulated_alert_n, "DCATM Alert_n incorrrect sequence"
            else:
                raise AssertionError("Unexpected DCATM Error")

    @staticmethod
    def reference(dca, dpar):
        output = np.bitwise_xor.reduce(np.concatenate((dca, dpar)))
        output = int(output)
        xor = bin(output).count('1') & 1
        return xor


class RCDDCSTMPS(Module):
    """
    Signal list:
    0 : xfsm.ongoing("DCSTM")
    1 : RW02
    2 : dcs_n
    3 : dca
    4 : dpar
    5 : alert_n
    """

    def __init__(self, sig_list, config):
        self.sig_list = sig_list
        self.config = config
        self.state_list = None

    def sanitize_list(self, L):
        L = [l.tolist() for l in L]
        L = list(filter(None, L))
        return L

    def post_process(self):
        self.trim_states()
        self.split_dcs_n_x_training()
        self.validate(cs_training_bit=0)
        self.validate(cs_training_bit=1)

    def split_dcs_n_x_training(self):
        """
            Split the data into dcs0 and dcs1 training sets

            RW02 has index '1' and contains either value '2' or '3'
            2 if training bit 0
            3 if training bit 1
        """
        sig_np = np.array(self.sig_list)
        indices_dcs_n_0 = np.where(sig_np[1, :] == 2)[0]
        indices_dcs_n_1 = np.where(sig_np[1, :] == 3)[0]

        dcs_n_0 = np.bitwise_and(sig_np[2, indices_dcs_n_0], 0x01)
        dcs_n_1 = np.right_shift(np.bitwise_and(
            sig_np[2, indices_dcs_n_1], 0x02), 1)
        self.dcstm_0 = [dcs_n_0.tolist(), sig_np[5, indices_dcs_n_0].tolist()]
        self.dcstm_1 = [dcs_n_1.tolist(), sig_np[5, indices_dcs_n_1].tolist()]

    def trim_states(self):
        """
            Remove captured signals in states other than DCSTM
        """
        sig_np = np.array(self.sig_list)
        indices = np.where(sig_np[:, 0] == 1)[0]
        sig_list = []
        for i in range(sig_np.shape[1]):
            sig = sig_np[:, i]
            sig = sig[indices].tolist()
            sig_list.append(sig)
        self.sig_list = sig_list

    @staticmethod
    def detect_start_sequence(dcs_n_np, alert_n_np):
        first_zero = np.where(alert_n_np == 0)[0][0]
        # search_seq = [1, 1, 0, 0, 1, 1, 0, 0]
        search_seq = [0, 0, 1, 1, 0, 0, 1, 1]
        counter = first_zero
        while counter:
            sub_seq = dcs_n_np[counter-8:counter]
            if all(sub_seq == search_seq):
                break
            counter += -1
        rcd_latency = first_zero - counter
        start_seq = counter - 8
        return start_seq, rcd_latency

    def validate(self, cs_training_bit=0):
        """
            Prepare reference data

            Take every 4 samples (8 in ddr)
            Calculate output
            In first sample, the alert_n remains high
            If the total number of samples is not divisible by 4, alert should be as in last state
            dcs_n = None
        """

        sig_list_np = np.array((self.dcstm_0, self.dcstm_1)[
                               bool(cs_training_bit)])

        dcs_n_np = sig_list_np[0, :]
        alert_n_np = sig_list_np[1, :]
        # Detect start sequence
        start_sequence_id, rcd_latency = self.detect_start_sequence(
            dcs_n_np, alert_n_np)

        WINDOW_LEN = 8
        dcs_n_np = dcs_n_np[start_sequence_id:]
        alert_n_np = alert_n_np[start_sequence_id:]
        window = [(WINDOW_LEN)*i+(WINDOW_LEN-1)
                  for i in range(int(dcs_n_np.shape[0]/WINDOW_LEN))]
        window_np = np.array(window)+1

        samples_dcs_n = np.split(dcs_n_np, window_np)
        samples_alert_n = np.split(alert_n_np, window_np+rcd_latency)
        samples_dcs_n_len = len(samples_dcs_n)
        for id, sample in enumerate(samples_dcs_n):
            if id == (samples_dcs_n_len-2):
                break
            expected_alert_n = self.reference(sample)
            sim_alert_n = samples_alert_n[id+1].tolist()
            # breakpoint()
            assert sim_alert_n == expected_alert_n, "DCSTM Alert signal is wrong"

    @staticmethod
    def reference(dcs_n):
        """
            Reference implementation
            JEDEC 82-511 Page 43
        """
        WINDOW_LEN = 8
        if (dcs_n[0] == 0) & (dcs_n[2] == 1) & (dcs_n[4] == 0) & (dcs_n[6] == 1):
            alert_n = [0]*WINDOW_LEN
        else:
            alert_n = [1]*WINDOW_LEN
        return alert_n


class TestBed(Module):
    def __init__(self, is_dual_channel=False):
        RESET_TIME = RCD_SIM_TIMINGS["RESET"]
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
        self.if_ck_rst = If_ck_rst()
        self.if_sdram_A = If_channel_sdram()
        self.if_sdram_B = If_channel_sdram()
        self.if_alert_n = If_alert_n()
        self.if_ibuf_A = If_ibuf()
        self.if_ibuf_B = If_ibuf()
        self.if_obuf_A = If_obuf()
        self.if_obuf_B = If_obuf()
        self.if_lb = If_lb()
        self.if_bcom_A = If_bcom()
        self.if_bcom_B = If_bcom()
        self.if_regs_A = If_registers()
        self.if_regs_B = If_registers()
        self.is_dual_channel = is_dual_channel

        self.submodules.xenvironment = ClockDomainsRenamer("sys")(
            BusCSCAEnvironment(
                if_ibuf_o=self.if_ibuf_A,
            )
        )
        """
            TODO Hack to disable dpar generation
        """
        self.if_ibuf_A_2 = If_ibuf()

        self.comb += self.if_ibuf_A_2.dcs_n.eq(self.if_ibuf_A.dcs_n)
        self.comb += self.if_ibuf_A_2.dca.eq(self.if_ibuf_A.dca)

        self.config_monitor_ingress = {
            "monitor_type": MonitorType.DDR,
            "ingress": True,
            "channel": "A",
            "rank": None,
            "row": None
        }

        self.submodules.xmonitor_ingress = ClockDomainsRenamer("sys")(
            BusCSCAMonitorDev(
                if_ibuf_i=self.if_ibuf_A_2,
                is_sim_finished=self.xenvironment.agent.sequencer.is_sim_finished,
                config=self.config_monitor_ingress
            )
        )

        self.submodules.xrcd_core = ClockDomainsRenamer("sys")(
            DDR5RCD01Core(
                if_ck_rst=self.if_ck_rst,
                if_sdram_A=self.if_sdram_A,
                if_sdram_B=self.if_sdram_B,
                if_alert_n=self.if_alert_n,
                if_ibuf_A=self.if_ibuf_A_2,
                if_ibuf_B=self.if_ibuf_B,
                if_obuf_A=self.if_obuf_A,
                if_obuf_B=self.if_obuf_B,
                if_lb=self.if_lb,
                if_bcom_A=self.if_bcom_A,
                if_bcom_B=self.if_bcom_B,
                if_regs_A=self.if_regs_A,
                if_regs_B=self.if_regs_B,
                is_dual_channel=self.is_dual_channel,
            )
        )

        """
            Monitor Channel A Rank A Row A
        """
        self.if_bus_csca_o = If_bus_csca_o()
        self.comb += self.if_bus_csca_o.qcs_n.eq(self.if_obuf_A.qacs_a_n)
        self.comb += self.if_bus_csca_o.qca.eq(self.if_obuf_A.qaca_a)

        self.config_monitor_egress = {
            "monitor_type": MonitorType.ONE_N,
            "ingress": False,
            "channel": "A",
            "rank": "A",
            "row": "A"
        }

        self.submodules.xmonitor_egress = ClockDomainsRenamer("sys")(
            BusCSCAMonitorDev(
                if_ibuf_i=self.if_bus_csca_o,
                is_sim_finished=self.xenvironment.agent.sequencer.is_sim_finished,
                config=self.config_monitor_egress
            )
        )

        """
            Monitor RCD State
        """
        self.config_monitor_rcd = {
            "state_name_list": [
                "PON_DRST_EVENT",
                "STABLE_POWER_RESET",
                "POST_PON_DRST_EVENT",
                "INIT_IDLE",
                "DCSTM",
                "DCATM",
                "POST_TM_INIT_IDLE",
                "NORMAL",
            ]
        }

        xmonitor_rcd = Monitor(
            [
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "PON_DRST_EVENT"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "STABLE_POWER_RESET"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "POST_PON_DRST_EVENT"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "INIT_IDLE"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "DCSTM"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "DCATM"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "POST_TM_INIT_IDLE"),
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "NORMAL"),
            ],
            is_sim_finished=self.xenvironment.agent.sequencer.is_sim_finished,
            config=self.config_monitor_rcd
        )
        self.submodules.xmonitor_rcd = xmonitor_rcd

        """
            Monitor DCSTM
        """
        self.config_monitor_dcstm = {}
        xmonitor_dcstm = Monitor(
            [
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "DCSTM"),
                self.xrcd_core.xchannel_A.xcontrol_center.xregisters.xreg_file.registers[2],
                self.if_ibuf_A.dcs_n,
                self.if_ibuf_A.dca,
                self.if_ibuf_A.dpar,
                self.if_alert_n.alert_n,
            ],
            is_sim_finished=self.xenvironment.agent.sequencer.is_sim_finished,
            config=self.config_monitor_dcstm
        )
        self.submodules.xmonitor_dcstm = xmonitor_dcstm

        """
            Monitor DCATM
        """
        self.config_monitor_dcatm = {}
        xmonitor_dcatm = Monitor(
            [
                self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing(
                    "DCATM"),
                self.xrcd_core.xchannel_A.xcontrol_center.xregisters.xreg_file.registers[2],
                self.if_ibuf_A.dcs_n,
                self.if_ibuf_A.dca,
                self.if_ibuf_A_2.dpar,
                self.if_alert_n.alert_n,
            ],
            is_sim_finished=self.xenvironment.agent.sequencer.is_sim_finished,
            config=self.config_monitor_dcatm
        )
        self.submodules.xmonitor_dcatm = xmonitor_dcatm

        """
        TODO Hack
        """
        self.comb += If(
            self.xrcd_core.xchannel_A.xcontrol_center.xfsm.ongoing("DCATM"),
            self.if_ibuf_A_2.dpar.eq(0)
        ).Else(
            self.if_ibuf_A_2.dpar.eq(self.if_ibuf_A.dpar)
        )
        """
            Generators
        """
        self.add_generators(
            self.generators_dict()
        )

    def tb_run(self):
        yield self.if_ck_rst.drst_n.eq(0)
        t = t_sum(["RESET", "t_r_init_1"])
        for _ in range(t):
            yield
        yield self.if_ck_rst.drst_n.eq(1)

    def generators_dict(self):
        return {
            "sys":
            [
                self.xenvironment.run_env(
                    scenario_select=EnvironmentScenarios.INITIALIZATION_TEST),
                self.tb_run(),
                self.xmonitor_ingress.monitor(),
                self.xmonitor_egress.monitor(),
                self.xmonitor_rcd.monitor(),
                self.xmonitor_dcstm.monitor(),
                self.xmonitor_dcatm.monitor(),
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


class DDR5RCD01CoreTests_SingleChannel(unittest.TestCase):

    def setUp(self):
        self.tb = TestBed(is_dual_channel=False)
        """
            Waveform file
        """
        self.dir_name = "./wave_ut"
        if not os.path.exists(self.dir_name):
            os.mkdir(self.dir_name)
        self.file_name = self._testMethodName
        self.wave_file_name = self.dir_name + '/' + self.file_name + ".vcd"
        """
            Logging
        """
        self.LOG_FILE_NAME = self.dir_name + '/' + self.file_name + ".log"
        FORMAT = "[%(module)s.%(funcName)s] %(message)s"
        fileHandler = logging.FileHandler(
            filename=self.LOG_FILE_NAME, mode='w')
        fileHandler.formatter = logging.Formatter(FORMAT)
        streamHandler = logging.StreamHandler()

        logger = logging.getLogger('root')
        logger.addHandler(fileHandler)
        logger.addHandler(streamHandler)
        # logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.ERROR)

    def tearDown(self):
        del self.tb

    def test_ddr5_rdimm_init(self):
        logger = logging.getLogger('root')

        """
            migen simulation
        """
        run_simulation(
            self.tb,
            generators=self.tb.run_test(),
            clocks=self.tb.xcrg.clocks,
            vcd_name=self.wave_file_name
        )

        """
            Post-processing validation modules
        """
        self.tb.processor_rcd = RCDStatePS(
            sig_list=self.tb.xmonitor_rcd.signal_list,
            config=self.tb.xmonitor_rcd.config,
        )
        self.tb.processor_rcd.post_process()

        self.tb.processor_dcstm = RCDDCSTMPS(
            sig_list=self.tb.xmonitor_dcstm.signal_list,
            config=self.tb.xmonitor_dcstm.config,
        )
        self.tb.processor_dcstm.post_process()

        self.tb.processor_dcatm = RCDDCATMPS(
            sig_list=self.tb.xmonitor_dcatm.signal_list,
            config=self.tb.xmonitor_dcatm.config,
        )
        self.tb.processor_dcatm.post_process()

        self.tb.processor_ingress = BusCSCAMonitorPostProcessor(
            signal_list=self.tb.xmonitor_ingress.signal_list,
            config=self.tb.xmonitor_ingress.config,
            sim_state_list=self.tb.processor_rcd.sig_list,
            sim_state_config=self.tb.xmonitor_rcd.config["state_name_list"],
        )
        self.tb.processor_ingress.post_process()

        self.tb.processor_egress = BusCSCAMonitorPostProcessor(
            signal_list=self.tb.xmonitor_egress.signal_list,
            config=self.tb.xmonitor_egress.config,
            sim_state_list=self.tb.processor_rcd.sig_list,
            sim_state_config=self.tb.xmonitor_rcd.config["state_name_list"],
        )
        self.tb.processor_egress.post_process()

        """
            Debug logs
        """
        commands_ingress = self.tb.processor_ingress.commands
        commands_egress = self.tb.processor_egress.commands

        logger_change_log_file(old_log_file_name=self.file_name,
                               new_log_file_name=self.dir_name+"/traffic_ingress.log")
        for commands in [commands_ingress]:
            logging.debug("Commands")
            for cmd in commands:
                logging.debug(cmd)
            logging.debug("----------------")

        logger_change_log_file(old_log_file_name="traffic_ingress",
                               new_log_file_name=self.dir_name+"/traffic_egress.log")
        for commands in [commands_egress]:
            logging.debug("Commands")
            for cmd in commands:
                logging.debug(cmd)
            logging.debug("----------------")

        logger_change_log_file(
            old_log_file_name="traffic_egress", new_log_file_name=self.LOG_FILE_NAME)

        """
            Validation
        """
        sim_state_list = self.tb.processor_rcd.sim_states
        expected_sim_state_list = ['PON_DRST_EVENT', 'STABLE_POWER_RESET', 'POST_PON_DRST_EVENT',
                                   'INIT_IDLE', 'DCSTM', 'INIT_IDLE', 'DCSTM', 'DCATM', 'POST_TM_INIT_IDLE', 'NORMAL']
        assert sim_state_list == expected_sim_state_list, "RCD main FSM states are not as expected"

        self.tb.scoreboard = BusCSCAScoreboard(
            p=self.tb.processor_ingress,
            p_other=self.tb.processor_egress,
        )


if __name__ == '__main__':
    unittest.main()
