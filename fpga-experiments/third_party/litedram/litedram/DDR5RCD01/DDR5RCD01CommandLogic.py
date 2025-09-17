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
from litedram.DDR5RCD01.DDR5RCD01ActorMRW import DDR5RCD01ActorMRW


class DDR5RCD01CommandLogic(Module):
    """
        DDR5RCD01CommandLogic
        ---------------------

        DDR5RCD01CommandLogic is module, which...

        Decoder

        Error checking

        Prepare inputs to deserializer

        Act on MRW
    """

    def __init__(self,
                 if_ibuf_i,
                 if_csca_o,
                 if_csca_o_rank_A,
                 if_csca_o_rank_B,
                 if_ctrl_lbuf_rank_A_row_A,
                 if_ctrl_lbuf_rank_A_row_B,
                 if_ctrl_lbuf_rank_B_row_A,
                 if_ctrl_lbuf_rank_B_row_B,
                 if_register,
                 rw_is_output_inversion_enabled,
                 rw_is_parity_checking_enabled,
                 parity_error,
                 ):
        """
            Decoder
        """
        valid_int = Signal()
        valid_A_int = Signal()
        valid_B_int = Signal()
        is_this_ui_odd_int = Signal()
        is_cmd_beginning_int = Signal()
        is_cw_bit_set = Signal()

        if_csca_o_int = If_ibuf()
        if_csca_o_rank_A_int = If_ibuf()
        if_csca_o_rank_B_int = If_ibuf()

        xdecoder = DDR5RCD01Decoder(
            if_ibuf=if_ibuf_i,
            if_csca_o=if_csca_o_int,
            if_csca_o_rank_A=if_csca_o_rank_A_int,
            if_csca_o_rank_B=if_csca_o_rank_B_int,
            qvalid=valid_int,
            qvalid_A=valid_A_int,
            qvalid_B=valid_B_int,
            is_this_ui_odd=is_this_ui_odd_int,
            is_cmd_beginning=is_cmd_beginning_int,
            is_cw_bit_set=is_cw_bit_set,
        )
        self.submodules.xdecoder = xdecoder

        if_csca_o_actor = If_ibuf()
        if_csca_o_actor_rank_A = If_ibuf()
        if_csca_o_actor_rank_B = If_ibuf()

        xactor = DDR5RCD01ActorMRW(
            if_csca_i=if_csca_o_int,
            if_csca_i_rank_A=if_csca_o_rank_A_int,
            if_csca_i_rank_B=if_csca_o_rank_B_int,
            if_csca_o=if_csca_o_actor,
            if_csca_o_rank_A=if_csca_o_actor_rank_A,
            if_csca_o_rank_B=if_csca_o_actor_rank_B,
            valid=valid_int,
            is_this_ui_odd=is_this_ui_odd_int,
            is_cmd_beginning=is_cmd_beginning_int,
            is_cw_bit_set=is_cw_bit_set,
            reg_d=if_register.q,
            reg_addr=if_register.addr,
            reg_we=if_register.we,
            reg_q=if_register.d,
        )
        self.submodules.xactor = xactor

        """
            Parity Error checking
        """
        qvalid = Signal()
        qvalid_A = Signal()
        qvalid_B = Signal()
        qis_this_ui_odd = Signal()
        qis_cmd_beginning = Signal()

        xerror = DDR5RCD01Error(
            if_csca=if_csca_o_actor,
            if_csca_rank_A=if_csca_o_actor_rank_A,
            if_csca_rank_B=if_csca_o_actor_rank_B,
            if_csca_o=if_csca_o,
            if_csca_o_rank_A=if_csca_o_rank_A,
            if_csca_o_rank_B=if_csca_o_rank_B,
            valid=valid_int,
            valid_A=valid_A_int,
            valid_B=valid_B_int,
            is_this_ui_odd=is_this_ui_odd_int,
            is_cmd_beginning=is_cmd_beginning_int,
            qvalid=qvalid,
            qvalid_A=qvalid_A,
            qvalid_B=qvalid_B,
            qis_this_ui_odd=qis_this_ui_odd,
            qis_cmd_beginning=qis_cmd_beginning,
            rw_is_parity_checking_enabled=rw_is_parity_checking_enabled,
            parity_error=parity_error,
        )
        self.submodules.xerror = xerror

        """
            Output inversion enable
        """
        self.comb += If(
            rw_is_output_inversion_enabled,
            if_ctrl_lbuf_rank_B_row_A.deser_cs_n_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_B_row_A.deser_ca_d_disable_state.eq(0x0000),
            if_ctrl_lbuf_rank_B_row_B.deser_cs_n_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_B_row_B.deser_ca_d_disable_state.eq(0x0000),
        ).Else(
            if_ctrl_lbuf_rank_B_row_A.deser_cs_n_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_B_row_A.deser_ca_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_B_row_B.deser_cs_n_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_B_row_B.deser_ca_d_disable_state.eq(0xFFFF),
        )

        self.comb += [
            if_ctrl_lbuf_rank_A_row_A.deser_cs_n_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_A_row_A.deser_ca_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_A_row_B.deser_cs_n_d_disable_state.eq(0xFFFF),
            if_ctrl_lbuf_rank_A_row_B.deser_ca_d_disable_state.eq(0xFFFF),
        ]

        """
          If a valid command is decoded, deserialize it.
        """
        qvalid_A_del = Array(Signal() for _ in range(4))
        for i in range(len(qvalid_A_del)):
            if i == 0:
                self.sync += qvalid_A_del[i].eq(qvalid_A)
            else:
                self.sync += qvalid_A_del[i].eq(qvalid_A_del[i-1])

        self.comb += If(
            qvalid_A,
            if_ctrl_lbuf_rank_A_row_A.deser_sel_lower_upper.eq(
                qis_this_ui_odd),
            if_ctrl_lbuf_rank_A_row_A.deser_ca_d_en.eq(qvalid_A),
            if_ctrl_lbuf_rank_A_row_A.deser_cs_n_d_en.eq(qvalid_A),

            if_ctrl_lbuf_rank_A_row_B.deser_sel_lower_upper.eq(
                qis_this_ui_odd),
            if_ctrl_lbuf_rank_A_row_B.deser_ca_d_en.eq(qvalid_A),
            if_ctrl_lbuf_rank_A_row_B.deser_cs_n_d_en.eq(qvalid_A),
        ).Else(
            if_ctrl_lbuf_rank_A_row_A.deser_sel_lower_upper.eq(0),
            if_ctrl_lbuf_rank_A_row_A.deser_ca_d_en.eq(0),
            if_ctrl_lbuf_rank_A_row_A.deser_cs_n_d_en.eq(0),

            if_ctrl_lbuf_rank_A_row_B.deser_sel_lower_upper.eq(0),
            if_ctrl_lbuf_rank_A_row_B.deser_ca_d_en.eq(0),
            if_ctrl_lbuf_rank_A_row_B.deser_cs_n_d_en.eq(0),
        )

        """
            The valid signal delayed by 3 clocks drives the deserializer output enable
        """
        self.comb += If(
            qvalid_A_del[2],
            if_ctrl_lbuf_rank_A_row_A.deser_ca_q_en.eq(1),
            if_ctrl_lbuf_rank_A_row_A.deser_cs_n_q_en.eq(1),
            if_ctrl_lbuf_rank_A_row_B.deser_ca_q_en.eq(1),
            if_ctrl_lbuf_rank_A_row_B.deser_cs_n_q_en.eq(1),
        ).Else(
            if_ctrl_lbuf_rank_A_row_A.deser_ca_q_en.eq(0),
            if_ctrl_lbuf_rank_A_row_A.deser_cs_n_q_en.eq(0),
            if_ctrl_lbuf_rank_A_row_B.deser_ca_q_en.eq(0),
            if_ctrl_lbuf_rank_A_row_B.deser_cs_n_q_en.eq(0),
        )

        """
            RANK B
            If a valid command is decoded, deserialize it.
        """
        qvalid_B_del = Array(Signal() for _ in range(4))
        for i in range(len(qvalid_B_del)):
            if i == 0:
                self.sync += qvalid_B_del[i].eq(qvalid_B)
            else:
                self.sync += qvalid_B_del[i].eq(qvalid_B_del[i-1])

        self.comb += If(
            qvalid_B,
            if_ctrl_lbuf_rank_B_row_A.deser_sel_lower_upper.eq(
                qis_this_ui_odd),
            if_ctrl_lbuf_rank_B_row_A.deser_ca_d_en.eq(qvalid_B),
            if_ctrl_lbuf_rank_B_row_A.deser_cs_n_d_en.eq(qvalid_B),

            if_ctrl_lbuf_rank_B_row_B.deser_sel_lower_upper.eq(
                qis_this_ui_odd),
            if_ctrl_lbuf_rank_B_row_B.deser_ca_d_en.eq(qvalid_B),
            if_ctrl_lbuf_rank_B_row_B.deser_cs_n_d_en.eq(qvalid_B),
        ).Else(
            if_ctrl_lbuf_rank_B_row_A.deser_sel_lower_upper.eq(0),
            if_ctrl_lbuf_rank_B_row_A.deser_ca_d_en.eq(0),
            if_ctrl_lbuf_rank_B_row_A.deser_cs_n_d_en.eq(0),

            if_ctrl_lbuf_rank_B_row_B.deser_sel_lower_upper.eq(0),
            if_ctrl_lbuf_rank_B_row_B.deser_ca_d_en.eq(0),
            if_ctrl_lbuf_rank_B_row_B.deser_cs_n_d_en.eq(0),
        )

        """
            The valid signal delayed by 3 clocks drives the deserializer output enable
        """
        self.comb += If(
            qvalid_B_del[2],
            if_ctrl_lbuf_rank_B_row_A.deser_ca_q_en.eq(1),
            if_ctrl_lbuf_rank_B_row_A.deser_cs_n_q_en.eq(1),
            if_ctrl_lbuf_rank_B_row_B.deser_ca_q_en.eq(1),
            if_ctrl_lbuf_rank_B_row_B.deser_cs_n_q_en.eq(1),
        ).Else(
            if_ctrl_lbuf_rank_B_row_A.deser_ca_q_en.eq(0),
            if_ctrl_lbuf_rank_B_row_A.deser_cs_n_q_en.eq(0),
            if_ctrl_lbuf_rank_B_row_B.deser_ca_q_en.eq(0),
            if_ctrl_lbuf_rank_B_row_B.deser_cs_n_q_en.eq(0),
        )


if __name__ == "__main__":
    raise NotImplementedError
