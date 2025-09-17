#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.misc import WaitTimer

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from liteiclink.serwb.kuserdes import KUSerdes
from liteiclink.serwb.s7serdes import S7Serdes


# SerDes Initialization/Synchronisation ------------------------------------------------------------
#
# - Master sends IDLE patterns (zeroes) to Slave to reset it.
# - Master sends K28.5 commas to allow Slave to calibrate, Slave sends IDLE patterns.
# - Slave sends K28.5 commas to allow Master to calibrate, Master sends K28.5 commas.
# - Master stops sending K28.5 commas.
# - Slave stops sending K28.5 commas.
# - Physical link is ready.
# --------------------------------------------------------------------------------------------------

# Serdes Master Init -------------------------------------------------------------------------------

@ResetInserter()
class _SerdesMasterInit(Module):
    def __init__(self, serdes, taps, timeout):
        self.ready = Signal()
        self.error = Signal()

        # # #

        self.delay           = delay           = Signal(max=taps)
        self.delay_min       = delay_min       = Signal(max=taps)
        self.delay_min_found = delay_min_found = Signal()
        self.delay_max       = delay_max       = Signal(max=taps)
        self.delay_max_found = delay_max_found = Signal()
        self.shift           = shift           = Signal(max=40)

        # Timer
        self.submodules.timer = timer = WaitTimer(timeout)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(delay,           0),
            NextValue(delay_min,       0),
            NextValue(delay_min_found, 0),
            NextValue(delay_max,       0),
            NextValue(delay_max_found, 0),
            serdes.rx.delay_rst.eq(1),
            NextValue(shift, 0),
            NextState("RESET-SLAVE"),
            serdes.tx.idle.eq(1)
        )
        fsm.act("RESET-SLAVE",
            timer.wait.eq(1),
            If(timer.done,
                timer.wait.eq(0),
                NextState("SEND-PATTERN")
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("SEND-PATTERN",
            If(~serdes.rx.idle,
                timer.wait.eq(1),
                If(timer.done,
                    NextState("CHECK-PATTERN")
                )
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("WAIT-STABLE",
            timer.wait.eq(1),
            If(timer.done,
                timer.wait.eq(0),
                NextState("CHECK-PATTERN")
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("CHECK-PATTERN",
            If(~delay_min_found,
                If(serdes.rx.comma,
                    timer.wait.eq(1),
                    If(timer.done,
                        timer.wait.eq(0),
                        NextValue(delay_min, delay),
                        NextValue(delay_min_found, 1)
                    )
                ).Else(
                    NextState("INC-DELAY-SHIFT")
                ),
            ).Else(
                If(~serdes.rx.comma,
                    NextValue(delay_max, delay),
                    NextValue(delay_max_found, 1),
                    NextState("CHECK-SAMPLING-WINDOW")
                ).Else(
                    NextState("INC-DELAY-SHIFT")
                )
            ),
            serdes.tx.comma.eq(1)
        )
        self.comb += serdes.rx.shift.eq(shift)
        fsm.act("INC-DELAY-SHIFT",
            NextState("WAIT-STABLE"),
            If(delay == (taps - 1),
                If(shift == (40 - 1),
                    NextState("ERROR")
                ).Else(
                    NextValue(delay_min_found, 0),
                    NextValue(delay_min,       0),
                    NextValue(delay_max_found, 0),
                    NextValue(delay_max,       0),
                    NextValue(shift, shift + 1)
                ),
                NextValue(delay, 0),
                serdes.rx.delay_rst.eq(1)
            ).Else(
                NextValue(delay, delay + 1),
                serdes.rx.delay_inc.eq(1)
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("CHECK-SAMPLING-WINDOW",
            If((delay_min == 0) |
               (delay_max == (taps - 1)) |
               ((delay_max - delay_min) < taps//16),
               NextValue(delay_min_found, 0),
               NextValue(delay_max_found, 0),
               NextState("WAIT-STABLE")
            ).Else(
                NextValue(delay, 0),
                serdes.rx.delay_rst.eq(1),
                NextState("CONFIGURE-SAMPLING-WINDOW")
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("CONFIGURE-SAMPLING-WINDOW",
            If(delay == (delay_min + (delay_max - delay_min)[1:]),
                NextState("READY")
            ).Else(
                NextValue(delay, delay + 1),
                serdes.rx.delay_inc.eq(1)
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("READY",
            self.ready.eq(1)
        )
        fsm.act("ERROR",
            self.error.eq(1)
        )

# Serdes Slave Init --------------------------------------------------------------------------------

@ResetInserter()
class _SerdesSlaveInit(Module, AutoCSR):
    def __init__(self, serdes, taps, timeout):
        self.ready = Signal()
        self.error = Signal()

        # # #

        self.delay           = delay           = Signal(max=taps)
        self.delay_min       = delay_min       = Signal(max=taps)
        self.delay_min_found = delay_min_found = Signal()
        self.delay_max       = delay_max       = Signal(max=taps)
        self.delay_max_found = delay_max_found = Signal()
        self.shift         = shift         = Signal(max=40)

        # Timer
        self.submodules.timer = timer = WaitTimer(timeout)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(delay,           0),
            NextValue(delay_min,       0),
            NextValue(delay_min_found, 0),
            NextValue(delay_max,       0),
            NextValue(delay_max_found, 0),
            serdes.rx.delay_rst.eq(1),
            NextValue(shift, 0),
            timer.wait.eq(1),
            If(timer.done,
                timer.wait.eq(0),
                NextState("WAIT-STABLE"),
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("WAIT-STABLE",
            timer.wait.eq(1),
            If(timer.done,
                timer.wait.eq(0),
                NextState("CHECK-PATTERN")
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("CHECK-PATTERN",
            If(~delay_min_found,
                If(serdes.rx.comma,
                    timer.wait.eq(1),
                    If(timer.done,
                        timer.wait.eq(0),
                        NextValue(delay_min, delay),
                        NextValue(delay_min_found, 1)
                    )
                ).Else(
                    NextState("INC-DELAY-SHIFT")
                ),
            ).Else(
                If(~serdes.rx.comma,
                    NextValue(delay_max, delay),
                    NextValue(delay_max_found, 1),
                    NextState("CHECK-SAMPLING-WINDOW")
                ).Else(
                    NextState("INC-DELAY-SHIFT")
                )
            ),
            serdes.tx.idle.eq(1)
        )
        self.comb += serdes.rx.shift.eq(shift)
        fsm.act("INC-DELAY-SHIFT",
            NextState("WAIT-STABLE"),
            If(delay == (taps - 1),
                If(shift == (40 - 1),
                    NextState("ERROR")
                ).Else(
                    NextValue(delay_min_found, 0),
                    NextValue(delay_min,       0),
                    NextValue(delay_max_found, 0),
                    NextValue(delay_max,       0),
                    NextValue(shift, shift + 1)
                ),
                NextValue(delay, 0),
                serdes.rx.delay_rst.eq(1)
            ).Else(
                NextValue(delay, delay + 1),
                serdes.rx.delay_inc.eq(1)
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("CHECK-SAMPLING-WINDOW",
            If((delay_min == 0) |
               (delay_max == (taps - 1)) |
               ((delay_max - delay_min) < taps//16),
               NextValue(delay_min_found, 0),
               NextValue(delay_max_found, 0),
               NextState("WAIT-STABLE")
            ).Else(
                NextValue(delay, 0),
                serdes.rx.delay_rst.eq(1),
                NextState("CONFIGURE-SAMPLING-WINDOW")
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("CONFIGURE-SAMPLING-WINDOW",
            If(delay == (delay_min + (delay_max - delay_min)[1:]),
                NextState("SEND-PATTERN")
            ).Else(
                NextValue(delay, delay + 1),
                serdes.rx.delay_inc.eq(1),
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("SEND-PATTERN",
            timer.wait.eq(1),
            If(timer.done,
                If(~serdes.rx.comma,
                    NextState("READY")
                )
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("READY",
            self.ready.eq(1)
        )
        fsm.act("ERROR",
            self.error.eq(1)
        )

# Serdes Init Control ------------------------------------------------------------------------------

class _SerdesControl(Module, AutoCSR):
    def __init__(self, serdes, init, mode="master"):
        if mode == "master":
            self.reset = CSR()
        self.ready = CSRStatus()
        self.error = CSRStatus()

        self.delay           = CSRStatus(9)
        self.delay_min_found = CSRStatus()
        self.delay_min       = CSRStatus(9)
        self.delay_max_found = CSRStatus()
        self.delay_max       = CSRStatus(9)
        self.shift           = CSRStatus(6)

        self.prbs_error  = Signal()
        self.prbs_start  = CSR()
        self.prbs_cycles = CSRStorage(32)
        self.prbs_errors = CSRStatus(32)

        # # #

        if mode == "master":
            # In Master mode, reset is coming from CSR, it resets the Master that will also reset
            # the Slave by putting the link in IDLE state.
            self.sync += init.reset.eq(self.reset.re)
        else:
            # In Slave mode, reset is coming from link, Master reset the Slave by putting the link
            # in IDLE state..
            self.sync += [
                init.reset.eq(serdes.rx.idle),
                serdes.reset.eq(serdes.rx.idle)
            ]
        self.comb += [
            self.ready.status.eq(init.ready),
            self.error.status.eq(init.error),
            self.delay.status.eq(init.delay),
            self.delay_min_found.status.eq(init.delay_min_found),
            self.delay_min.status.eq(init.delay_min),
            self.delay_max_found.status.eq(init.delay_max_found),
            self.delay_max.status.eq(init.delay_max),
            self.shift.status.eq(init.shift)
        ]

        # PRBS
        prbs_cycles = Signal(32)
        prbs_errors = self.prbs_errors.status
        self.submodules.prbs_fsm = prbs_fsm = FSM(reset_state="IDLE")
        prbs_fsm.act("IDLE",
            NextValue(prbs_cycles, 0),
            If(self.prbs_start.re,
                NextValue(prbs_errors, 0),
                NextState("CHECK")
            )
        )
        prbs_fsm.act("CHECK",
            NextValue(prbs_cycles, prbs_cycles + 1),
            If(self.prbs_error,
                NextValue(prbs_errors, prbs_errors + 1),
            ),
            If(prbs_cycles == self.prbs_cycles.storage,
                NextState("IDLE")
            )
        )

# SERWB PHY ----------------------------------------------------------------------------------------

class SERWBPHY(Module, AutoCSR):
    def __init__(self, device, pads, mode="master", init_timeout=2**15):
        self.sink   = sink   = stream.Endpoint([("data", 32)])
        self.source = source = stream.Endpoint([("data", 32)])
        assert mode in ["master", "slave"]

        # SerDes
        if device[:4] == "xcku":
            taps = 512
            self.submodules.serdes = KUSerdes(pads, mode)
        elif device[:4] == "xc7a":
            taps = 32
            self.submodules.serdes = S7Serdes(pads, mode)
        else:
            raise NotImplementedError

        # SerDes Init
        init_cls = {"master": _SerdesMasterInit, "slave":  _SerdesSlaveInit}[mode]
        self.submodules.init = init_cls(self.serdes, taps, init_timeout)

        # SerDes Control
        self.submodules.control = _SerdesControl(self.serdes, self.init, mode)

        # Dataflow
        self.comb += [
            If(self.init.ready,
                If(sink.valid,
                    sink.connect(self.serdes.tx.sink),
                ),
                self.serdes.rx.source.connect(source)
            ).Else(
                self.serdes.rx.source.ready.eq(1)
            ),
            self.serdes.tx.sink.valid.eq(1) # Always transmitting
        ]

        # The PRBS test is using the scrambler/descrambler as PRBS, sending 0 to the scrambler and
        # checking that descrambler output is always 0.
        self.comb += self.control.prbs_error.eq(source.valid & source.ready & (source.data != 0))
