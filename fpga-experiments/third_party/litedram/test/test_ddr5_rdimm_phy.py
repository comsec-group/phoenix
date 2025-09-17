# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import re
import copy
import unittest
from typing import Mapping
from functools import partial
from collections import defaultdict

from migen import *

from litedram.phy.ddr5.simphy import DDR5SimPHY
from litedram.phy.ddr5 import simsoc
from litedram.phy.sim_utils import SimLogger
from litedram.phy.utils import Serializer, Deserializer

from litedram import modules as litedram_modules
from litedram.DDR5RCD01.RCD_definitions import sideband_type as sb_enum
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.I2CMockMaster import I2CMockMasterWrapper
from litedram.DDR5RCD01.DDR5RCD01SidebandMockSimulationPads import DDR5RCD01SidebandMockSimulationPads
from litedram.DDR5RCD01.DDR5RCD01SystemWrapper import DDR5RCD01SystemWrapper
from litedram.phy.ddr5.sdram_simulation_model import DDR5SDRAMSimulationModel

import test.phy_common
from test.CRG import CRG
from test.phy_common import DFISequencer, PadChecker

sim_clocks = {
    "sys":            (64, 31),
    "sys_rst":        (64, 30),
    "sys2x":          (32, 15),
    "sys4x":          (16,  7),
    "sys4x_n":        (16, 15),
    "sys4x_ddr":      ( 8,  3),
    "sys4x_90":       (16,  3),
    "sys4x_90_ddr":   ( 8,  7),
    "sys4x_180":      (16, 15),
    "sys4x_180_ddr":  ( 8,  3),
    "sys8x_ddr":      ( 4,  1),
}

class TestSystem(Module):
    pass

class DDR5RDIMM_PHY(unittest.TestCase):
    SYS_CLK_FREQ = 50e6
    DATABITS = 8
    BURST_LENGTH = 8
    NPHASES = 4

    def tearDown(self):
        pass

    def setUp(self):
        self.crg = CRG(sim_clocks, 3)
        self.phy = DDR5SimPHY(
            sys_clk_freq=self.SYS_CLK_FREQ,
            direct_control=False,
            aligned_reset_zero=True,
            masked_write=True
        )

        pads_sideband = DDR5RCD01SidebandMockSimulationPads()
        xi2cmockmaster = I2CMockMasterWrapper(
            pads_sideband
        )
        # self.xi2cmockmaster = ClockDomainsRenamer("sys4x_ddr")(xi2cmockmaster)
        self.xi2cmockmaster = xi2cmockmaster

        xRCDSystem = DDR5RCD01SystemWrapper(
            phy_pads        = self.phy.pads,
            pads_sideband   = pads_sideband,
            rcd_passthrough = False,
            sideband_type   = sb_enum.MOCK,
        )
        self.xRCDSystem = ClockDomainsRenamer("sys4x_ddr")(xRCDSystem)

        self.RCD_outpads = {
            ('A_', 0, 1): "A_front_top",
            ('A_', 0, 0): "A_front_bottom",
            ('A_', 1, 1): "A_back_top",
            ('A_', 1, 0): "A_back_bottom",
            ('B_', 0, 1): "B_front_top",
            ('B_', 0, 0): "B_front_bottom",
            ('B_', 1, 1): "B_back_top",
            ('B_', 1, 0): "B_back_bottom",
        }
        # breakpoint()
        for domain in self.RCD_outpads.values():
            # breakpoint()
            if not hasattr(self.xRCDSystem, domain):
                continue
            """
                TODO dirty hack to filter domains. Properly implement teardown!
            """
            _tmp = "cd_"+domain+"_t"
            _cmp = "cd_"+domain+"_c"
            if hasattr(self.crg, _tmp) or hasattr(self.crg, _cmp):
                continue
            pads = getattr(self.xRCDSystem, domain)
            self.crg.add_domain(domain+"_t", sim_clocks["sys4x"], ~pads.reset_n)
            self.crg.add_domain(domain+"_c", sim_clocks["sys4x_n"], ~pads.reset_n)
            # breakpoint()

        sys_clk_freq = int(1e9)//64
        sdram_module = litedram_modules.DDR5SimX4(sys_clk_freq, "1:4")
        sdram_module.geom_settings.rowbits = 1
        domain = self.RCD_outpads[("A_", 0, 0)]
        self.pads = getattr(self.xRCDSystem, domain)
        self.sdram = DDR5SDRAMSimulationModel(
            pads          = self.pads,
            cl            = 22,
            cwl           = 20,
            sys_clk_freq  = sys_clk_freq,
            geom_settings = sdram_module.geom_settings,
            module_num    = 0,
            log_level     = "all=ERROR",
            dq_dqs_ratio  = 4,
            cd_positive=domain+"_t",
            cd_negative=domain+"_c",
            skip_fsm_to_stage=7,
        )

        self.rdphase: int = self.phy.settings.rdphase.reset.value
        self.wrphase: int = self.phy.settings.wrphase.reset.value

        self.cmd_latency:   int = self.phy.settings.cmd_latency
        self.read_latency:  int = self.phy.settings.read_latency
        self.write_latency: int = self.phy.settings.write_latency
        # read latency has to account for bitslips after dq deserializer
        read_latency_in_cycles = self.NPHASES * (self.read_latency - Deserializer.LATENCY - 1 - 1)
        write_latency_in_cycles = self.NPHASES * self.phy.settings.write_latency + 6

        # 0s, 1s and Xs for 1 sys_clk in `*_ddr` clock domain
        self.zeros: str = '0' * self.NPHASES * 2
        self.ones:  str = '1' * self.NPHASES * 2
        self.xs:    str = 'x' * self.NPHASES * 2

        # latencies to use in pad checkers
        # Extra '0' for unaligned ddr clk and cs clk
        # delay 1 + 1 + 1/8 + (Serializer.LATENCY - 1) + 0.5 to command counted in sysclk
        self.ca_latency:       str = self.xs + '0' * (2 * self.NPHASES * Serializer.LATENCY) + '0' * self.NPHASES
        self.cs_n_latency:     str = self.xs + '0' * (2 * self.NPHASES * Serializer.LATENCY) + '1' * self.NPHASES

        # -2 preamble
        self.dqs_t_rd_latency: str = self.xs * 2 + 'xx'*(self.NPHASES * Serializer.LATENCY) + 'xx' * self.NPHASES + \
                                    (self.rdphase + read_latency_in_cycles) * 'xx'
        self.dq_rd_latency:    str = self.xs * 2 + 'xx'*(self.NPHASES * Serializer.LATENCY) + 'xx' * self.NPHASES + \
                                    (self.rdphase + read_latency_in_cycles + 2) * 'xx'
        # Write latency = reset + send to dfi + sync + bitslip + cdc + serializer + preamble is 2 ddr clocks long
        min_write_latency = self.phy.settings.min_write_latency

        self.dqs_t_wr_latency: str = self.xs * 2 + 'xx'*(2*self.NPHASES*Serializer.LATENCY) + "xx" * self.NPHASES + \
                                    "xx" + "xx" * (min_write_latency - 2)
        self.dq_wr_latency:    str = self.xs * 2 + 'xx'*(2*self.NPHASES*Serializer.LATENCY) + "xx" * self.NPHASES + \
                                    "xx" + "xx" * min_write_latency

    @staticmethod
    def process_ca(ca: str) -> int:
        """dfi_address is mapped 1:1 to CA"""
        ca = ca.replace(' ', '') # remove readability spaces
        ca = ca[::-1]            # reverse bit order (also readability)
        return int(ca, 2)        # convert to int

    # Test that bank/address for different commands are correctly serialized to CA pads
    read_0       = dict(cs_n=0, address=process_ca.__func__('10111 0 10100 000'))  # RD p0
    read_1       = dict(cs_n=1, address=process_ca.__func__('001100110 01000'))    # RD p1
    write_0      = dict(cs_n=0, address=process_ca.__func__('10110 0 11100 000'))  # WR p0
    write_1      = dict(cs_n=1, address=process_ca.__func__('000000001 01100'))    # WR p1
    activate_0   = dict(cs_n=0, address=process_ca.__func__('00 1000 01000 000'))  # ACT p0
    activate_1   = dict(cs_n=1, address=process_ca.__func__('0111100001111 0'))    # ACT p1
    refresh_ab   = dict(cs_n=0, address=process_ca.__func__('11001 0 00010 000'))  # REFab
    precharge_ab = dict(cs_n=0, address=process_ca.__func__('11010 0 0000 0 000')) # PREab
    mrw_0        = dict(cs_n=0, address=process_ca.__func__('10100 11001100 0'))   # MRW p0
    mrw_1        = dict(cs_n=1, address=process_ca.__func__('01010101 00 0 000'))  # MRW p1
    zqc_start    = dict(cs_n=0, address=process_ca.__func__('11110 10100000'))     # MPC + ZQCAL START op
    zqc_latch    = dict(cs_n=0, address=process_ca.__func__('11110 00100000'))     # MPC + ZQCAL LATCH op
    mrr_0        = dict(cs_n=0, address=process_ca.__func__('10101 10110100 0'))   # MRR p0
    mrr_1        = dict(cs_n=1, address=process_ca.__func__('0000000000 0 000'))   # MRR p1

    two_cycle_commands = ['10111', '10110', '00', '10100', '10101']

    @classmethod
    def to_2N_mode(cls, instructions):
        ret = {}
        two_cycles = False
        for cycle, instruction in enumerate(instructions):
            for phase, value in instruction.items():
                idx = idx0 = (cycle, phase)
                if two_cycles:
                    two_cycles = False
                    new_dfi_cycle = cycle * cls.NPHASES + phase + 1
                    idx0 = (new_dfi_cycle//cls.NPHASES, new_dfi_cycle % cls.NPHASES)
                elif 'address' in value:
                    for pre in cls.two_cycle_commands:
                        _cmd = f'{value["address"]:014b}'
                        if _cmd[::-1].startswith(pre):
                            two_cycles=True
                idx1 = idx0[0] + (idx0[1] + 1) // cls.NPHASES, (idx0[1] + 1) % cls.NPHASES
                if idx0 not in ret:
                    ret[idx0] = {}
                if idx1 not in ret:
                    ret[idx1] = {}
                for key, word in value.items():
                    if "address" in key:
                        ret[idx0]['mode_2n'] = 1
                        ret[idx1]['mode_2n'] = 1
                        ret[idx0][key]       = word
                        ret[idx1][key]       = word
                    elif "cs" in key:
                        ret[idx0]['mode_2n'] = 1
                        ret[idx1]['mode_2n'] = 1
                        ret[idx0][key]       = word
                        ret[idx1][key]       = 1
                    else:
                        ret[idx][key ]      = word
        flatten = []
        for key, value in sorted(ret.items(), reverse=True):
            cycle, phase = key
            while len(flatten) <= cycle:
                flatten.append({})
            flatten[cycle][phase] = value
        return flatten

    @classmethod
    def dq_pattern(cls, *args, **kwargs) -> str:
        return test.phy_common.dq_pattern(
            *args,
            databits=cls.DATABITS,
            nphases=cls.NPHASES,
            burst=cls.BURST_LENGTH,
            **kwargs,
        )

    @staticmethod
    def rdimm_mode(dut, _rdimm_mode):
        yield dut._rdimm_mode.storage.eq(_rdimm_mode)
        yield

    def controller_generator(self):
        yield

    def generators_dict(self):
        return {
            "sys":
            [
               self.controller_generator(),
            ]
        }

    def run_test(self, dfi_sequence, pad_checkers: Mapping[str, Mapping[str, str]], pad_generators=None, stimulus_generators = {}, **kwargs):
        # pad_checkers: {clock: {sig: values}}
        self.dut = dut = TestSystem()
        dut.submodules.crg = self.crg
        dut.submodules.phy = self.phy
        # dut.submodules.xRCDSystem = self.xRCDSystem
        # dut.submodules.sdram = self.sdram
        dfi = DFISequencer([{}, {}] + dfi_sequence)
        checkers = {clk: PadChecker(self.pads, pad_signals) for clk, pad_signals in pad_checkers.items()}
        generators = defaultdict(list)
        generators["sys"].append(dfi.generator(dut.phy.dfi))
        generators["sys"].append(dfi.reader(dut.phy.dfi))
        generators["sys"].append(DDR5RDIMM_PHY.rdimm_mode(dut.phy, 1))
        for clock, checker in checkers.items():
            generators[clock].append(checker.run())
        pad_generators = pad_generators or {}
        for clock, gens in pad_generators.items():
            gens = gens if isinstance(gens, list) else [gens]
            for gen in gens:
                generators[clock].append(gen(self.pads))
        for gens in stimulus_generators.values():
            generators["sys"].extend(gens)
        test.phy_common.run_simulation(dut, generators, clocks=self.crg.clocks, **kwargs)
        # PadChecker.assert_ok(self, checkers)
        # dfi.assert_ok(self)

    def test_ddr5_rcd_simple(self):
        # Test that CS_n is serialized correctly when sending command on phase 0
        self.run_test(
            dfi_sequence = [
                *[{} for _ in range(100)],
                {0: self.read_0, 1: self.read_1},
                {0: self.write_0, 1: self.write_1},
                {0: self.activate_0, 1: self.activate_1},
                {0: self.refresh_ab},
                {0: self.precharge_ab},
                {0: self.mrw_0, 1: self.mrw_1},
                {0: self.zqc_start},
                {0: self.zqc_latch},
                {0: self.mrr_0, 1: self.mrr_1},
                *[{} for _ in range(5)],
            ],
            pad_checkers = {"sys4x_180": {
                'cs_n': self.cs_n_latency + '01111111',
            }},
            vcd_name="ddr5_rdimm_phy_cs_n_phase_0_1N.vcd"
        )

    def test_ddr5_rcd_initialization(self):
        self.run_test(
            dfi_sequence = [
                *[{} for _ in range(100)],
                {0: self.read_0, 1: self.read_1},
                {0: self.write_0, 1: self.write_1},
                {0: self.activate_0, 1: self.activate_1},
                {0: self.refresh_ab},
                {0: self.precharge_ab},
                {0: self.mrw_0, 1: self.mrw_1},
                {0: self.zqc_start},
                {0: self.zqc_latch},
                {0: self.mrr_0, 1: self.mrr_1},
                *[{} for _ in range(5)],
            ],
            pad_checkers = {"sys4x_180": {
                'cs_n': self.cs_n_latency + '01111111',
            }},
            stimulus_generators=self.generators_dict(),
            vcd_name="test_ddr5_rcd_initialization.vcd"
        )

    def test_ddr5_rcd_stable_power_init(self):
        self.run_test(
            dfi_sequence = [
                *[{} for _ in range(5)],
                {0: self.read_0, 1: self.read_1},
                {0: self.write_0, 1: self.write_1},
                {0: self.read_0, 1: self.read_1},
                {0: self.write_0, 1: self.write_1},
                {0: self.activate_0, 1: self.activate_1},
                {0: self.refresh_ab},
                {0: self.precharge_ab},
                {0: self.mrw_0, 1: self.mrw_1},
                {0: self.zqc_start},
                {0: self.zqc_latch},
                {0: self.mrr_0, 1: self.mrr_1},
                *[{} for _ in range(5)],
            ]
            ,
            pad_checkers = {"sys4x_180": {
                'cs_n': self.cs_n_latency + '01111111',
            }},
            vcd_name="ddr5_stable_power_init.vcd"
        )

