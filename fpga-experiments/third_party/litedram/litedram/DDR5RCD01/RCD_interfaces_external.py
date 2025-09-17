#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *

"""
Clocks, reset, error
"""


class If_ck_rst(Record):
    """
    Clock and reset interface from HOST to RCD device
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def if_rst_assert(self):
        yield self.drst_n.eq(0)

    def if_rst_deassert(self):
        yield self.drst_n.eq(1)

    def description(self):
        return [
            ('dck_t', 1),
            ('dck_c', 1),
            ('drst_n', 1),
        ]


class If_sdram(Record):
    """
    This interface is used for the:
    Signals coming from the sdram to channel
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            # SDRAM Channel A
            ('derror_a_in_n', 1, False),
            ('qrst_a_n', 1),
            ('dlbd_a',    1),
            ('dlbs_a',    1),
            # SDRAM Channel B
            ('derror_b_in_n', 1, False),
            ('qrst_b_n', 1),
            ('dlbd_b',    1),
            ('dlbs_b',    1),
        ]


class If_alert_n(Record):
    """
    Host/RCD error interface
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            ('alert_n', 1),
        ]


"""
CA/CS Bus
"""


class If_ibuf(Record):
    """ Input Buffer Interface
    """

    def __init__(self, dcs_n_w=2, dca_w=7):
        layout = self.description(dcs_n_w, dca_w)
        Record.__init__(self, layout)

    def description(self, dcs_n_w, dca_w):
        return [
            ('dcs_n', dcs_n_w),
            ('dca', dca_w),
            ('dpar', 1),
        ]


class If_obuf(Record):
    """ TODO """

    def __init__(self, qcs_n_w=2, qca_w=14):
        layout = self.description(qcs_n_w=2, qca_w=14)
        Record.__init__(self, layout)

    def description(self, qcs_n_w=2, qca_w=14):
        return [
            # CS/CA Bus
            # Rank A
            # Row A
            ('qacs_a_n', qcs_n_w, False),
            ('qaca_a', qca_w, False),
            # Row B
            ('qacs_b_n', qcs_n_w, False),
            ('qaca_b', qca_w, False),

            # Rank B
            # Row A
            ('qbcs_a_n', qcs_n_w, False),
            ('qbca_a', qca_w, False),
            # Row B
            ('qbcs_b_n', qcs_n_w, False),
            ('qbca_b', qca_w, False),

            # Clock outputs
            # TODO comments are out of date!
            # Rank 0, Row A
            ('qack_t', 1, False),
            ('qack_c', 1, False),
            # Rank 1, Row B
            ('qbck_t', 1, False),
            ('qbck_c', 1, False),
            # Rank 0, Row A
            ('qcck_t', 1, False),
            ('qcck_c', 1, False),
            # Rank 1, Row B
            ('qdck_t', 1, False),
            ('qdck_c', 1, False),
        ]


"""
Loopback
"""


class If_lb(Record):
    """
    Host/RCD loopback interface
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self):
        return [
            ('qlbd',    1),
            ('qlbs',    1),
        ]


"""
BCOM interface
"""


class If_bcom(Record):
    """
    Clock interface
    """

    def __init__(self):
        layout = self.description(bcom_a_w=3)
        Record.__init__(self, layout)

    def description(self, bcom_a_w=3):
        return [
            ('brst_a_n', 1),
            ('bcs_a_n', 1),
            ('bcom_a_n', bcom_a_w),

            ('bcs_b_n', 1),
            ('bcom_b_n', bcom_a_w),
            ('brst_b_n', 1),

            ('bck_a_t', 1),
            ('bck_a_c', 1),

            ('bck_b_t', 1),
            ('bck_b_c', 1),
        ]


"""
Sideband
"""


class If_sideband(Record):
    """
    Sideband
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('sda', 1),
            ('scl', 1),
        ]


class If_sideband_mock(Record):
    """
    Sideband mock
    """

    def __init__(self):
        layout = self.description()
        Record.__init__(self, layout)

    def description(self,):
        return [
            ('we', 1),
            ('channel', 4),
            ('page_num', CW_REG_BIT_SIZE),
            ('reg_num', CW_REG_BIT_SIZE),
            ('data', CW_REG_BIT_SIZE),
        ]


if __name__ == "__main__":
    raise NotSupportedException()
