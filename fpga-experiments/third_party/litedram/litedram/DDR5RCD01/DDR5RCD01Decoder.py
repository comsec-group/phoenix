#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *


class DDR5RCD01Decoder(Module):
    """
        DDR5 RCD01 Decoder
        ------------------

        DDR5 RCD01 Decoder implements XOR logic to detect positive and negative edges on dcs_n signals.

        1. If a negative edge is detected, then either:
             a single command is present on the CSCA bus
             a sequence of commands started

        Single command behavior
        -----------------------
        If bit CA[1] is high, then the command is 1UI, else a 2UI command.

            Single UI
            ---------
            qvalid will be set for the next 2 clock cycles.
            is_this_ui_odd will toggle once (0,1)
            is_cmd_beginning will produce a single pulse

            Double UI
            ---------
            qvalid will be set for the next 4 clock cycles.
            is_this_ui_odd will toggle twice (0,1,0,1)
            is_cmd_beginning will produce a single pulse

        Sequence of commands behavior
        -----------------------------
            qvalid will be set for z clock cycles:
                z=2k+4j,
                where k is the number of 1UI commands,
                where j is the number of 2UI commands,
            is_this_ui_odd will toggle as long as qvalid is asserted
            is_cmd_beginning will produce a single pulses. Their
            total number will be equal to the number of input commands (k+j)

        Module
        ------
        if_ibuf - The input CSCA bus interface. {CS_n[1:0], CA[6:0], DPAR} signals.
        qvalid - If this signal is asserted, then a valid UI is present on the qcs_n, qca ports.
        qca, qcs_n - CSCA bus
        is_this_ui_odd - This signal is asserted, every time an odd UI is present on the outputs.
        is_cmd_beginning - This signal is asserted every time a begining of a command is detected.

        Parameters
        ------
        N/A

    """

    def __init__(self,
                 if_ibuf,
                 if_csca_o,
                 if_csca_o_rank_A,
                 if_csca_o_rank_B,
                 qvalid,
                 qvalid_A,
                 qvalid_B,
                 is_this_ui_odd,
                 is_cmd_beginning,
                 is_cw_bit_set,
                 ):
        """
            Definitions
            CA[1] bit holds information whether the command is 1UI or 2UI
            Rank A is selected by asserting CS[1]
            Rank B is selected by asserting CS[0]
        """
        CA_IS_1UI_BIT = 1
        RANK_A_BIT_SEL = 1
        RANK_B_BIT_SEL = 0

        """
            XOR edge detection
        """
        cs_n_w = len(if_ibuf.dcs_n)
        ca_w = len(if_ibuf.dca)
        del_dcs_n = Signal(cs_n_w, reset=~0)
        self.sync += del_dcs_n.eq(if_ibuf.dcs_n)

        del_dca = Signal(ca_w)
        self.sync += del_dca.eq(if_ibuf.dca)

        del_dpar = Signal()
        self.sync += del_dpar.eq(if_ibuf.dpar)

        det_edge = Signal(2)
        self.comb += det_edge.eq(if_ibuf.dcs_n ^ del_dcs_n)

        det_posedge = Signal(2)
        self.comb += det_posedge.eq(det_edge & if_ibuf.dcs_n)

        det_negedge = Signal(2)
        self.comb += det_negedge.eq(det_edge & ~if_ibuf.dcs_n)

        """
            Detect if command is 1UI or 2UI
        """
        is_cmd_active = Signal()

        is_1_ui_command = Signal()
        self.comb += is_1_ui_command.eq(if_ibuf.dca[CA_IS_1UI_BIT])

        force_active_high = Signal(2)

        del_is_1_ui_command = Signal()
        self.sync += del_is_1_ui_command.eq(is_1_ui_command)

        # 2UI commands requires keeping "active" after DCS is deasserted
        self.sync += If(
            is_cmd_active & (is_this_ui_odd == 0) & (del_is_1_ui_command == 0),
            force_active_high.eq(3),
        ).Else(
            If(
                force_active_high,
                force_active_high.eq(force_active_high-1),
            ).Else(
                force_active_high.eq(0),
            )
        )

        is_force_non_zero = Signal()
        self.comb += is_force_non_zero.eq(force_active_high > 0)

        self.sync += If(
            det_negedge != 0,
            is_cmd_active.eq(1),
        ).Else(
            If(
                det_posedge,
                is_cmd_active.eq(0),
            )
        )
        """
            Pseudo-clock is a signal which toggles at the start of each detected UI.
            The clock always starts at LOW at the DCS assertion edge.
        """
        pseudo_clock = Signal()
        pseudo_clock_en = Signal()
        self.sync += If(
            det_negedge | is_cmd_active,
            pseudo_clock_en.eq(1),
        ).Else(
            pseudo_clock_en.eq(0),
        )

        self.sync += If(
            det_negedge,
            pseudo_clock.eq(0)
        ).Else(
            If(
                pseudo_clock_en,
                pseudo_clock.eq(~pseudo_clock)
            ).Else(
                pseudo_clock.eq(0)
            )
        )

        self.comb += is_this_ui_odd.eq(pseudo_clock)
        self.comb += qvalid.eq(is_cmd_active | is_force_non_zero)
        self.comb += is_cmd_beginning.eq(qvalid &
                                         (~is_this_ui_odd) & (is_force_non_zero == 0))

        """
            Addressing feature
            CS
            11 - deselect
            01 - send to rank A
            10 - send to rank B
            00 - send to both ranks
        """
        capture_previous_cs = Signal(2, reset=~0)
        self.sync += If(
            is_cmd_beginning,
            capture_previous_cs.eq(del_dcs_n),
        )

        is_cmd_destined_for_rank_A = Signal()
        is_cmd_destined_for_rank_B = Signal()
        is_cmd_destined_for_both_ranks = Signal()

        self.comb += If(
            ~qvalid,
            is_cmd_destined_for_rank_A.eq(0),
        ).Else(
            If(
                is_cmd_beginning,
                is_cmd_destined_for_rank_A.eq(~del_dcs_n[RANK_A_BIT_SEL]),
            ).Else(
                is_cmd_destined_for_rank_A.eq(
                    ~capture_previous_cs[RANK_A_BIT_SEL])
            )
        )

        self.comb += If(
            ~qvalid,
            is_cmd_destined_for_rank_B.eq(0),
        ).Else(
            If(
                is_cmd_beginning,
                is_cmd_destined_for_rank_B.eq(~del_dcs_n[RANK_B_BIT_SEL]),
            ).Else(
                is_cmd_destined_for_rank_B.eq(
                    ~capture_previous_cs[RANK_B_BIT_SEL])
            )
        )

        self.comb += is_cmd_destined_for_both_ranks.eq(
            is_cmd_destined_for_rank_A & is_cmd_destined_for_rank_B)
        self.comb += qvalid_A.eq(qvalid & is_cmd_destined_for_rank_A)
        self.comb += qvalid_B.eq(qvalid & is_cmd_destined_for_rank_B)

        self.comb += If(
            is_cmd_destined_for_rank_A,
            if_csca_o_rank_A.dcs_n.eq(del_dcs_n),
            if_csca_o_rank_A.dca.eq(del_dca),
            if_csca_o_rank_A.dpar.eq(del_dpar),
        ).Else(
            if_csca_o_rank_A.dcs_n.eq(~0),
            if_csca_o_rank_A.dca.eq(~0),
            if_csca_o_rank_A.dpar.eq(~0),
        )

        self.comb += If(
            is_cmd_destined_for_rank_B,
            if_csca_o_rank_B.dcs_n.eq(del_dcs_n),
            if_csca_o_rank_B.dca.eq(del_dca),
            if_csca_o_rank_B.dpar.eq(del_dpar),
        ).Else(
            if_csca_o_rank_B.dcs_n.eq(~0),
            if_csca_o_rank_B.dca.eq(~0),
            if_csca_o_rank_B.dpar.eq(~0),
        )

        self.comb += If(
            qvalid,
            if_csca_o.dcs_n.eq(del_dcs_n),
            if_csca_o.dca.eq(del_dca),
            if_csca_o.dpar.eq(del_dpar),
        ).Else(
            if_csca_o.dcs_n.eq(~0),
            if_csca_o.dca.eq(~0),
            if_csca_o.dpar.eq(~0),
        )

        """
            Detect if command is meant for RCD
        """
        is_cw_bit_set = Signal()
        self.comb += If(
            force_active_high == 0b10,
            is_cw_bit_set.eq(if_ibuf.dca[3])
        )


if __name__ == "__main__":
    NotSupportedException
