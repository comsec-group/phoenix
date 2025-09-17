#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

# DRP ----------------------------------------------------------------------------------------------

_drp_layout = [
    ("clk",                1, DIR_M_TO_S),
    ("en",                 1, DIR_M_TO_S),
    ("we",                 1, DIR_M_TO_S),
    ("rdy",                1, DIR_S_TO_M),
    ("addr", "address_width", DIR_M_TO_S),
    ("di",      "data_width", DIR_M_TO_S),
    ("do",      "data_width", DIR_S_TO_M),
]


class DRPInterface(Record):
    def __init__(self, address_width=9, data_width=16):
        Record.__init__(self, set_layout_parameters(_drp_layout,
            address_width=address_width, data_width=data_width))


class DRPMux(Module, DRPInterface):
    def __init__(self, **kwargs):
        DRPInterface.__init__(self, **kwargs)
        self.sel = Signal(4)
        self.interfaces = []

    def add_interface(self, interface):
        self.interfaces.append(interface)

    def do_finalize(self):
        assert len(self.interfaces) <= 16
        cases = {}
        for i, interface in enumerate(self.interfaces):
            cases[i] = interface.connect(self)
        self.comb += Case(self.sel, cases)
