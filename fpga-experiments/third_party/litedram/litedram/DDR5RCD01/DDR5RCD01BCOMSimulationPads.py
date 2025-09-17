#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# Litedram
from litedram.phy.sim_utils import SimPad, SimulationPads


class DDR5RCD01BCOMSimulationPads(SimulationPads):
    """ DDR5 RCD01 BCOM SimulationPads
    """
    def layout(self):
        # BCOM is only used by LRDIMM
        bcom = [
            SimPad('bcs_n', 1, False),
            SimPad('bcom', 3, False),
            SimPad('brst_n', 1, False),
            SimPad('bck_t', 1, False),
            SimPad('bck_c', 1, False),
        ]
        return bcom


if __name__ == "__main__":
    p = DDR5RCD01BCOMSimulationPads()
