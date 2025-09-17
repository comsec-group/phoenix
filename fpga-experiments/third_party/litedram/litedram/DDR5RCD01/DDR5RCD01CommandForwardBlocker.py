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


class DDR5RCD01CommandForwardBlocker(Module):
    """
        DDR5 RCD01 Command Forward Blocker
        to be inserted before the rank buffer to disable command forwarding and ensure proper state
        Module
        ------


        Parameters
        ------
        if_ctrl.block
    """

    def __init__(self,
                 if_ibuf: If_bus_csca,
                 if_ibuf_o: If_bus_csca,
                 if_clk_row_A: If_ck,
                 if_clk_row_A_o: If_ck,
                 if_clk_row_B: If_ck,
                 if_clk_row_B_o: If_ck,
                 if_ctrl: If_ctrl_blocker,
                 ):

        _HIGH = ~0
        _LOW = 0

        self.comb += If(
            if_ctrl.block,
            if_ibuf_o.cs_n.eq(_HIGH),
            if_ibuf_o.ca.eq(_HIGH),
            if_clk_row_A_o.ck_t.eq(_LOW),
            if_clk_row_A_o.ck_c.eq(_LOW),
            if_clk_row_B_o.ck_t.eq(_LOW),
            if_clk_row_B_o.ck_c.eq(_LOW),
        ).Else(
            if_ibuf_o.cs_n.eq(if_ibuf.cs_n),
            if_ibuf_o.ca.eq(if_ibuf.ca),
            if_clk_row_A_o.ck_t.eq(if_clk_row_A.ck_t),
            if_clk_row_A_o.ck_c.eq(if_clk_row_A.ck_c),
            if_clk_row_B_o.ck_t.eq(if_clk_row_B.ck_t),
            if_clk_row_B_o.ck_c.eq(if_clk_row_B.ck_c),
        )


if __name__ == "__main__":
    NotSupportedException
