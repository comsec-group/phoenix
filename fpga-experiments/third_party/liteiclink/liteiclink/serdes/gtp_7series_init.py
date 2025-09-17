#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from math import ceil

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer
from migen.genlib.misc import WaitTimer

from liteiclink.serdes.common import *


__all__ = ["GTPTXInit", "GTPRXInit"]

# GTP TX Init --------------------------------------------------------------------------------------

class GTPTXInit(Module):
    def __init__(self, sys_clk_freq, buffer_enable):
        self.done            = Signal() # o
        self.restart         = Signal() # i

        # GTP signals
        self.plllock         = Signal() # i
        self.pllreset        = Signal() # o
        self.gttxreset       = Signal() # o
        self.gttxpd          = Signal() # o
        self.txresetdone     = Signal() # i
        self.txdlysreset     = Signal() # o
        self.txdlysresetdone = Signal() # i
        self.txphinit        = Signal() # o
        self.txphinitdone    = Signal() # i
        self.txphalign       = Signal() # o
        self.txphaligndone   = Signal() # i
        self.txdlyen         = Signal() # o
        self.txuserrdy       = Signal() # o

        # DRP (optional)
        self.drp_start       = Signal()        # o
        self.drp_done        = Signal(reset=1) # i

        # # #

        # Double-latch transceiver asynch outputs
        plllock         = Signal()
        txresetdone     = Signal()
        txdlysresetdone = Signal()
        txphinitdone    = Signal()
        txphaligndone   = Signal()
        self.specials += [
            MultiReg(self.plllock, plllock),
            MultiReg(self.txresetdone, txresetdone),
            MultiReg(self.txdlysresetdone, txdlysresetdone),
            MultiReg(self.txphinitdone, txphinitdone),
            MultiReg(self.txphaligndone, txphaligndone)
        ]

        # Deglitch FSM outputs driving transceiver asynch inputs
        gttxreset   = Signal()
        gttxpd      = Signal()
        txdlysreset = Signal()
        txphinit    = Signal()
        txphalign   = Signal()
        txdlyen     = Signal()
        txuserrdy   = Signal()
        self.sync += [
            self.gttxreset.eq(gttxreset),
            self.gttxpd.eq(gttxpd),
            self.txdlysreset.eq(txdlysreset),
            self.txphinit.eq(txphinit),
            self.txphalign.eq(txphalign),
            self.txdlyen.eq(txdlyen),
            self.txuserrdy.eq(txuserrdy)
        ]

        # Detect txphaligndone rising edge
        txphaligndone_r = Signal(reset=1)
        txphaligndone_rising = Signal()
        self.sync += txphaligndone_r.eq(txphaligndone)
        self.comb += txphaligndone_rising.eq(txphaligndone & ~txphaligndone_r)

        # FSM
        fsm = ResetInserter()(FSM(reset_state="POWER-DOWN"))
        self.submodules.fsm = fsm
        fsm.act("POWER-DOWN",
            gttxreset.eq(1),
            gttxpd.eq(1),
            self.pllreset.eq(1),
            NextState("DRP")
        )
        fsm.act("DRP",
            gttxreset.eq(1),
            self.pllreset.eq(1),
            self.drp_start.eq(1),
            If(self.drp_done,
                NextState("WAIT-PLL-RESET")
            )
        )
        fsm.act("WAIT-PLL-RESET",
            gttxreset.eq(1),
            If(plllock,
                NextState("WAIT-INIT-DELAY")
            )
        )
        # Wait 500ns after configuration before releasing GTP reset (to follow AR43482)
        init_delay = WaitTimer(int(500e-9*sys_clk_freq))
        self.submodules += init_delay
        self.comb += init_delay.wait.eq(1)
        fsm.act("WAIT-INIT-DELAY",
            gttxreset.eq(1),
            If(init_delay.done,
                NextState("WAIT-GTP-RESET")
            )
        )
        fsm.act("WAIT-GTP-RESET",
            txuserrdy.eq(1),
            If(txresetdone,
                If(buffer_enable,
                    NextState("READY")
                ).Else(
                    NextState("ALIGN")
                )
            )
        )
        fsm.act("ALIGN",
            txuserrdy.eq(1),
            txdlysreset.eq(1),
            If(txdlysresetdone,
                NextState("WAIT-ALIGN")
            )
        )
        fsm.act("WAIT-ALIGN",
            txuserrdy.eq(1),
            txphinit.eq(1),
            If(txphinitdone,
                NextState("WAIT-FIRST-ALIGN-DONE")
            )
        )
        # Align done after 2 rising edges of Xxphaligndone (UG482 / buffer bypass config mode)
        fsm.act("WAIT-FIRST-ALIGN-DONE",
            txuserrdy.eq(1),
            txphalign.eq(1),
            If(txphaligndone_rising,
                NextState("WAIT-SECOND-ALIGN-DONE")
            )
        )
        fsm.act("WAIT-SECOND-ALIGN-DONE",
            txuserrdy.eq(1),
            txdlyen.eq(1),
            If(txphaligndone_rising,
                NextState("READY")
            )
        )
        fsm.act("READY",
            txuserrdy.eq(1),
            txdlyen.eq(1),
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

# GTP RX Init --------------------------------------------------------------------------------------

class GTPRXInit(Module):
    def __init__(self, sys_clk_freq, buffer_enable):
        self.done            = Signal()
        self.restart         = Signal()

        # GTP signals
        self.plllock         = Signal()
        self.gtrxreset       = Signal()
        self.gtrxpd          = Signal()
        self.rxresetdone     = Signal()
        self.rxdlysreset     = Signal()
        self.rxdlysresetdone = Signal()
        self.rxphalign       = Signal()
        self.rxuserrdy       = Signal()
        self.rxsyncdone      = Signal()
        self.rxpmaresetdone  = Signal()

        self.drp             = DRPInterface()

        # # #

        drpvalue = Signal(16)
        drpmask  = Signal()
        self.comb += [
            self.drp.clk.eq(ClockSignal()),
            self.drp.addr.eq(0x011),
            If(drpmask,
                self.drp.di.eq(drpvalue & 0xf7ff)
            ).Else(
                self.drp.di.eq(drpvalue)
            )
        ]

        rxpmaresetdone = Signal()
        self.specials += MultiReg(self.rxpmaresetdone, rxpmaresetdone)
        rxpmaresetdone_r = Signal()
        self.sync += rxpmaresetdone_r.eq(rxpmaresetdone)

        # Double-latch transceiver asynch outputs
        plllock         = Signal()
        rxresetdone     = Signal()
        rxdlysresetdone = Signal()
        rxsyncdone      = Signal()
        self.specials += [
            MultiReg(self.plllock, plllock),
            MultiReg(self.rxresetdone, rxresetdone),
            MultiReg(self.rxdlysresetdone, rxdlysresetdone),
            MultiReg(self.rxsyncdone, rxsyncdone)
        ]

        # Deglitch FSM outputs driving transceiver asynch inputs
        gtrxreset   = Signal()
        gtrxpd      = Signal()
        rxdlysreset = Signal()
        rxphalign   = Signal()
        rxuserrdy   = Signal()
        self.sync += [
            self.gtrxreset.eq(gtrxreset),
            self.gtrxpd.eq(gtrxpd),
            self.rxdlysreset.eq(rxdlysreset),
            self.rxphalign.eq(rxphalign),
            self.rxuserrdy.eq(rxuserrdy)
        ]

        fsm = ResetInserter()(FSM(reset_state="POWER-DOWN"))
        self.submodules.fsm = fsm
        fsm.act("POWER-DOWN",
            gtrxreset.eq(1),
            gtrxpd.eq(1),
            NextState("WAIT-INIT-DELAY")
        )
        # Wait 500ns after configuration before releasing GTP reset (to follow AR43482)
        init_delay = WaitTimer(int(500e-9*sys_clk_freq))
        self.submodules += init_delay
        self.comb += init_delay.wait.eq(1)
        fsm.act("WAIT-INIT-DELAY",
            gtrxreset.eq(1),
            If(plllock & init_delay.done,
                NextState("DRP_READ_ISSUE")
            )
        )
        fsm.act("DRP_READ_ISSUE",
            gtrxreset.eq(1),
            self.drp.en.eq(1),
            NextState("DRP_READ_WAIT")
        )
        fsm.act("DRP_READ_WAIT",
            gtrxreset.eq(1),
            If(self.drp.rdy,
                NextValue(drpvalue, self.drp.do),
                NextState("DRP_MOD_ISSUE")
            )
        )
        fsm.act("DRP_MOD_ISSUE",
            gtrxreset.eq(1),
            drpmask.eq(1),
            self.drp.en.eq(1),
            self.drp.we.eq(1),
            NextState("DRP_MOD_WAIT")
        )
        fsm.act("DRP_MOD_WAIT",
            gtrxreset.eq(1),
            If(self.drp.rdy,
                NextState("WAIT_PMARST_FALL")
            )
        )
        fsm.act("WAIT_PMARST_FALL",
            rxuserrdy.eq(1),
            If(rxpmaresetdone_r & ~rxpmaresetdone,
                NextState("DRP_RESTORE_ISSUE")
            )
        )
        fsm.act("DRP_RESTORE_ISSUE",
            rxuserrdy.eq(1),
            self.drp.en.eq(1),
            self.drp.we.eq(1),
            NextState("DRP_RESTORE_WAIT")
        )
        fsm.act("DRP_RESTORE_WAIT",
            rxuserrdy.eq(1),
            If(self.drp.rdy,
                NextState("WAIT-GTP-RESET")
            )
        )
        fsm.act("WAIT-GTP-RESET",
            rxuserrdy.eq(1),
            If(rxresetdone,
                If(buffer_enable,
                    NextState("READY")
                ).Else(
                    NextState("ALIGN")
                )
            )
        )
        fsm.act("ALIGN",
            rxuserrdy.eq(1),
            rxdlysreset.eq(1),
            If(rxdlysresetdone,
                NextState("WAIT_ALIGN_DONE")
            )
        )
        fsm.act("WAIT_ALIGN_DONE",
            rxuserrdy.eq(1),
            If(rxsyncdone,
                NextState("READY")
            )
        )
        fsm.act("READY",
            rxuserrdy.eq(1),
            self.done.eq(1),
            If(self.restart,
                NextState("POWER-DOWN")
            )
        )

        # FSM watchdog / restart
        watchdog = WaitTimer(int(4e-3*sys_clk_freq))
        self.submodules += watchdog
        self.comb += [
            watchdog.wait.eq(~fsm.reset & ~self.done),
            fsm.reset.eq(self.restart | watchdog.done)
        ]
