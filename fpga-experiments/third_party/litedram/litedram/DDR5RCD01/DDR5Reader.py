#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
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


@enum.unique
class CmdType(enum.IntEnum):
    INACTIVE = 0x1
    SINGLE_UI = 0x2
    DOUBLE_UI = 0x3
    FOLLOW_UP = 0xF


@enum.unique
class DataRateType(enum.IntEnum):
    DDR = 1
    SDR1 = 2
    SDR2 = 3
    ONE_N = 4
    TWO_N = 5


class DDR5Reader(Module):
    """
        Wrapper provides monitors for all data rate modes, i.e.: DDR,SDR,1N,2N

        Module
        ------

        Parameters
        ----------

    """

    def __init__(self,
                 if_ibuf_i,
                 dcs_n_w=2,
                 dca_w=7,
                 monit_arr_d=128,
                 data_rate=DataRateType.DDR):

        dcs_n = Signal(dcs_n_w)
        dca = Signal(dca_w)
        dpar = Signal()

        self.comb += dcs_n.eq(if_ibuf_i.dcs_n)
        self.comb += dca.eq(if_ibuf_i.dca)
        self.comb += dpar.eq(if_ibuf_i.dpar)

        """
            XOR edge detection
        """
        del_dcs_n = Signal(dcs_n_w, reset=~0)
        self.sync += del_dcs_n.eq(dcs_n)

        del_dca = Signal(dca_w, reset=0)
        self.sync += del_dca.eq(dca)

        del_dpar = Signal(reset=0)
        self.sync += del_dpar.eq(dpar)

        det_edge = Signal(2)
        self.comb += det_edge.eq(dcs_n ^ del_dcs_n)

        det_posedge = Signal(2)
        self.comb += det_posedge.eq(det_edge & dcs_n)

        det_negedge = Signal(2)
        self.comb += det_negedge.eq(det_edge & ~dcs_n)

        cmd_active = Signal()

        is_1_ui_command = Signal()
        self.comb += is_1_ui_command.eq(dca[1])

        ui_counter_threshold = Signal(8)
        ui_counter = Signal(8)

        if data_rate == DataRateType.DDR:
            pass
        elif data_rate == DataRateType.SDR1:
            pass
        elif data_rate == DataRateType.SDR2:
            pass
        elif data_rate == DataRateType.ONE_N:
            pass
        elif data_rate == DataRateType.TWO_N:
            pass

        self.sync += If(
            det_negedge,
            If(
                is_1_ui_command,
                ui_counter.eq(2)
            ).Else(
                ui_counter.eq(4)
            )
        ).Else(
            If(
                ui_counter > 0,
                ui_counter.eq(ui_counter+1)
            ).Else(
                ui_counter.eq(ui_counter)
            )
        )

        self.comb += If(
            ui_counter > 0,
            cmd_active.eq(1)
        )


class TestBed(Module):
    def __init__(self):
        if_ibuf = If_ibuf()
        self.submodules.env = BusCSCAEnvironment(
            if_ibuf_o=if_ibuf,
        )
        self.submodules.monitor = DDR5Reader(
            if_ibuf_i=if_ibuf
        )


def run_test(tb):
    logging.debug('Write test')
    scenario_select = EnvironmentScenarios.SIMPLE_GENERIC
    yield from tb.env.run_env(scenario_select=scenario_select)
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
