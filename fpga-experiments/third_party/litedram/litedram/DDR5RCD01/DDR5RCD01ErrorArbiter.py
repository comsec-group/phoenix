#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
from operator import xor
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_utils import *


class DDR5RCD01ErrorArbiter(Module):
    """
    DDR5 RCD01 Error Arbiter
    -----------------------

    This module assigns priority of signals sent to Alert block

    Module
    ------
    <interface>

    Parameters
    ----------
    if_ctrl.is_dcstm_en
    if_ctrl.is_dcatm_en
    if_ctrl.is_normal_en
    if_ctrl.is_parity_checking_en

    """

    def __init__(self,
                 parity_error,
                 sdram_error,
                 dcstm_sample,
                 dcatm_sample,
                 error_o,
                 if_ctrl,
                 ):

        self.comb += If(
            if_ctrl.is_dcstm_en,
            error_o.eq(dcstm_sample),
        ).Elif(
            if_ctrl.is_dcatm_en,
            error_o.eq(dcatm_sample),
        ).Else(
            If(
                if_ctrl.is_parity_checking_en,
                error_o.eq(parity_error | sdram_error),
            ).Else(
                error_o.eq(sdram_error),
            )
        )


if __name__ == "__main__":
    NotSupportedException
