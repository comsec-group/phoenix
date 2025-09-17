#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from enum import Enum
import enum
from collections import namedtuple

from migen import *

from litedram.DDR5RCD01.RCD_utils import NotSupportedException

"""
    Use shorter values for simulations below
    All values shall be ints (expressed in clk periods)
"""
RCD_SIM_TIMINGS = {
    "RESET": 10,
    "t_r_init_1": 3,
    "t_r_init_2": 3,
    "t_r_init_3": 3,
    "t_r_init_4": 3,
    "t_stab_01" : 5,
}

def t_sum(names):
    sum = 0
    for name in names:
        sum += RCD_SIM_TIMINGS[name]
    return sum

"""
    Use values from spec below
"""
RCD_SPEC_TIMINGS = {

}
if __name__ == "__main__":
    raise NotSupportedException
