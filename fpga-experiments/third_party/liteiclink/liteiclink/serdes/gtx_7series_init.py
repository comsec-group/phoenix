#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from math import ceil

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer
from migen.genlib.misc import WaitTimer


__all__ = ["GTXTXInit", "GTXRXInit"]

# GTX Init -----------------------------------------------------------------------------------------

class GTXInit(Module):
    def __init__(self, sys_clk_freq, buffer_enable):
        self.done            = Signal() # o
        self.restart         = Signal() # i

        # GTX signals
        self.plllock         = Signal() # i
        self.pllreset        = Signal() # o
        self.gtXxreset       = Signal() # o
        self.gtXxpd          = Signal() # o
        self.Xxresetdone     = Signal() # i
        self.Xxdlysreset     = Signal() # o
        self.Xxdlysresetdone = Signal() # i
        self.Xxphaligndone   = Signal() # i
        self.Xxuserrdy       = Signal() # o

        # DRP (optional)
        self.drp_start       = Signal()        # o
        self.drp_done        = Signal(reset=1) # i

        # # #

        # Double-latch transceiver asynch outputs
        plllock         = Signal()
        Xxresetdone     = Signal()
        Xxdlysresetdone = Signal()
        Xxphaligndone   = Signal()
        self.specials += [
            MultiReg(self.plllock, plllock),
            MultiReg(self.Xxresetdone, Xxresetdone),
            MultiReg(self.Xxdlysresetdone, Xxdlysresetdone),
            MultiReg(self.Xxphaligndone, Xxphaligndone)
        ]

        # Detect Xxphaligndone rising edge
        Xxphaligndone_r      = Signal(reset=1)
        Xxphaligndone_rising = Signal()
        self.sync += Xxphaligndone_r.eq(Xxphaligndone)
        self.comb += Xxphaligndone_rising.eq(Xxphaligndone & ~Xxphaligndone_r)

        # Deglitch FSM outputs driving transceiver asynch inputs
        gtXxreset   = Signal()
        gtXxpd      = Signal()
        Xxdlysreset = Signal()
        Xxuserrdy   = Signal()
        self.sync += [
            self.gtXxreset.eq(gtXxreset),
            self.gtXxpd.eq(gtXxpd),
            self.Xxdlysreset.eq(Xxdlysreset),
            self.Xxuserrdy.eq(Xxuserrdy)
        ]

        # FSM
        fsm = ResetInserter()(FSM(reset_state="POWER-DOWN"))
        self.submodules.fsm = fsm
        fsm.act("POWER-DOWN",
            gtXxreset.eq(1),
            gtXxpd.eq(1),
            self.pllreset.eq(1),
            NextState("DRP")
        )
        fsm.act("DRP",
            gtXxreset.eq(1),
            self.pllreset.eq(1),
            self.drp_start.eq(1),
            If(self.drp_done,
                NextState("WAIT-PLL-RESET")
            )
        )
        fsm.act("WAIT-PLL-RESET",
            gtXxreset.eq(1),
            If(plllock,
                NextState("WAIT-INIT-DELAY")
            )
        )
        # Wait 500ns after configuration before releasing GTX reset (to follow AR43482)
        init_delay = WaitTimer(int(500e-9*sys_clk_freq))
        self.submodules += init_delay
        self.comb += init_delay.wait.eq(1)
        fsm.act("WAIT-INIT-DELAY",
            gtXxreset.eq(1),
            If(init_delay.done,
                NextState("WAIT-GTX-RESET")
            )
        )
        fsm.act("WAIT-GTX-RESET",
            Xxuserrdy.eq(1),
            If(Xxresetdone,
                NextState("WAIT-CDR-LOCK")
            )
        )
        # Wait for clock recovery lock (only needed for RX but we also do it for TX
        cdr_lock_timer = WaitTimer(1024)
        self.submodules += cdr_lock_timer
        fsm.act("WAIT-CDR-LOCK",
            Xxuserrdy.eq(1),
            cdr_lock_timer.wait.eq(1),
            If(cdr_lock_timer.done,
                If(buffer_enable,
                    NextState("READY")
                ).Else(
                    NextState("ALIGN")
                )
            )
        )
        fsm.act("ALIGN",
            Xxuserrdy.eq(1),
            Xxdlysreset.eq(1),
            NextState("WAIT-ALIGN")
        )
        fsm.act("WAIT-ALIGN",
            Xxuserrdy.eq(1),
            If(Xxdlysresetdone,
                NextState("WAIT-FIRST-ALIGN-DONE")
            )
        )
        # Align done after 2 rising edges of Xxphaligndone (UG476 / buffer bypass config mode)
        fsm.act("WAIT-FIRST-ALIGN-DONE",
            Xxuserrdy.eq(1),
            If(Xxphaligndone_rising,
                NextState("WAIT-SECOND-ALIGN-DONE")
            )
        )
        fsm.act("WAIT-SECOND-ALIGN-DONE",
            Xxuserrdy.eq(1),
            If(Xxphaligndone_rising,
                NextState("READY")
            )
        )
        fsm.act("READY",
            Xxuserrdy.eq(1),
            self.done.eq(1),
            If(self.restart,
                NextState("POWER-DOWN")
            )
        )

        # FSM watchdog / restart
        watchdog = WaitTimer(int(1e-3*sys_clk_freq))
        self.submodules += watchdog
        self.comb += [
            watchdog.wait.eq(~fsm.reset & ~self.done),
            fsm.reset.eq(self.restart | watchdog.done)
        ]

# GTX TX Init --------------------------------------------------------------------------------------

class GTXTXInit(GTXInit):
    pass

# GTX RX Init --------------------------------------------------------------------------------------
class GTXRXInit(GTXInit):
    pass
