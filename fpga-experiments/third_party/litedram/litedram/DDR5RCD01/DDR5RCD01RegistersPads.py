#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# LiteDRAM
from litedram.phy.sim_utils import SimPad, SimulationPads


class DDR5RCD01RegistersPads(SimulationPads):
    """ DDR5 RCD01 Channel Registers pads
    TODO Documentation
    TODO layout parameters fix
    """

    def layout(self):
        return [
            SimPad('we_A', 1),
            SimPad('d_A', 8),
            SimPad('addr_A', 8),
            SimPad('q_A', 8),

            SimPad('we_B', 1),
            SimPad('d_B', 8),
            SimPad('addr_B', 8),
            SimPad('q_B', 8),
        ]


if __name__ == "__main__":
    p = DDR5RCD01RegistersPads()
