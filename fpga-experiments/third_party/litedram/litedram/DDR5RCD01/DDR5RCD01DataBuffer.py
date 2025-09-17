#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# RCD
from litedram.DDR5RCD01.DDR5RCD01DataBufferChip import DDR5RCD01DataBufferChip
from litedram.DDR5RCD01.DDR5RCD01DataBufferShell import DDR5RCD01DataBufferShell
from litedram.DDR5RCD01.DDR5RCD01DataBufferSimulationPads import DDR5RCD01DataBufferSimulationPads
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *


class DDR5RCD01DataBuffer(Module):
    """ The DDR5RCD01DataBuffer is a wrapper for the DDR5 data bus. It allows to easily
    switch from the RDIMM to the LRDIMM implementation with the dimm_type flag.

    Expected behaviour:
    RDIMM - data signals are unchanged and passed through
    LRDIMM - data signals are connected to the DDR5RCD01DataBufferChip object, which
    may be implemented in the future
    """

    def __init__(self,
                 pads_ingress,
                 dimm_type=dimm_type.RDIMM,
                 **kwargs):

        if dimm_type == dimm_type.RDIMM:
            xDB = DDR5RCD01DataBufferShell(pads_ingress)

        if dimm_type == dimm_type.LRDIMM:
            xDB = DDR5RCD01DataBufferChip(pads_ingress)

        self.submodules+= xDB
        self.pads_egress = xDB.pads_egress


if __name__ == "__main__":
    pads_ingress = DDR5RCD01DataBufferSimulationPads()
    xDB = DDR5RCD01DataBuffer(
        pads_ingress=pads_ingress
    )
