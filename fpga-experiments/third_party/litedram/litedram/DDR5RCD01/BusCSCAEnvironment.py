#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
import random
from collections import namedtuple
from operator import xor
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.BusCSCAAgent import BusCSCAAgent
from litedram.DDR5RCD01.BusCSCACommand import *
from litedram.DDR5RCD01.RCD_sim_timings import RCD_SIM_TIMINGS, t_sum
# from test.CRG import CRG


Payload = namedtuple('payload', ['mra', 'op', 'cw'])


@enum.unique
class EnvironmentScenarios(enum.IntEnum):
    NONE = 0
    TEST_CW_WR_RD = 1
    SIMPLE_GENERIC = 2
    DECODER_UT = 3
    DECODER_MCA = 4
    DOUBLE_ONLY = 5
    TEST_ALL = 6
    INITIALIZATION_TEST = 7


class BusCSCAEnvironment(Module):
    """
        Scenarios:
            Single MRW/MRR
            Pattern MRWs/MRRs
            Random Valid
            Random Random

        Write options:
            Randomized
            Range (i,i+i,...)
            Fixed

        # Perform MRWs from addr 23,46
        ["MRW_2_RCD_PATTERN_ITER", range=[23,46], payload="random|fixed|range"]
        # Perform MRWs at random addresses
        ["MRW_2_RCD_PATTERN_RND", n=20 writes, payload="random|fixed|range"]
        ["MRW_2_RCD_SINGLE", dest_register=0x5E, dest_val=0xFF]
        ["MRW_2_DRAM_SINGLE", 3]
    """

    def __init__(self,
                 if_ibuf_o
                 ):
        self.queue = []
        xBusCSCAAgent = BusCSCAAgent(
            if_ibuf_o=if_ibuf_o,
        )
        self.submodules.agent = xBusCSCAAgent
        self.scenarios = []

    def run_from_test(self, queue):
        self.queue = queue
        yield from self.agent.run_agent(self.queue)

    def run_env(self, scenario_select=EnvironmentScenarios.NONE):
        self.build_scenario(scenario_select=scenario_select)
        yield from self.agent.run_agent(self.queue)

    def build_scenario(self, scenario_select=EnvironmentScenarios.TEST_CW_WR_RD):
        if scenario_select == EnvironmentScenarios.TEST_CW_WR_RD:
            self.queue = self.scenario_cw_wr_rd(
                inactive_pre_len=100,
                inactive_inter_len=1,
                inactive_post_len=1,
                pattern="consecutive",
                addr_begin=0x12,
                pattern_len=4
            )
        elif scenario_select == EnvironmentScenarios.SIMPLE_GENERIC:
            self.queue = self.simple_generic(
                inactive_pre_len=100,
                inactive_inter_len=4,
                inactive_post_len=1,
                pattern_len=4
            )
        elif scenario_select == EnvironmentScenarios.DECODER_UT:
            self.queue = self.simple_generic(
                inactive_pre_len=2,
                inactive_inter_len=3,
                inactive_post_len=1,
                pattern_len=4
            )
        elif scenario_select == EnvironmentScenarios.DECODER_MCA:
            self.queue = self.decoder_mca(
                inactive_pre_len=3,
                inactive_inter_len=1,
                inactive_post_len=1,
                pattern_len=2
            )
        elif scenario_select == EnvironmentScenarios.DOUBLE_ONLY:
            self.queue = self.simple_double(
                inactive_pre_len=100,
                inactive_inter_len=0,
                inactive_post_len=1,
                pattern_len=2
            )
        elif scenario_select == EnvironmentScenarios.TEST_ALL:
            self.queue = self.test_all(
                inactive_pre_len=100,
                inactive_inter_len=0,
                inactive_post_len=1,
                pattern_len=2
            )
        elif scenario_select == EnvironmentScenarios.INITIALIZATION_TEST:
            self.queue = self.test_init(
                inactive_pre_len=12,
                inactive_inter_len=0,
                inactive_post_len=1,
                pattern_len=2
            )
        else:
            self.queue = []

    def decoder_mca(self,
                    inactive_pre_len=5,
                    inactive_inter_len=0,
                    inactive_post_len=1,
                    pattern_len=4
                    ):
        scenario = []
        for i in range(inactive_pre_len):
            scenario += [BusCSCAInactive().cmd]

        for i in range(pattern_len):
            scenario += self.mca_mix()
            for j in range(inactive_inter_len):
                scenario += [BusCSCAInactive().cmd]

        for i in range(inactive_post_len):
            scenario += [BusCSCAInactive().cmd]

        return scenario

    @staticmethod
    def extend_inactive(scenario, len):
        for i in range(len):
            scenario += [BusCSCAInactive().cmd]
        return scenario

    @staticmethod
    def extend_mrw(scenario, payload):
        scenario += [BusCSCAMRW(payload=payload, is_padded=False).cmd]
        return scenario

    @staticmethod
    def extend_dcstm(scenario, len):
        for i in range(len):
            scenario += [BusCSCANOP().cmd]
            scenario += [BusCSCAInactive().cmd]
        for i in range(len):
            scenario += [BusCSCAInactive().cmd]
            scenario += [BusCSCAInactive().cmd]
        return scenario

    @staticmethod
    def extend_dcatm(scenario, len):
        for _ in range(len):
            scenario += [BusCSCADCATM().cmd]
            for _ in range(3):
                scenario += [BusCSCAInactive().cmd]

        return scenario

    def test_init(self,
                  inactive_pre_len=5,
                  inactive_inter_len=1,
                  inactive_post_len=1,
                  pattern_len=2
                  ):
        scenario = []
        t_rst = t_sum(["t_r_init_1", "t_r_init_3"])
        for i in range(t_rst):
            scenario += [BusCSCAActive().cmd]

        t_lock = t_sum(["t_stab_01"])
        scenario = self.extend_inactive(scenario, t_lock)

        """
            Give up control for sideband until t_J ???
            Right now, let host do MRWs
        """
        # scenario = self.extend_inactive(scenario, 13)

        """
            Write to frequency registers
            RW_05
        """
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x05, op=0x0F, cw=0x1))

        """
            Write to mode registers
            RW_00 RW_01
        """
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x00, op=0b00100011, cw=0x1))
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x01, op=0b10000000, cw=0x1))

        """
            DCSTM
        """
        scenario = self.extend_inactive(scenario, 1)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x02, op=0b00000010, cw=0x1))
        scenario = self.extend_inactive(scenario, 10)
        scenario = self.extend_dcstm(scenario, 8)
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x02, op=0b00000000, cw=0x1))
        scenario = self.extend_inactive(scenario, 10)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x02, op=0b00000011, cw=0x1))
        scenario = self.extend_inactive(scenario, 10)
        scenario = self.extend_dcstm(scenario, 8)
        scenario = self.extend_inactive(scenario, 3)

        """
            DCATM
        """
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x02, op=0b00000001, cw=0x1))
        scenario = self.extend_inactive(scenario, 7)
        scenario = self.extend_dcatm(scenario, 4)
        scenario = self.extend_inactive(scenario, 2)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x02, op=0b00000000, cw=0x1))

        """
            Enable QRST
            Write CMD6 and CMD8 to RW04 to clear QRST
        """
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x04, op=0x06, cw=0x1))
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x04, op=0x08, cw=0x1))

        """
            DRAM Interface Blocking
            RW_01.1
            0b00000010
        """
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x01, op=0b10000010, cw=0x1))


        """
            NOP to RW04 to release QCS
        """
        scenario = self.extend_inactive(scenario, 3)
        scenario = self.extend_mrw(scenario,
                                   payload=Payload(mra=0x04, op=0x00, cw=0x1))

        scenario = self.extend_inactive(scenario, 10)
        for i in range(pattern_len):
            scenario += self.all_mix()
            scenario = self.extend_inactive(scenario, inactive_inter_len)

        scenario = self.extend_inactive(scenario, inactive_post_len)
        return scenario

    def test_all(self,
                 inactive_pre_len=5,
                 inactive_inter_len=1,
                 inactive_post_len=1,
                 pattern_len=2
                 ):
        scenario = []
        for i in range(inactive_pre_len):
            scenario += [BusCSCAInactive().cmd]

        for i in range(pattern_len):
            scenario += self.all_mix()
            for j in range(inactive_inter_len):
                scenario += [BusCSCAInactive().cmd]

        for i in range(inactive_post_len):
            scenario += [BusCSCAInactive().cmd]

        return scenario

    def simple_double(self,
                      inactive_pre_len=5,
                      inactive_inter_len=1,
                      inactive_post_len=1,
                      pattern_len=2
                      ):
        scenario = []
        for i in range(inactive_pre_len):
            scenario += [BusCSCAInactive().cmd]

        for i in range(pattern_len):
            scenario += self.double_mix()
            for j in range(inactive_inter_len):
                scenario += [BusCSCAInactive().cmd]

        for i in range(inactive_post_len):
            scenario += [BusCSCAInactive().cmd]

        return scenario

    def simple_generic(self,
                       inactive_pre_len=5,
                       inactive_inter_len=1,
                       inactive_post_len=1,
                       pattern_len=4
                       ):
        scenario = []
        for i in range(inactive_pre_len):
            scenario += [BusCSCAInactive().cmd]

        for i in range(pattern_len):
            scenario += self.generic_mix()
            for j in range(inactive_inter_len):
                scenario += [BusCSCAInactive().cmd]

        for i in range(inactive_post_len):
            scenario += [BusCSCAInactive().cmd]

        return scenario

    def scenario_cw_wr_rd(self, inactive_pre_len=2, inactive_inter_len=2, inactive_post_len=2, pattern="consecutive", addr_begin=0, pattern_len=3):
        scenario = []
        for i in range(inactive_pre_len):
            scenario += [BusCSCAInactive().cmd]

        if pattern == "consecutive":
            for i in range(pattern_len):
                scenario += self.CW_read(rw_addr=addr_begin+i)
                for j in range(inactive_inter_len):
                    scenario += [BusCSCAInactive().cmd]
        elif pattern == "random":
            random_addrs = random.sample(list(range(0, 128)), pattern_len)
            for i in random_addrs:
                scenario += self.CW_read(rw_addr=i)
                for j in range(inactive_inter_len):
                    scenario += [BusCSCAInactive().cmd]

        for i in range(inactive_post_len):
            scenario += [BusCSCAInactive().cmd]

        return scenario

    def multi_cmd(self):
        flow = []
        for _ in range(3):
            flow += [
                BusCSCAGeneric1Multi().cmd,
            ]
        flow += [
            BusCSCAGeneric2Multi().cmd,
        ]

        return flow

    def generic_cmd(self):
        flow = []
        flow += [
            BusCSCAGeneric1().cmd,
            BusCSCAGeneric1A().cmd,
            BusCSCAGeneric1B().cmd,
            BusCSCAGeneric2().cmd,
            BusCSCAGeneric2A().cmd,
            BusCSCAGeneric2B().cmd,
        ]
        return flow

    def all_mix(self):
        flow = []

        flow += [
            BusCSCAGeneric2().cmd,
            BusCSCAGeneric2A().cmd,
            BusCSCAGeneric2B().cmd,
        ]
        flow += self.generic_cmd()
        flow += self.multi_cmd()

        return flow

    def double_mix(self):
        flow = []
        flow += [
            BusCSCAGeneric2().cmd,
            BusCSCAGeneric2A().cmd,
            BusCSCAGeneric2B().cmd,
        ]
        flow += self.multi_cmd()
        return flow

    def mca_mix(self):
        flow = []
        flow += self.generic_cmd()
        flow += self.multi_cmd()
        return flow

    def generic_mix(self):
        flow = []
        flow += [
            BusCSCAGeneric1().cmd,
            BusCSCAGeneric1A().cmd,
            BusCSCAGeneric1B().cmd,
            BusCSCAGeneric1AB().cmd,
            BusCSCAGeneric2().cmd,
            BusCSCAGeneric2A().cmd,
            BusCSCAGeneric2B().cmd,
            BusCSCAGeneric2AB().cmd,
        ]
        return flow

    def CW_read(self, rw_addr=0x00):
        """
            8.1 Reading Control Words
            Table 90 - Control Word Read Sequence
        """
        flow = []
        flow += [
            BusCSCAMRW(payload=Payload(0x5E, rw_addr, 0x1),
                       is_padded=True).cmd,
            BusCSCAMRW(payload=Payload(0x3F, 0x5A, 0x0), is_padded=True).cmd,
            BusCSCAMRR(payload=Payload(0x3F, 0x00, 0x0), is_padded=True).cmd,
        ]
        return flow


class TestBed(Module):
    def __init__(self):
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

        if_ibuf_o = If_ibuf()
        self.submodules.dut = BusCSCAEnvironment(
            if_ibuf_o=if_ibuf_o,
        )


def run_test(tb):
    logging.debug('Write test')
    scenario_select = EnvironmentScenarios.TEST_CW_WR_RD
    yield from tb.dut.run_env(scenario_select=scenario_select)
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
