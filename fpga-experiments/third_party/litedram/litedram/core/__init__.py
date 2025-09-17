#
# This file is part of LiteDRAM.
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.soc.interconnect.csr import AutoCSR

from litedram.dfii import DFIInjector
from litedram.core.controller import ControllerSettings, LiteDRAMController
from litedram.core.crossbar import LiteDRAMCrossbar
from litedram.phy import dfi

# Core ---------------------------------------------------------------------------------------------

class LiteDRAMCore(Module, AutoCSR):
    def __init__(self, phy, module, clk_freq, **kwargs):
        self.submodules.dfii = DFIInjector(
            addressbits = max(module.geom_settings.addressbits, getattr(phy, "addressbits", 0)),
            bankbits    = max(module.geom_settings.bankbits, getattr(phy, "bankbits", 0)),
            nranks      = phy.settings.nranks,
            databits    = phy.settings.dfi_databits,
            nphases     = phy.settings.nphases,
            write_latency  = phy.settings.write_latency,
            memtype        = phy.settings.memtype,
            strobes        = phy.settings.strobes,
            with_sub_channels = phy.settings.with_sub_channels,
            masked_writes_arg = phy.settings.masked_write)
        self.comb += self.dfii.master.connect(phy.dfi)

        self.submodules.controller = controller = LiteDRAMController(
            phy_settings        = phy.settings,
            geom_settings       = module.geom_settings,
            timing_settings     = module.timing_settings,
            max_expected_values = module.maximal_timing_values,
            clk_freq            = clk_freq,
            **kwargs)
        if phy.settings.memtype != "DDR5":
            self.comb += controller.dfi.connect(self.dfii.slave)
        else:
            #DDR5 special case
            intermediate_bus = dfi.Interface(
                max(module.geom_settings.addressbits, getattr(phy, "addressbits", 0)),
                max(module.geom_settings.bankbits, getattr(phy, "bankbits", 0)),
                phy.settings.nranks,
                phy.settings.dfi_databits,
                phy.settings.nphases)
            self.comb += controller.dfi.connect(intermediate_bus, omit=["cs_n"])
            self.comb += [
                inter_phase.cs_n[0].eq(controlr_phase.cs_n)
                    for (inter_phase, controlr_phase) in
                        zip(intermediate_bus.phases, controller.dfi.phases)
                ]
            for i in range(1, phy.settings.nranks):
                self.comb += [
                    inter_phase.cs_n[i].eq(1)
                        for inter_phase in intermediate_bus.phases]
            self.comb += intermediate_bus.connect(self.dfii.slave)

        self.submodules.crossbar = LiteDRAMCrossbar(controller.interface)
