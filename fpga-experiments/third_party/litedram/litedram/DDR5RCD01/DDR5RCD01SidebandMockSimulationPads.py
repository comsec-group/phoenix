#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# LiteDRAM
from litedram.phy.sim_utils import SimPad, SimulationPads

from litedram.DDR5RCD01.RCD_definitions import *


class DDR5RCD01SidebandMockSimulationPads(SimulationPads):
    """ DDR5 RCD01 Sideband Mock SimulationPads
    TODO Documentation
    TODO layout parameters fix
    """

    def layout(self):
        sideband = [
            SimPad('we', 1),
            SimPad('channel', 4),
            SimPad('page_num', CW_REG_BIT_SIZE),
            SimPad('reg_num', CW_REG_BIT_SIZE),
            SimPad('data', CW_REG_BIT_SIZE),
        ]
        return sideband


if __name__ == "__main__":
    p = DDR5RCD01SidebandMockSimulationPads()
