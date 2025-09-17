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
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *


class DDR5RCD01CommandReceiveBlocker(Module):
    """
        DDR5 RCD01 Command Receive Blocker
        to be inserted in between the input buffer and the decoder (command logic)
        Module
        ------

        Parameters
        ------
        if_ctrl.block
    """

    def __init__(self,
                 if_ibuf :If_ibuf,
                 if_ibuf_o : If_ibuf,
                 if_ctrl : If_ctrl_blocker,
                 ):

        _HIGH = ~0
        _LOW = 0

        self.comb += If(
            if_ctrl.block,
            if_ibuf_o.dcs_n.eq(_HIGH),
            if_ibuf_o.dca.eq(_HIGH),
            if_ibuf_o.dpar.eq(_HIGH),
        ).Else(
            if_ibuf_o.dcs_n.eq(if_ibuf.dcs_n),
            if_ibuf_o.dca.eq(if_ibuf.dca),
            if_ibuf_o.dpar.eq(if_ibuf.dpar),
        )


if __name__ == "__main__":
    NotSupportedException
