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
from litedram.DDR5RCD01.DDR5RCD01Registers import DDR5RCD01Registers
from litedram.DDR5RCD01.I2CMockMaster import I2CMockMaster
from litedram.DDR5RCD01.I2CMockSlave import I2CMockSlave
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
            I2C master
            Master is responsible for generating a WR/RD pattern
        """
        if_mock = If_sideband_mock()
        xmock_master = I2CMockMaster(if_mock)
        self.submodules.xmock_master = xmock_master

        """
            Slave is responsible for receiving commands from master
            and translating them into RCD Regfile reads/writes
        """
        if_regs_A = If_registers()
        if_regs_B = If_registers()
        xmock_slave = I2CMockSlave(if_mock, if_regs_A, if_regs_B)
        self.submodules.xmock_slave = xmock_slave

        """
            RCD register file
            If write is to address 0x0 to 0x5F, the write is to register file
            If write is to address 0x60 to 0xFF, the write is to pages
            Reads are always through reg_q (must set pointers before reading)
        """
        # cw_page_num = CW_PAGE_NUM
        cw_page_num = 6
        xregisters_A = DDR5RCD01Registers(
            d=if_regs_A.d,
            addr=if_regs_A.addr,
            we=if_regs_A.we,
            q=if_regs_A.q,
            cw_page_num=cw_page_num
        )
        self.submodules.xregisters_A = xregisters_A

        xregisters_B = DDR5RCD01Registers(
            d=if_regs_B.d,
            addr=if_regs_B.addr,
            we=if_regs_B.we,
            q=if_regs_B.q,
            cw_page_num=cw_page_num
        )
        self.submodules.xregisters_B = xregisters_B

        """
            Generators
        """
        self.add_generators(
            self.generators_dict()
        )

    def generators_dict(self):
        return {
            "sys":
            [
                self.seq()
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

    def seq(self):
        while (yield ResetSignal("sys")):
            yield

        yield from self.xmock_master.rcd_set_dimm_operating_speed(channel=0, rank=0, target_speed=-1)

        for channel in range(2):
            for rank in range(2):
                # wait for a little
                for _ in range(40):
                    yield

                yield from self.xmock_master.enter_dcstm(channel, rank)

                # wait for a little
                for _ in range(40):
                    yield

                yield from self.xmock_master.exit_dcstm(channel, rank)

        # wait for a little
        for _ in range(40):
            yield

    def reg_write(self, w_channel, w_page, w_reg, w_data):
        yield from self.xmock_master.write(w_channel, 0, w_reg, w_data)


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

    def test_cw_rd_wr(self):
        logger = logging.getLogger('root')
        logger.debug("-"*80)
        run_simulation(
            self.tb,
            generators=self.tb.run_test(),
            clocks=self.tb.xcrg.clocks,
            vcd_name=self.wave_file_name
        )


if __name__ == '__main__':
    unittest.main()
