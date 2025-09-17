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


class DDR5RCD01ChannelIngressSimulationPads(SimulationPads):
    """ DDR5 RCD01 Common Ingress Simulation Pads
    """

    def layout(self, dcs_n_w=2, dca_w=7):
        channel = [
            # Address/Command
            SimPad('dcs_n', dcs_n_w, False),
            SimPad('dca', dca_w, False),
            # Parity
            SimPad('dpar', 1, False),
        ]
     
        return channel


if __name__ == "__main__":
    p = DDR5RCD01ChannelIngressSimulationPads()
