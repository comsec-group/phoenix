#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.misc import WaitTimer

from litex.build.io import *

from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from liteiclink.serwb.datapath import TXDatapath, RXDatapath

# SerDes Clocking ----------------------------------------------------------------------------------

class _SerdesClocking(Module):
    def __init__(self, pads, mode="master"):
        self.refclk = Signal()

        # # #

        # In Master mode, generate the clock with 180° phase shift so that Slave can use this clock
        # to sample data.
        if mode == "master":
            self.specials += DDROutput(0, 1, self.refclk)
            if hasattr(pads, "clk_p"):
                self.specials += DifferentialOutput(self.refclk, pads.clk_p, pads.clk_n)
            else:
                self.comb += pads.clk.eq(self.refclk)

        # In Slave mode, use the clock provided by Master.
        elif mode == "slave":
            if hasattr(pads, "clk_p"):
                self.specials += DifferentialInput(pads.clk_p, pads.clk_n, self.refclk)
            else:
                self.comb += self.refclk.eq(pads.clk)
        else:
            raise ValueError

# SerDes TX ----------------------------------------------------------------------------------------

class _SerdesTX(Module):
    def __init__(self, pads):
        # Control
        self.idle  = idle  = Signal()
        self.comma = comma = Signal()

        # Datapath
        self.sink = sink = stream.Endpoint([("data", 32)])

        # # #

        # Datapath
        self.submodules.datapath = datapath = TXDatapath(1)
        self.comb += [
            sink.connect(datapath.sink),
            datapath.source.ready.eq(1),
            datapath.idle.eq(idle),
            datapath.comma.eq(comma)
        ]

        # Output data (on rising edge of sys_clk)
        self.data = data = Signal()
        self.sync += data.eq(datapath.source.data)
        if hasattr(pads, "tx_p"):
            self.specials += DifferentialOutput(data, pads.tx_p, pads.tx_n)
        else:
            self.comb += pads.tx.eq(data)

# SerDes RX ----------------------------------------------------------------------------------------

class _SerdesRX(Module):
    def __init__(self, pads):
        # Control
        self.shift = shift = Signal(6)

        # Status
        self.idle  = idle  = Signal()
        self.comma = comma = Signal()

        # Datapath
        self.source = source = stream.Endpoint([("data", 32)])

        # # #

        # Input data (on rising edge of sys_clk)
        self.data = data = Signal()
        data_d = Signal()
        if hasattr(pads, "rx_p"):
            _data = Signal()
            self.specials += DifferentialInput(pads.rx_p, pads.rx_n, _data)
            self.sync += data.eq(_data)
        else:
            self.sync += data.eq(pads.rx)

        # Datapath
        self.submodules.datapath = datapath = RXDatapath(1)
        self.comb += [
            datapath.sink.valid.eq(1),
            datapath.sink.data.eq(data),
            datapath.shift.eq(self.shift),
            datapath.source.connect(source),
            idle.eq(datapath.idle),
            comma.eq(datapath.comma)
        ]

# SerDes -------------------------------------------------------------------------------------------

@ResetInserter()
class _Serdes(Module):
    def __init__(self, pads, mode="master"):
        if hasattr(pads, "clk"):
            self.submodules.clocking = _SerdesClocking(pads, mode)
        self.submodules.tx       = _SerdesTX(pads)
        self.submodules.rx       = _SerdesRX(pads)


# SerDes Initialization/Synchronisation ------------------------------------------------------------
#
# - Master sends IDLE patterns (zeroes) to Slave to reset it.
# - Master sends K28.5 commas to allow Slave to calibrate, Slave sends IDLE patterns.
# - Slave sends K28.5 commas to allow Master to calibrate, Master sends K28.5 commas.
# - Master stops sending K28.5 commas.
# - Slave stops sending K28.5 commas.
# - Physical link is ready.
# --------------------------------------------------------------------------------------------------

# SerDes Master Init -------------------------------------------------------------------------------

@ResetInserter()
class _SerdesMasterInit(Module):
    def __init__(self, serdes, timeout):
        self.ready = Signal()
        self.error = Signal()

        # # #

        # Shift
        self.shift = shift = Signal(max=40)

        # Timer
        self.submodules.timer = timer = WaitTimer(timeout)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
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
            If(serdes.rx.comma,
                timer.wait.eq(1),
                If(timer.done,
                    NextState("READY")
                )
            ).Else(
                NextState("INC-SHIFT")
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("INC-SHIFT",
            NextState("WAIT-STABLE"),
            If(shift == (40 - 1),
                NextState("ERROR")
            ).Else(
                serdes.rx.shift.eq(1),
                NextValue(shift, shift + 1)
            ),
            serdes.tx.comma.eq(1)
        )
        fsm.act("READY",
            self.ready.eq(1)
        )
        fsm.act("ERROR",
            self.error.eq(1)
        )

# SerDes Slave Init --------------------------------------------------------------------------------

@ResetInserter()
class _SerdesSlaveInit(Module, AutoCSR):
    def __init__(self, serdes, timeout):
        self.ready = Signal()
        self.error = Signal()

        # # #

        # Shift
        self.shift = shift = Signal(max=40)

        # Timer
        self.submodules.timer = timer = WaitTimer(timeout)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
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
            If(serdes.rx.comma,
                timer.wait.eq(1),
                If(timer.done,
                    NextState("SEND-PATTERN")
                )
            ).Else(
                NextState("INC-SHIFT")
            ),
            serdes.tx.idle.eq(1)
        )
        fsm.act("INC-SHIFT",
            NextState("WAIT-STABLE"),
            If(shift == (40 - 1),
                NextState("ERROR")
            ).Else(
                serdes.rx.shift.eq(1),
                NextValue(shift, shift + 1)
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

# SerDes Init Control ------------------------------------------------------------------------------

class _SerdesControl(Module, AutoCSR):
    def __init__(self, serdes, init, mode="master"):
        if mode == "master":
            self.reset = CSR()
        self.ready = CSRStatus()
        self.error = CSRStatus()

        self.shift = CSRStatus(6)

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
            # in IDLE state.
            self.sync += [
                init.reset.eq(serdes.rx.idle),
                serdes.reset.eq(serdes.rx.idle)
            ]
        self.comb += [
            self.ready.status.eq(init.ready),
            self.error.status.eq(init.error),
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
    def __init__(self, device, pads, mode="master", init_timeout=2**16):
        self.sink   = sink   = stream.Endpoint([("data", 32)])
        self.source = source = stream.Endpoint([("data", 32)])
        assert mode in ["master", "slave"]

        # SerDes
        self.submodules.serdes = _Serdes(pads, mode)

        # SerDes Init
        init_cls = {"master": _SerdesMasterInit, "slave":  _SerdesSlaveInit}[mode]
        self.submodules.init = init_cls(self.serdes, init_timeout)

        # SerDes Control
        self.submodules.control = _SerdesControl(self.serdes, self.init, mode)

        # Dataflow
        self.comb += [
            If(self.init.ready,
                If(sink.valid,
                    sink.connect(self.serdes.tx.sink),
                ),
                self.serdes.rx.source.connect(source)
            ),
            self.serdes.tx.sink.valid.eq(1),  # Always transmitting.
            self.serdes.rx.source.ready.eq(1) # Always receiving.
        ]

        # The PRBS test is using the scrambler/descrambler as PRBS, sending 0 to the scrambler and
        # checking that descrambler output is always 0.
        self.comb += self.control.prbs_error.eq(source.valid & source.ready & (source.data != 0))
