#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from enum import Enum
import enum

@enum.unique
class MonitorType(enum.IntEnum):
    DDR = 1
    SDR = 2
    ONE_N = 3
    TWO_N = 4

@enum.unique
class MonitorCommandType(enum.IntEnum):
    DESELECT = 0x1
    SINGLE_UI = 0x2
    DOUBLE_UI = 0x3
    MULTI = 0x4


@enum.unique
class CommandDestination(enum.IntEnum):
    RANK_A = 0
    RANK_B = 1
    RANK_AB = 2


@enum.unique
class CSEncoding(enum.IntEnum):
    SELECT_RANK_AB = 0b00
    SELECT_RANK_A = 0b01
    SELECT_RANK_B = 0b10
    DESELECT = 0b11
