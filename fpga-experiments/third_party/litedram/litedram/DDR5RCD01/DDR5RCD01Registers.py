#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
from reprlib import *
import logging
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
#
from litedram.DDR5RCD01.DDR5RCD01Pages import DDR5RCD01Pages
from litedram.DDR5RCD01.DDR5RCD01RegFile import DDR5RCD01RegFile


class DDR5RCD01Registers(Module):
    """
        DDR5 RCD Registers
        ------------------

        If write is to address 0x0 to 0x5F, the write is to register file.

        If write is to address 0x60 to 0xFF, the write is to pages.

        Reads are always through reg_q (must set pointers before reading).

    """

    def __init__(self, d, addr, we, q, cw_page_num):
        reg_we = Signal()
        bank_we = Signal()
        page_addr = Signal(CW_REG_BIT_SIZE)
        self.comb += If(
            addr <= ADDR_CW_PAGE,
            reg_we.eq(we),
            bank_we.eq(0),
            page_addr.eq(0),
        ).Else(
            reg_we.eq(0),
            bank_we.eq(we),
            page_addr.eq(addr-ADDR_CW_PAGE-1),
        )

        bank_d = Signal(CW_REG_BIT_SIZE)
        self.comb += bank_d.eq(d)
        reg_d = Signal(CW_REG_BIT_SIZE)
        self.comb += reg_d.eq(d)

        # These signals are already set
        bank_page_pointer = Signal(CW_REG_BIT_SIZE)
        page_copy = Array(Signal(CW_REG_BIT_SIZE)
                          for y in range(CW_PAGE_PTRS_NUM))
        bank_page_pointer = Signal(CW_REG_BIT_SIZE)
        # Not all pages are currently used, so their number may be reduced to speed-up the simulation
        xpage_file = DDR5RCD01Pages(
            d=bank_d,
            we=bank_we,
            page_pointer=bank_page_pointer,
            q_page=page_copy,
            page_addr=page_addr,
            cw_page_num=cw_page_num,
        )
        self.submodules.xpage_file = xpage_file
        reg_q = Signal(CW_REG_BIT_SIZE)
        # If writing to the register, set reg_d to valid data, set reg_we to '1'
        xreg_file = DDR5RCD01RegFile(
            d=reg_d,
            addr=addr,
            we=reg_we,
            q=reg_q,
            page=page_copy,
            page_pointer=bank_page_pointer
        )
        self.submodules.xreg_file = xreg_file
        self.comb += q.eq(reg_q)


if __name__ == "__main__":
    NotSupportedException
