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


@enum.unique
class MonitorType(enum.IntEnum):
    DDR = 1
    SDR = 2
    ONE_N = 3
    TWO_N = 4


@enum.unique
class MonitorCommandType(enum.IntEnum):
    INACTIVE = 0x1
    SINGLE_UI = 0x2
    DOUBLE_UI = 0x3
    FOLLOW_UP = 0xF


class MonitorCommand:
    def __init__(self, monitor_ui_list):
        self.cmd = monitor_ui_list

    def __str__(self):
        s = ""
        for id, cmd in enumerate(self.cmd):
            s += f"UI[{id}]: "
            s += str(cmd)
            s += "\r\n"
        return s


@dataclass
class MonitorUI:
    """
    Track monitor signals
    """
    is_active: int
    is_follow_up: int
    cmd_len: int
    cmd_type: int
    dcs_n: int
    dca: int
    dpar: int

    def __init__(self, tuple, is_type=MonitorType.DDR):
        self.is_type = is_type
        if self.is_type == MonitorType.DDR:
            attrs = ["is_active", "is_follow_up", "cmd_len",
                     "cmd_type", "dcs_n", "dca", "dpar"]
        elif self.is_type == MonitorType.ONE_N:
            attrs = ["is_active", "is_follow_up", "cmd_len",
                     "cmd_type", "dcs_n", "dca"]
        else:
            raise NotSupportedException
        for id, attr in enumerate(attrs):
            setattr(self, attr, tuple[id])

    def __str__(self, debug=False):
        if debug:
            s = ""
            if self.is_active:
                s += "is_active = " + str(self.is_active) + " "
                s += "cmd_len = " + str(self.cmd_len) + " "
                if self.is_follow_up:
                    s += "follow_up_UI"
                if self.cmd_type != MonitorCommandType.FOLLOW_UP:
                    if self.cmd_type == MonitorCommandType.INACTIVE:
                        s += "cmd_type = " + "INACTIVE" + " "
                    elif self.cmd_type == MonitorCommandType.SINGLE_UI:
                        s += "cmd_type = " + "1 UI CMD" + " "
                    elif self.cmd_type == MonitorCommandType.DOUBLE_UI:
                        s += "cmd_type = " + "2 UI CMD" + " "
                    s += "dcs_n = " + str(self.dcs_n) + " "
                    s += "dca = " + str(self.dca) + " "
                    if self.is_type == MonitorType.DDR:
                        s += "dpar = " + str(self.dpar) + " "
            else:
                s += "inactive"
        else:
            s = ""
            if self.is_active:
                s += "dcs_n = " + str(self.dcs_n) + " "
                s += "dca = " + str(self.dca) + " "
                if self.is_type == MonitorType.DDR:
                    s += "dpar = " + str(self.dpar) + " "
            else:
                s += "inactive"
        return s


class MonitorQueue:
    def __init__(self, q=None):
        self.q = q
        self.q_filter_inactive = []
        self.received_cmds = 0
        self.pattern_num = 0

    def filter_inactive(self):
        self.q_filter_inactive = []
        for cmd_item in self.q:
            if cmd_item.cmd[0].cmd_type != MonitorCommandType.INACTIVE:
                self.q_filter_inactive.append(cmd_item)
        self.set_statistics()

    def set_statistics(self):
        self.pattern_num = len(self.q)
        self.received_cmds = len(self.q_filter_inactive)

    def __str__(self):
        q = self.q_filter_inactive

        s = ""
        for cmd_id, cmd_item in enumerate(q):
            for id, cmd in enumerate(cmd_item.cmd):
                s += f"UI[{id}]: "
                s += str(cmd)
                s += "\r\n"
        s += "Monitor statistics\r\n"
        s += "------------------\r\n"
        s += f"Received [{self.received_cmds}] commands in [{self.pattern_num}] patterns\r\n"
        return s


if __name__ == "__main__":
    raise NotSupportedException
