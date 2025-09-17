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


class DDR5RCD01CoreEgressSimulationPads(SimulationPads):
    """ DDR5 RCD01 Core Egress SimulationPads
    """

    def __init__(self):
        super().__init__()

    def layout(self, dcs_n_w=2, dca_w=14):
        egress = [
            # Loopback sources
            SimPad('dlbd', 1, False),
            SimPad('dlbs', 1, False),
            # SDRAM raises an error
            SimPad('derror_in_n', 1, False),
            # Reset
            SimPad('qrst_n', 1, False),
            # Adress, Chip Select
            # Top Row
            SimPad('qacs_n', dcs_n_w, False),
            SimPad('qaca', dca_w, False),
            # Bottom Row
            SimPad('qbcs_n', dcs_n_w, False),
            SimPad('qbca', dca_w, False),
            # Clock outputs
            # Rank 0, Row Top
            SimPad('qack_t', 1, False),
            SimPad('qack_c', 1, False),
            # Rank 1, Row Top
            SimPad('qbck_t', 1, False),
            SimPad('qbck_c', 1, False),
            # Rank 0, Row Bottom
            SimPad('qcck_t', 1, False),
            SimPad('qcck_c', 1, False),
            # Rank 1, Row Top
            SimPad('qdck_t', 1, False),
            SimPad('qdck_c', 1, False),
        ]
        return egress


if __name__ == "__main__":
    pe_sc = DDR5RCD01CoreEgressSimulationPads()
