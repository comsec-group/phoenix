#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# LiteDRAM
from litedram.phy.sim_utils import SimPad, SimulationPads
# LiteDRAM : RCD


class DDR5RCD01CommonIngressSimulationPads(SimulationPads):
    """ DDR5 RCD01 Common Ingress Simulation Pads
    """

    def layout(self):
        common = [
            # Clock
            SimPad('dck_t', 1),
            SimPad('dck_c', 1),
            # Reset input (Comes from MC)
            SimPad('drst_n', 1),
            # Loopback
            SimPad('qlbd', 1),
            SimPad('qlbs', 1),
            # Raise errors
            SimPad('alert_n', 1),
        ]

        return common


if __name__ == "__main__":
    p = DDR5RCD01CommonIngressSimulationPads()
