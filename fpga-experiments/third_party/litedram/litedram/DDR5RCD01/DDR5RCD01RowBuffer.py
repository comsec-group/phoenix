#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_utils import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01LineBuffer import DDR5RCD01LineBuffer
from litedram.DDR5RCD01.DDR5RCD01OutputBuffer_CSCA import DDR5RCD01OutputBuffer_CSCA
from litedram.DDR5RCD01.DDR5RCD01OutputBuffer_CLKS import DDR5RCD01OutputBuffer_CLKS


class DDR5RCD01RowBuffer(Module):
    """DDR5 RCD01 Row Buffer
    TODO
    Row buffer is a wrapper for a line buffer and an output buffer

    Row Buffer:
        CS/CA : Line buffer - Output Buffer : CS/CA


    Module
    ------
    TODO Explain interfaces
    """

    def __init__(self,
                 if_ibuf,
                 if_obuf_csca,
                 if_pll_clk,
                 if_obuf_clks,
                 if_ctrl_lbuf,
                 if_ctrl_obuf,
                 if_ctrl_clk,
                 ):

        if_lbuf_2_obuf = If_bus_csca_o()

        xlbuf = DDR5RCD01LineBuffer(
            if_i=if_ibuf,
            if_o=if_lbuf_2_obuf,
            if_ctrl=if_ctrl_lbuf
        )
        self.submodules += xlbuf

        xobuf_csca = DDR5RCD01OutputBuffer_CSCA(
            if_i_csca=if_lbuf_2_obuf,
            if_o_csca=if_obuf_csca,
            if_ctrl=if_ctrl_obuf
        )
        self.submodules += xobuf_csca

        xobuf_clk = DDR5RCD01OutputBuffer_CLKS(
            if_i_clks=if_pll_clk,
            if_o_clks=if_obuf_clks,
            if_ctrl=if_ctrl_clk
        )
        self.submodules += xobuf_clk


if __name__ == "__main__":
    raise NotSupportedException()
