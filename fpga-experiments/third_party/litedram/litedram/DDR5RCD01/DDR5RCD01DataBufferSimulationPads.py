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

class DDR5RCD01DataBufferSimulationPads(SimulationPads):
    """ The DDR5RCD01DataBufferSimulationPads shall provide SimulationPads
    for the DDR5 Data Signals: dq,cb,dqs.
    Note, the pads are the same for ingress and egress traffic.
    """
    def layout(self, dq_w=32, cb_w=8, dqs_w=10):
        dq_dqs_ratio = (dq_w + cb_w) // dqs_w
        channel = [
            SimPad('dq', dq_w, True, dq_dqs_ratio),
            SimPad('cb', cb_w, True, dq_dqs_ratio),
            SimPad('dqs_t', dqs_w, True, 1),
            SimPad('dqs_c', dqs_w, True, 1),
        ]
        return channel

if __name__ == "__main__":
    p = DDR5RCD01DataBufferSimulationPads()
