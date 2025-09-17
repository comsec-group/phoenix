#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *


class DDR5RCD01LoopbackCommon(Module):
    """
        DDR5 RCD Loopback Common
        ------------------------
    TODO Documentation
  """

    def __init__(self,
                lbd_a,
                lbs_a,
                lbd_b,
                lbs_b,
                qlbd,
                qlbs,
                if_ctrl,
                if_config,
                ):
        self.comb += If(
            if_ctrl.lb_sel_channel_A_B,
            qlbd.eq(lbd_b),
            qlbs.eq(lbs_b),
        ).Else(
            qlbd.eq(lbd_a),
            qlbs.eq(lbs_a),
        )

if __name__ == "__main__":
   NotSupportedException