#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import unittest
import logging
# migen
from migen import *
from migen.fhdl import verilog
# RCD
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *


class CRG(Module):
    """
        clocks = {
            "clk_name" : (clk_period in ticks, clk_shift in ticks)
        }
    """
    def __init__(self, clocks, reset_cnt):        
        self.clocks = clocks
        r = Signal(max=reset_cnt+1)
        self.sync.sys_rst += [
            If(r < reset_cnt,
                r.eq(r+1),
               )
        ]
        for clk in self.clocks:
            if clk == "sys_rst":
                continue
            setattr(self.clock_domains, "cd_{}".format(clk), ClockDomain(clk))
            cd = getattr(self, 'cd_{}'.format(clk))
            self.comb += cd.rst.eq(~(r == reset_cnt))

    def add_domain(self, clock_domain, clk_tuple, clk_rst=None):
        cd = getattr(self, f"cd_{clock_domain}", None)
        assert cd is None, f"{clock_domain} already exists"
        setattr(
            self.clock_domains,
            "cd_{}".format(clock_domain),
            ClockDomain(clock_domain)
        )
        cd = getattr(self, 'cd_{}'.format(clock_domain))
        self.clocks[clock_domain] = clk_tuple
        if clk_rst is not None:
            self.comb += cd.rst.eq(clk_rst)
