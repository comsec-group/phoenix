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


class DDR5RCD01Error(Module):
    """
    DDR5 RCD01 Error
    ----------------

    1. If parity checking is enabled:
        - the module calculates the parity
        - raises alerts to Alert in Common (single-pulse)
    2. Alawys(?) passes derror_n_in signal
    3. Controls reads and writes to Error Log Registers (24:20)
        - Set CA Parity Error Status (RW24)
        - Clear bit in RW01 to disable parity checking (re-enable mode is possible)
    4. Send message to control center that the output should be blocked?
        or command center takes this information from rw20

    Module
    ------
    <interface>

    Parameters
    ----------
    <params>

    """

    def __init__(self,
                 if_csca,
                 if_csca_rank_A,
                 if_csca_rank_B,
                 if_csca_o,
                 if_csca_o_rank_A,
                 if_csca_o_rank_B,
                 valid,
                 valid_A,
                 valid_B,
                 is_this_ui_odd,
                 is_cmd_beginning,
                 qvalid,
                 qvalid_A,
                 qvalid_B,
                 qis_this_ui_odd,
                 qis_cmd_beginning,
                 rw_is_parity_checking_enabled,
                 parity_error,
                 ):
        """
            Check parity
        """
        parity_checking_reenable = Signal()
        del_is_cmd_beginning = Signal()
        is_2nd_ui_active = Signal()

        self.sync += del_is_cmd_beginning.eq(is_cmd_beginning)
        self.comb += is_2nd_ui_active.eq(del_is_cmd_beginning)

        is_parity_error_detected = Signal()
        dca_w = len(if_csca.dca)

        self.comb += If(
            valid,
            is_parity_error_detected.eq(
                reduce(xor, [if_csca.dca[bit] for bit in range(dca_w)]) ^ if_csca.dpar)
        ).Else(
            is_parity_error_detected.eq(0)
        )

        d_is_parity_error_detected = Signal()
        self.sync += If(
            is_parity_error_detected,
            d_is_parity_error_detected.eq(1)
        ).Else(
            If(
                parity_checking_reenable,
                d_is_parity_error_detected.eq(0)
            )
        )

        """
            Table 9 - Blocking commands on Parity Error
        """
        is_blocking_future_cmds = Signal()
        is_parity_checking_enabled = Signal()

        del_rw_is_parity_checking_enabled = Signal()
        self.sync += del_rw_is_parity_checking_enabled.eq(
            rw_is_parity_checking_enabled)
        edge_parity_enable = Signal()
        self.comb += edge_parity_enable.eq(
            del_rw_is_parity_checking_enabled ^ rw_is_parity_checking_enabled)

        self.comb += parity_checking_reenable.eq(
            edge_parity_enable & rw_is_parity_checking_enabled)

        self.sync += If(
            parity_checking_reenable,
            is_parity_checking_enabled.eq(1),
            is_blocking_future_cmds.eq(0),
        ).Else(
            If(
                is_parity_error_detected,
                is_parity_checking_enabled.eq(0),
                is_blocking_future_cmds.eq(1),
            )
        )

        disable_future_cmds = Signal()
        self.sync += If(
            parity_checking_reenable,
            disable_future_cmds.eq(0),
        ).Else(
            If(
                rw_is_parity_checking_enabled,
                If(
                    is_blocking_future_cmds & (~valid),
                    disable_future_cmds.eq(1)
                )
            ).Else(
                disable_future_cmds.eq(0)
            )
        )

        self.comb += If(
            disable_future_cmds,
            if_csca_o.dcs_n.eq(~0),
            if_csca_o.dca.eq(0),
            if_csca_o_rank_A.dcs_n.eq(~0),
            if_csca_o_rank_A.dca.eq(0),
            if_csca_o_rank_B.dcs_n.eq(~0),
            if_csca_o_rank_B.dca.eq(0),
        ).Else(
            If(
                is_parity_checking_enabled,
                If(
                    is_parity_error_detected | d_is_parity_error_detected,
                    if_csca_o.dcs_n.eq(~0),
                    if_csca_o.dca.eq(if_csca.dca),
                    if_csca_o_rank_A.dcs_n.eq(~0),
                    if_csca_o_rank_A.dca.eq(if_csca.dca),
                    if_csca_o_rank_B.dcs_n.eq(~0),
                    if_csca_o_rank_B.dca.eq(if_csca.dca),
                ).Else(
                    if_csca_o.dcs_n.eq(0),
                    if_csca_o.dca.eq(if_csca.dca),
                    if_csca_o_rank_A.dcs_n.eq(0),
                    if_csca_o_rank_A.dca.eq(if_csca.dca),
                    if_csca_o_rank_B.dcs_n.eq(0),
                    if_csca_o_rank_B.dca.eq(if_csca.dca),
                )
            ).Else(
                if_csca_o.dcs_n.eq(if_csca.dcs_n),
                if_csca_o.dca.eq(if_csca.dca),
                if_csca_o_rank_A.dcs_n.eq(if_csca.dcs_n),
                if_csca_o_rank_A.dca.eq(if_csca.dca),
                if_csca_o_rank_B.dcs_n.eq(if_csca.dcs_n),
                if_csca_o_rank_B.dca.eq(if_csca.dca),
            )
        )

        self.comb += If(
            disable_future_cmds,
            qvalid.eq(0),
            qvalid_A.eq(0),
            qvalid_B.eq(0),
            qis_this_ui_odd.eq(0),
            qis_cmd_beginning.eq(0),
        ).Else(
            qvalid.eq(valid),
            qvalid_A.eq(valid_A),
            qvalid_B.eq(valid_B),
            qis_this_ui_odd.eq(is_this_ui_odd),
            qis_cmd_beginning.eq(is_cmd_beginning),
        )

        self.comb += parity_error.eq(is_parity_error_detected)


if __name__ == "__main__":
    NotSupportedException
