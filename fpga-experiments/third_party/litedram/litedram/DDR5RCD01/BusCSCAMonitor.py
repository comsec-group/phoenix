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
from litedram.DDR5RCD01.monitor_definitions import *
from test.CRG import CRG


class BusCSCAMonitor(Module):
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
    """

    def __init__(self,
                 if_ibuf_i,
                 is_sim_finished,
                 monitor_arr_d=128):
        self.xarr_post_sim = []
        self.is_sim_finished = is_sim_finished
        self.monitor_q = MonitorQueue(q=[])

        if isinstance(if_ibuf_i, If_ibuf):
            self.is_type = MonitorType.DDR

            dcs_n_w = len(if_ibuf_i.dcs_n)
            dcs_n = Signal(dcs_n_w)

            dca_w = len(if_ibuf_i.dca)
            dca = Signal(dca_w)

            dpar = Signal()
            dpar_w = len(dpar)

            self.comb += dcs_n.eq(if_ibuf_i.dcs_n)
            self.comb += dca.eq(if_ibuf_i.dca)
            self.comb += dpar.eq(if_ibuf_i.dpar)
        elif isinstance(if_ibuf_i, If_bus_csca_o):
            self.is_type = MonitorType.ONE_N

            dcs_n_w = len(if_ibuf_i.qcs_n)
            dcs_n = Signal(dcs_n_w)

            dca_w = len(if_ibuf_i.qca)
            dca = Signal(dca_w)

            self.comb += dcs_n.eq(if_ibuf_i.qcs_n)
            self.comb += dca.eq(if_ibuf_i.qca)
        else:
            raise TypeError(
                "Monitor received an interface, which is not supported. Expected=[If_ibuf, if_bus_csca_o]")

        """
            XOR edge detection
        """
        del_dcs_n = Signal(dcs_n_w, reset=~0)
        self.sync += del_dcs_n.eq(dcs_n)

        del_dca = Signal(dca_w, reset=0)
        self.sync += del_dca.eq(dca)

        if self.is_type == MonitorType.DDR:
            del_dpar = Signal(reset=0)
            self.sync += del_dpar.eq(dpar)

        det_edge = Signal(2)
        self.comb += det_edge.eq(dcs_n ^ del_dcs_n)

        det_posedge = Signal(2)
        self.comb += det_posedge.eq(det_edge & dcs_n)

        det_negedge = Signal(2)
        self.comb += det_negedge.eq(det_edge & ~dcs_n)

        """
            Detect if command is present on the bus
        """
        cmd_len = Signal(16)
        cmd_len_w = len(cmd_len)

        counter_invalid = Signal(cmd_len_w)
        counter_en = Signal()
        counter_rst = Signal(reset=0)
        cmd_active = Signal()

        is_1_ui_command = Signal()
        self.comb += is_1_ui_command.eq(dca[1])

        if self.is_type == MonitorType.DDR:
            set_ui_counter_1ui = 2
            set_ui_counter_2ui = 4
        elif self.is_type == MonitorType.ONE_N:
            set_ui_counter_1ui = 2
            set_ui_counter_2ui = 4

        ui_counter = Signal(8)
        self.sync += If(
            det_negedge,
            If(
                is_1_ui_command,
                ui_counter.eq(set_ui_counter_1ui)
            ).Else(
                ui_counter.eq(set_ui_counter_2ui)
            )
        ).Else(
            If(
                ui_counter > 0,
                ui_counter.eq(ui_counter-1)
            ).Else(
                ui_counter.eq(ui_counter)
            )
        )

        self.comb += If(
            ui_counter > 0,
            cmd_active.eq(1)
        )

        """
            Invalid counter
            Multiple invalid cycles (cs kept high) are counted and kept in the

        """
        counter_save = Signal()
        self.comb += If(
            det_negedge,
            counter_save.eq(1),
        )
        self.comb += If(
            cmd_active == 1,
            counter_en.eq(0),
            counter_rst.eq(1),
        ).Else(
            counter_en.eq(1),
            counter_rst.eq(0),
        )

        self.sync += If(
            counter_rst,
            counter_invalid.eq(0),
        ).Else(
            If(
                counter_en,
                counter_invalid.eq(counter_invalid + 1)
            )
        )



        cmd_len = Signal(16)
        self.comb += If(
            counter_save,
            cmd_len.eq(counter_invalid)
        ).Else(
            cmd_len.eq(1)
        )

        del_cmd_active = Signal()
        self.sync += del_cmd_active.eq(cmd_active)
        is_follow_up = Signal()
        self.comb += is_follow_up.eq(cmd_active & del_cmd_active)

        cmd_type = Signal(4)
        self.sync += If(
            det_negedge,
            If(
                is_1_ui_command,
                cmd_type.eq(MonitorCommandType.SINGLE_UI)
            ).Else(
                cmd_type.eq(MonitorCommandType.DOUBLE_UI)
            )
        ).Else(
            If(
                cmd_active,
                cmd_type.eq(MonitorCommandType.FOLLOW_UP)
            ).Else(
                cmd_type.eq(MonitorCommandType.INACTIVE)
            )
        )

        """
            Save monitor data to an array
        """
        xarr_we = Signal()
        if self.is_type == MonitorType.DDR:
            self.comb += xarr_we.eq(
                counter_save | cmd_active
            )
        elif self.is_type == MonitorType.ONE_N:
            self.comb += xarr_we.eq(
                counter_save |
                (cmd_active & (ui_counter == 4)) |
                (cmd_active & (ui_counter == 2))
            )

        xarr_ptr = Signal(cmd_len_w)
        self.xarr_is_active = Array(Signal() for _ in range(monitor_arr_d))
        self.xarr_is_follow_up = Array(Signal() for _ in range(monitor_arr_d))
        self.xarr_cmd_len = Array(Signal(16) for _ in range(monitor_arr_d))
        self.xarr_cmd_type = Array(Signal(4) for _ in range(monitor_arr_d))
        self.xarr_dcs_n = Array(Signal(dcs_n_w) for _ in range(monitor_arr_d))
        self.xarr_dca = Array(Signal(dca_w) for _ in range(monitor_arr_d))
        if self.is_type == MonitorType.DDR:
            self.xarr_dpar = Array(Signal() for _ in range(monitor_arr_d))

        if self.is_type == MonitorType.DDR:
            self.sync += If(
                xarr_we,
                self.xarr_is_active[xarr_ptr].eq(cmd_active),
                self.xarr_is_follow_up[xarr_ptr].eq(is_follow_up),
                self.xarr_cmd_len[xarr_ptr].eq(cmd_len),
                self.xarr_cmd_type[xarr_ptr].eq(cmd_type),
                self.xarr_dcs_n[xarr_ptr].eq(del_dcs_n),
                self.xarr_dca[xarr_ptr].eq(del_dca),
                self.xarr_dpar[xarr_ptr].eq(del_dpar),
            )
        elif self.is_type == MonitorType.ONE_N:
            self.sync += If(
                xarr_we,
                self.xarr_is_active[xarr_ptr].eq(cmd_active),
                self.xarr_is_follow_up[xarr_ptr].eq(is_follow_up),
                self.xarr_cmd_len[xarr_ptr].eq(cmd_len),
                self.xarr_cmd_type[xarr_ptr].eq(cmd_type),
                self.xarr_dcs_n[xarr_ptr].eq(del_dcs_n),
                self.xarr_dca[xarr_ptr].eq(del_dca),
            )

        self.sync += If(
            xarr_we,
            xarr_ptr.eq(xarr_ptr+1)
        )

        self.xarr_overflow = Signal()
        self.comb += If(
            xarr_ptr >= monitor_arr_d,
            self.xarr_overflow.eq(1)
        )

    def monitor(self):
        while not self.is_sim_finished[0]:
            xarr_is_active = yield self.xarr_is_active
            xarr_is_follow_up = yield self.xarr_is_follow_up
            xarr_cmd_len = yield self.xarr_cmd_len
            xarr_cmd_type = yield self.xarr_cmd_type
            xarr_dcs_n = yield self.xarr_dcs_n
            xarr_dca = yield self.xarr_dca
            yield
        if self.is_type == MonitorType.DDR:
            xarr_dpar = yield self.xarr_dpar
            self.xarr_post_sim = list(zip(xarr_is_active, xarr_is_follow_up, xarr_cmd_len,
                                          xarr_cmd_type, xarr_dcs_n, xarr_dca, xarr_dpar))
        elif self.is_type == MonitorType.ONE_N:
            self.xarr_post_sim = list(zip(xarr_is_active, xarr_is_follow_up, xarr_cmd_len,
                                          xarr_cmd_type, xarr_dcs_n, xarr_dca))

    def post_process(self):
        xarr_monitor_ctrls = []
        for id, item in enumerate(self.xarr_post_sim):
            xarr_monitor_ctrls.append(MonitorUI(item, is_type=self.is_type))
        # breakpoint()
        self.squash_follow_ups(xarr=xarr_monitor_ctrls)
        # breakpoint()
        self.monitor_q.filter_inactive()
        self.monitor_q.report()

    def squash_follow_ups(self, xarr):
        bus_cs_ca_cmd = []
        for id, item in enumerate(xarr):
            if item.cmd_type == MonitorCommandType.SINGLE_UI:
                if self.is_type == MonitorType.DDR:
                    """ Expect that the next entry is a follow-up"""
                    if xarr[id+1].cmd_type == MonitorCommandType.FOLLOW_UP:
                        bus_cs_ca_cmd.append(MonitorCommand(
                            [xarr[id+_] for _ in range(2)]))
                elif self.is_type == MonitorType.ONE_N:
                    # """ Expect that the _+2 is a follow-up"""
                    # if xarr[id+1].cmd_type == MonitorCommandType.FOLLOW_UP:
                    bus_cs_ca_cmd.append(
                        MonitorCommand([xarr[id+_] for _ in [0]])
                    )
                    # pass

            if item.cmd_type == MonitorCommandType.DOUBLE_UI:
                if self.is_type == MonitorType.DDR:
                    """ Expect that the next 3 entries are follow-ups"""
                    follow_up_ids = [1, 2, 3]
                    follow_ups_types = [
                        xarr[id+m].cmd_type for m in follow_up_ids]
                    are_follow_ups = [(MonitorCommandType.FOLLOW_UP == follow_up_type)
                                      for follow_up_type in follow_ups_types]
                    if all(are_follow_ups):
                        bus_cs_ca_cmd.append(MonitorCommand(
                            [xarr[id+_] for _ in range(4)]))
                elif self.is_type == MonitorType.ONE_N:
                    """ Expect that the _+1 entry is a follow-up"""
                    follow_up_ids = [1]
                    follow_ups_types = [
                        xarr[id+m].cmd_type for m in follow_up_ids]
                    are_follow_ups = [(MonitorCommandType.FOLLOW_UP == follow_up_type)
                                      for follow_up_type in follow_ups_types]
                    if all(are_follow_ups):
                        bus_cs_ca_cmd.append(MonitorCommand(
                            [xarr[id+_] for _ in [0, 1]]))

                        pass

            if item.cmd_type == MonitorCommandType.INACTIVE:
                bus_cs_ca_cmd.append(MonitorCommand([xarr[id]]))

            if bus_cs_ca_cmd != []:
                self.monitor_q.q.append(bus_cs_ca_cmd[0])

            bus_cs_ca_cmd = []


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
        self.submodules.monitor = BusCSCAMonitor(
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
    tb.monitor.post_process()
    logging.debug(str(tb.monitor.monitor_q))

    xscoreboard = BusCSCAScoreboard(
        q1=tb.monitor.monitor_q,
        q2=tb.monitor.monitor_q
    )
    # breakpoint()
    logging.info(str(eT))
