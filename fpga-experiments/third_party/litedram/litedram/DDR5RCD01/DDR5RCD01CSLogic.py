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
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01Decoder import DDR5RCD01Decoder
from litedram.DDR5RCD01.DDR5RCD01Error import DDR5RCD01Error


class DDR5RCD01CSLogic(Module):
    """
        CS Logic
        The control center forwards the cmd to the deserializer by the
        If_ctrl_lbuf interface. The deserializer is placed inside of the lbuf.
        (Not optimal for synthesis).

        Commands (CA and CS_n) are forwarded in normal mode:
        1. Detect active CS_n
        2. Send the command to the DRAM interface
        Use Cases:

        1 UI command:
        - CS is low
        - CA on this edge and next is captured (c.f. RCD model clocking)

        2 UI commands:
        - CS is low only during 1st UI. Can be low if the non-target termination
        is being signalled. c.f. Table 4
        - CA must be captured on 2 more edges

        Parity error detected during a 1 UI command

        Parity error detected during a 2 UI command

        DRAM Interface Blocking Mode is enabled

        CA Pass-through Mode is enabled

        The decode portion should always listen
    """

    def __init__(self,
                 if_ibuf_i,
                 if_ibuf_o,
                 if_ctrl_lbuf,
                 inv_en=False,
                 CS_BIT_SELECT=0,
                 ):
        """
            Output inversion enable
        """
        if inv_en:
            self.comb += if_ctrl_lbuf.deser_cs_n_d_disable_state.eq(0xFFFF)
            self.comb += if_ctrl_lbuf.deser_ca_d_disable_state.eq(0x0000)
        else:
            self.comb += if_ctrl_lbuf.deser_cs_n_d_disable_state.eq(0xFFFF)
            self.comb += if_ctrl_lbuf.deser_ca_d_disable_state.eq(0xFFFF)

        """
            Decoder
        """
        valid_int = Signal()
        is_this_ui_odd_int = Signal()
        is_cmd_beginning_int = Signal()
        if_ibuf_int = If_ibuf()

        self.submodules.decoder = DDR5RCD01Decoder(
            if_ibuf=if_ibuf_i,
            if_ibuf_o=if_ibuf_int,
            qvalid=valid_int,
            is_cmd_beginning=is_cmd_beginning_int,
            is_this_ui_odd=is_this_ui_odd_int,
            CS_BIT_SELECT=0
        )

        parity_error = Signal()
        valid = Signal()
        is_this_ui_odd = Signal()
        is_cmd_beginning = Signal()

        self.submodules.error = DDR5RCD01Error(
            if_ibuf_i=if_ibuf_int,
            if_ibuf_o=if_ibuf_o,
            decoder_valid=valid_int,
            decoder_is_this_ui_odd=is_this_ui_odd_int,
            decoder_is_cmd_beginning=is_cmd_beginning_int,
            q_valid=valid,
            q_is_this_ui_odd=is_this_ui_odd,
            q_is_cmd_beginning=is_cmd_beginning,
            error=parity_error
        )

        """
          If a valid command is decoded, deserialize it.
        """
        self.comb += if_ctrl_lbuf.deser_sel_lower_upper.eq(is_this_ui_odd),
        self.comb += if_ctrl_lbuf.deser_ca_d_en.eq(valid),
        self.comb += if_ctrl_lbuf.deser_ca_q_en.eq(is_this_ui_odd),
        self.comb += if_ctrl_lbuf.deser_cs_n_d_en.eq(valid),
        self.comb += if_ctrl_lbuf.deser_cs_n_q_en.eq(is_this_ui_odd),

if __name__ == "__main__":
    raise NotImplementedError
