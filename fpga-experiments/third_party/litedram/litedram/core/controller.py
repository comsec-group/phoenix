#
# This file is part of LiteDRAM.
#
# Copyright (c) 2015 Sebastien Bourdeauducq <sb@m-labs.hk>
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""LiteDRAM Controller."""

from migen import *

from litex.soc.interconnect.csr import CSRStorage, AutoCSR
from litedram.common import *
from litedram.phy import dfi
from litedram.core.refresher import Refresher
from litedram.core.bankmachine import BankMachine
from litedram.core.multiplexer import Multiplexer

# Settings -----------------------------------------------------------------------------------------

class ControllerSettings(Settings):
    def __init__(self,
        # Command buffers
        cmd_buffer_depth    = 8,
        cmd_buffer_buffered = False,

        # Read/Write times
        read_time           = 32,
        write_time          = 16,

        # Bandwidth
        with_bandwidth      = False,

        # Refresh
        with_refresh        = True,
        refresh_cls         = Refresher,
        refresh_zqcs_freq   = 1e0,
        refresh_postponing  = 1,

        # Auto-Precharge
        with_auto_precharge = True,

        # Address mapping
        address_mapping     = "ROW_BANK_COL"):
        self.set_attributes(locals())


REGISTER_NAMES = ("tRP", "tRCD", "tWR", "tWTR", "tREFI", "tRFC",
    "tFAW", "tCCD", "tCCD_WR", "tRTP", "tRRD", "tRC", "tRAS", "tZQCS")
class LiteDRAMControllerRegisterBank(Module, AutoCSR):
    def __init__(self, initial_timings, max_expected_values, memtype):
        for reg in REGISTER_NAMES:
            if reg == "tZQCS" and memtype in ["LPDDR4", "LPDDR5", "DDR5"]:
                continue # ZQCS refresher does not work with LPDDR4, LPDDR5 and DDR5
            try:
                width = getattr(max_expected_values, reg)
            except AttributeError:
                width = None
            width = width.bit_length() if width is not None else 1
            try:
                reset_val = getattr(initial_timings, reg)
            except AttributeError:
                reset_val = None
            csr = CSRStorage(width, name=reg, reset=reset_val if reset_val is not None else 0)
            assert reset_val is None or reset_val < 2**width, (reg, reset_val, 2**width)
            setattr(self, reg, csr)

    def get_register_signals(self):
        regs = {}
        for reg in REGISTER_NAMES:
            try:
                csr = getattr(self, reg)
            except AttributeError:
                continue
            if csr is not None:
                regs[reg] = csr.storage
        return regs


# Controller ---------------------------------------------------------------------------------------

class LiteDRAMController(Module):
    def __init__(self, phy_settings, geom_settings, timing_settings, max_expected_values, clk_freq,
        controller_settings=ControllerSettings()):
        if phy_settings.memtype == "SDR":
            burst_length = phy_settings.nphases
        else:
            burst_length = burst_lengths[phy_settings.memtype]
        address_align = log2_int(burst_length)

        # Settings ---------------------------------------------------------------------------------
        self.settings        = controller_settings
        self.settings.phy    = phy_settings
        self.settings.geom   = geom_settings
        self.settings.timing = timing_settings

        nranks = 1 #phy_settings.nranks
        nbanks = 2**geom_settings.bankbits

        # Registers --------------------------------------------------------------------------------

        self.registers = registers = LiteDRAMControllerRegisterBank(timing_settings, max_expected_values, phy_settings.memtype)
        timing_regs = registers.get_register_signals()

        # LiteDRAM Interface (User) ----------------------------------------------------------------
        __nranks = self.settings.phy.nranks
        self.settings.phy.nranks    = 1
        self.interface = interface = LiteDRAMInterface(address_align, self.settings)
        self.settings.phy.nranks    = __nranks

        # DFI Interface (Memory) -------------------------------------------------------------------
        self.dfi = dfi.Interface(
            addressbits = geom_settings.addressbits,
            bankbits    = geom_settings.bankbits,
            nranks      = 1, #phy_settings.nranks,
            databits    = phy_settings.dfi_databits,
            nphases     = phy_settings.nphases)

        # # #

        # Refresher --------------------------------------------------------------------------------
        self.submodules.refresher = self.settings.refresh_cls(self.settings,
            clk_freq    = clk_freq,
            timing_regs = timing_regs,
            zqcs_freq   = self.settings.refresh_zqcs_freq,
            postponing  = self.settings.refresh_postponing)

        # Bank Machines ----------------------------------------------------------------------------

        # tWTP (write-to-precharge) calculation ----------------------------------------------------
        write_latency = math.ceil(self.settings.phy.cwl / self.settings.phy.nphases)
        max_precharge_time = write_latency + max_expected_values.tWR + max_expected_values.tCCD # AL=0
        precharge_time_sig = Signal(max_precharge_time.bit_length())
        precharge_time = write_latency + timing_regs['tWR'] + \
            (timing_regs['tCCD'] if phy_settings.memtype != "DDR5" else timing_regs['tCCD_WR']) # AL=0
        # Value changes only on registers update, use sync to reduce critical path length
        self.sync += precharge_time_sig.eq(precharge_time)

        bank_machines = []
        for n in range(nranks*nbanks):
            bank_machine = BankMachine(n,
                address_width       = interface.address_width,
                address_align       = address_align,
                nranks              = nranks,
                settings            = self.settings,
                timing_regs         = timing_regs,
                precharge_time_sig  = precharge_time_sig)
            bank_machines.append(bank_machine)
            self.submodules += bank_machine
            self.comb += getattr(interface, "bank"+str(n)).connect(bank_machine.req)
        self.bank_machines = bank_machines

        # Multiplexer ------------------------------------------------------------------------------
        self.submodules.multiplexer = Multiplexer(
            settings      = self.settings,
            bank_machines = bank_machines,
            refresher     = self.refresher,
            dfi           = self.dfi,
            interface     = interface,
            timing_regs   = timing_regs)

    def get_csrs(self):
        return self.multiplexer.get_csrs() + self.registers.get_csrs() + \
            reduce(add, [bank.get_csrs() for bank in self.bank_machines])
