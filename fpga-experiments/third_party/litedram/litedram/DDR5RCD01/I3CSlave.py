#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# LiteDRAM : RCD
from litedram.DDR5RCD01.DDR5RCD01SidebandSimulationPads import DDR5RCD01SidebandSimulationPads
from litedram.DDR5RCD01.RCD_utils import *

class I3CSlave(Module):
    """ I3C Slave
    TODO Documentation
    """

    def __init__(self, pads_sideband, **kwargs):
        # TODO implementation
        sideband_2_core = DDR5RCD01SidebandSimulationPads()
        self.submodules.sideband_2_core = sideband_2_core


if __name__ == "__main__":
    raise NotSupportedException
