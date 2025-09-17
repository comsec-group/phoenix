#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_utils import *

class DDR5RCD01DataBufferChip(Module):
    def __init__(self, pads_i):        
        print('LRDIMM Data Buffer not implemented.')
        # TODO replace print with raise in the final stage of development

if __name__ == "__main__":
    raise NotSupportedException
