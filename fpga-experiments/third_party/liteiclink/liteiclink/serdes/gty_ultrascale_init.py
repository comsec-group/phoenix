#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from math import ceil

from migen import *
from migen.genlib.cdc import MultiReg
from migen.genlib.misc import WaitTimer


__all__ = ["GTYTXInit", "GTYRXInit"]

# GTY Init -----------------------------------------------------------------------------------------

class GTYInit(Module):
    def __init__(self, sys_clk_freq, rx, buffer_enable):
        self.done            = Signal() # o
        self.restart         = Signal() # i

        # GTH signals
        self.plllock         = Signal() # i
        self.pllreset        = Signal() # o
        self.gtXxreset       = Signal() # o
        self.Xxresetdone     = Signal() # i
        self.Xxdlysreset     = Signal() # o
        self.Xxdlysresetdone = Signal() # i
        self.Xxphaligndone   = Signal() # i
        self.Xxsyncdone      = Signal() # i
        self.Xxuserrdy       = Signal() # o

        # # #

        # Double-latch transceiver asynch outputs
        plllock         = Signal()
        Xxresetdone     = Signal()
        Xxdlysresetdone = Signal()
        Xxphaligndone   = Signal()
        Xxsyncdone      = Signal()
        self.specials += [
            MultiReg(self.plllock, plllock),
            MultiReg(self.Xxresetdone, Xxresetdone),
            MultiReg(self.Xxdlysresetdone, Xxdlysresetdone),
            MultiReg(self.Xxphaligndone, Xxphaligndone),
            MultiReg(self.Xxsyncdone, Xxsyncdone)
        ]

        # Deglitch FSM outputs driving transceiver asynch inputs
        gtXxreset   = Signal()
        Xxdlysreset = Signal()
        Xxuserrdy   = Signal()
        self.sync += [
            self.gtXxreset.eq(gtXxreset),
            self.Xxdlysreset.eq(Xxdlysreset),
            self.Xxuserrdy.eq(Xxuserrdy)
        ]

        # PLL reset must be at least 2us
        pll_reset_cycles = ceil(2e-6*sys_clk_freq)
        pll_reset_timer  = WaitTimer(pll_reset_cycles)
        self.submodules += pll_reset_timer

        fsm = ResetInserter()(FSM(reset_state="RESET_ALL"))
        self.submodules.fsm = fsm

        ready_timer = WaitTimer(int(10e-3*sys_clk_freq))
        self.submodules += ready_timer
        self.comb += [
            ready_timer.wait.eq(~self.done & ~fsm.reset),
            fsm.reset.eq(self.restart | ready_timer.done)
        ]

        if rx:
            cdr_stable_timer = WaitTimer(1024)
            self.submodules += cdr_stable_timer

        Xxphaligndone_r      = Signal(reset=1)
        Xxphaligndone_rising = Signal()
        self.sync += Xxphaligndone_r.eq(Xxphaligndone)
        self.comb += Xxphaligndone_rising.eq(Xxphaligndone & ~Xxphaligndone_r)

        fsm.act("RESET_ALL",
            gtXxreset.eq(1),
            self.pllreset.eq(1),
            pll_reset_timer.wait.eq(1),
            If(pll_reset_timer.done,
                NextState("RELEASE_PLL_RESET")
            )
        )
        fsm.act("RELEASE_PLL_RESET",
            gtXxreset.eq(1),
            If(plllock, NextState("RELEASE_GTY_RESET"))
        )
        # Release GTY reset and wait for GTY resetdone (from UG578, GTY is reset on falling edge
        # of gtXxreset)
        if rx:
            fsm.act("RELEASE_GTY_RESET",
                Xxuserrdy.eq(1),
                cdr_stable_timer.wait.eq(1),
                If(Xxresetdone & cdr_stable_timer.done,
                    If(buffer_enable,
                        NextState("READY")
                    ).Else(
                        NextState("ALIGN")
                    )
                )
            )
        else:
            fsm.act("RELEASE_GTY_RESET",
                Xxuserrdy.eq(1),
                If(Xxresetdone,
                    If(buffer_enable,
                        NextState("READY")
                    ).Else(
                        NextState("ALIGN")
                    )
                )
            )
        # Start delay alignment (pulse)
        fsm.act("ALIGN",
            Xxuserrdy.eq(1),
            Xxdlysreset.eq(1),
            NextState("WAIT_ALIGN")
        )
        if rx:
            # Wait for delay alignment
            fsm.act("WAIT_ALIGN",
                Xxuserrdy.eq(1),
                If(Xxsyncdone,
                    NextState("READY")
                )
            )
        else:
            # Wait for delay alignment
            fsm.act("WAIT_ALIGN",
                Xxuserrdy.eq(1),
                If(Xxdlysresetdone,
                    NextState("WAIT_FIRST_ALIGN_DONE")
                )
            )

        # Wait 2 rising edges of Xxphaligndone (from UG576 in TX Buffer Bypass in Single-Lane Auto
        # Mode)
        fsm.act("WAIT_FIRST_ALIGN_DONE",
            Xxuserrdy.eq(1),
            If(Xxphaligndone_rising, NextState("WAIT_SECOND_ALIGN_DONE"))
        )
        fsm.act("WAIT_SECOND_ALIGN_DONE",
            Xxuserrdy.eq(1),
            If(Xxphaligndone_rising, NextState("READY"))
        )
        fsm.act("READY",
            Xxuserrdy.eq(1),
            self.done.eq(1),
            If(self.restart, NextState("RESET_ALL"))
        )

# GTY TX Init --------------------------------------------------------------------------------------

class GTYTXInit(GTYInit):
    def __init__(self, sys_clk_freq, buffer_enable=False):
        GTYInit.__init__(self, sys_clk_freq, rx=False, buffer_enable=buffer_enable)

# GTY RX Init --------------------------------------------------------------------------------------

class GTYRXInit(GTYInit):
    def __init__(self, sys_clk_freq, buffer_enable=False):
        GTYInit.__init__(self, sys_clk_freq, rx=True, buffer_enable=buffer_enable)
