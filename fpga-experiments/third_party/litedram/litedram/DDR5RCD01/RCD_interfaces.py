#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *


class If_ck(Record):
    """
    Clock interface
    """

    def __init__(self, n_clks=1):

        layout = self.description(n_clks)
        Record.__init__(self, layout)

    def description(self, n_clks):
        return [
            ('ck_t', n_clks),
            ('ck_c', n_clks),
        ]


class If_bus_csca(Record):
    """
    This interface encapsulates the output CS/CA bus.
    """

    def __init__(self, qcs_n_w=2, qca_w=7):
        layout = self.description(qcs_n_w, qca_w)
        Record.__init__(self, layout)

    def description(self, qcs_n_w, qca_w):
        return [
            # Single row: Command, Chip Select
            ('cs_n', qcs_n_w, False),
            ('ca', qca_w, False),
        ]


class If_bus_csca_o(Record):
    """
    This interface encapsulates the output CS/CA bus. (CA is double the size of input)
    """

    def __init__(self, qcs_n_w=2, qca_w=14):
        layout = self.description(qcs_n_w, qca_w)
        Record.__init__(self, layout)

    def description(self, qcs_n_w, qca_w):
        return [
            # Single row: Command, Chip Select
            ('qcs_n', qcs_n_w, False),
            ('qca', qca_w, False),
        ]


class If_channel_sdram(Record):
    """
    This interface is used for the:
    Signals coming from the SDRAM to channel
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            ('derror_in_n', 1, False),
            ('qrst_n', 1),
            ('dlbd',    1),
            ('dlbs',    1),
        ]


class If_ctrl_ibuf(Record):
    """
    This interface is used for the:
    Configuration of the input buffer
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            ('en', 1),
        ]


class If_ctrl_lbuf(Record):
    """
    This interface is used for the:
    Configuration of the line buffer
    """

    def __init__(self, qcs_n_w=2, qca_w=14):
        layout = self.description(qcs_n_w, qca_w)
        Record.__init__(self, layout)

    def description(self, qcs_n_w, qca_w):
        return [
            ('sel_latency_add', 3),
            ('deser_sel_lower_upper', 1),
            ('deser_ca_d_en', 1),
            ('deser_ca_q_en', 1),
            ('deser_cs_n_d_en', 1),
            ('deser_cs_n_q_en', 1),
            ('deser_ca_d_disable_state', qca_w),
            ('deser_cs_n_d_disable_state', qcs_n_w),
        ]


class If_ctrl_obuf_CSCA(Record):
    """
    This interface is used for the:
    Configuration of the output buffer
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):

        return [
            ('oe_qcs_n', 1),
            ('o_inv_en_qcs_n', 1),
            ('oe_qca', 1),
            ('o_inv_en_qca', 1),
            ('tie_high_cs', 1),
            ('tie_high_ca', 1),
            ('tie_low_cs', 1),
            ('tie_low_ca', 1),
        ]


class If_ctrl_obuf_CLKS(Record):
    """
    This interface is used for the:
    Configuration of the output buffer
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            ('oe_ck_t', 1),
            ('o_inv_en_ck_t', 1),
            ('oe_ck_c', 1),
            ('o_inv_en_ck_c', 1),
            ('tie_high_ck_t', 1),
            ('tie_high_ck_c', 1),
            ('tie_low_ck_t', 1),
            ('tie_low_ck_c', 1),
        ]


class If_config_global(Record):
    """
    This interface is used for the:
    Configuration of the B channel global settings
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            # TODO list all RWs that are global, based on the global list in definitions.
            ('Global_RWs', 1),
        ]


class If_config_common(Record):
    """
    This interface is used for the:
    Configuration of the common block settings
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            # TODO add RWs, e.g. PLL control, loopback mode, error mode
            ('Common_RWs', 1),
        ]


# class If_common(Record):
#     """
#     This interface is used for the:
#     Configuration of the common block settings
#     """

#     def __init__(self):
#         layout = self.description()
#         Record.__init__(self, layout)

#     def description(self):
#         return [
#             # TODO parity, lb, etc.
#             ('parity', 1),
#             ('loopback', 1),
#         ]


# class If_common_sdram(Record):
#     """
#     Channel/common signals
#     """

#     def __init__(self):
#         layout = self.description()
#         Record.__init__(self, layout)

#     def description(self):
#         return [
#             ('qrst_a_n', 1),
#             ('qrst_b_n', 1),
#         ]


# class If_channel_common(Record):
#     """
#     Channel/common signals
#     """

#     def __init__(self):
#         layout = self.description()
#         Record.__init__(self, layout)

#     def description(self):
#         return [
#             ('err_parity', 1),
#             ('err_n_sdram', 1),
#             ('dlbd',  1),
#             ('dlbs',  1),
#         ]


# class If_int_lb(Record):
#     """
#     DFE Tap internal loopback interface
#     """

#     def __init__(self):
#         layout = self.description()
#         Record.__init__(self, layout)

#     def description(self):
#         return [
#             ('dca_lb',    7),
#             ('dpar_lb',    1),
#         ]


class If_rst_n(Record):
    """
    Global reset
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def if_assert(self):
        yield self.rst_n.eq(0)

    def if_deassert(self):
        yield self.rst_n.eq(1)

    def description(self):
        return [
            ('rst_n',    1),
        ]


class If_ctrl_common(Record):
    """
    PLL configuration interface
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            ('pll_en', 1),
            ('pll_bypass', 1),
            ('err_en', 1),
            ('lb_en', 1),
            ('lb_sel_mode', 1),
            ('lb_sel_phase_ab', 1),
            ('lb_sel_int_bit', 3),
            ('lb_sel_channel_A_B', 1),
            ('alert_n_mode', 1),
        ]


class If_registers(Record):
    """
    I2CSlaveMock<->Registers interface
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('we', 1),
            ('addr', CW_REG_BIT_SIZE),
            ('d', CW_REG_BIT_SIZE),
            ('q', CW_REG_BIT_SIZE),
        ]


class If_ctrl_blocker(Record):
    """
    Block interface
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('block', 1),
        ]


class If_ctrl_dcstm_agent(Record):
    """
    DCSTM
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('enable', 1),
            ('select_dcs_n', 1),
        ]


class If_ctrl_dcatm_agent(Record):
    """
    DCATM
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('enable', 1),
            ('exit_dcatm', 1),
        ]


class If_ctrl_error_arbiter(Record):
    """
    DCATM
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('is_dcstm_en', 1),
            ('is_dcatm_en', 1),
            ('is_normal_en', 1),
            ('is_parity_checking_en', 1),
        ]


class If_ctrl_cmd_logic(Record):
    """
    DCATM
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('is_output_inversion_en', 1),
            ('is_parity_checking_en', 1),
        ]


if __name__ == "__main__":
    raise NotSupportedException()
