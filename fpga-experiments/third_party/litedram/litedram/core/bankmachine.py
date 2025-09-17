#
# This file is part of LiteDRAM.
#
# Copyright (c) 2015 Sebastien Bourdeauducq <sb@m-labs.hk>
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""LiteDRAM BankMachine (Rows/Columns management)."""

import math

from migen import *

from litex.soc.interconnect import stream

from litex.soc.interconnect.csr import CSRStatus, AutoCSR
from litedram.common import *
from litedram.core.multiplexer import *

# AddressSlicer ------------------------------------------------------------------------------------

class _AddressSlicer:
    """Helper for extracting row/col from address

    Column occupies lower bits of the address, row - higher bits. Address has
    a forced alignment, so column does not contain alignment bits.
    """
    def __init__(self, colbits, address_align):
        self.colbits       = colbits
        self.address_align = address_align

    def row(self, address):
        split = self.colbits - self.address_align
        return address[split:]

    def col(self, address):
        split = self.colbits - self.address_align
        return Cat(Replicate(0, self.address_align), address[:split])

# BankMachine --------------------------------------------------------------------------------------

class BankMachine(Module, AutoCSR):
    """Converts requests from ports into DRAM commands

    BankMachine abstracts single DRAM bank by keeping track of the currently
    selected row. It converts requests from LiteDRAMCrossbar to targetted
    to that bank into DRAM commands that go to the Multiplexer, inserting any
    needed activate/precharge commands (with optional auto-precharge). It also
    keeps track and enforces some DRAM timings (other timings are enforced in
    the Multiplexer).

    BankMachines work independently from the data path (which connects
    LiteDRAMCrossbar with the Multiplexer directly).

    Stream of requests from LiteDRAMCrossbar is being queued, so that reqeust
    can be "looked ahead", and auto-precharge can be performed (if enabled in
    settings).

    Lock (cmd_layout.lock) is used to synchronise with LiteDRAMCrossbar. It is
    being held when:
     - there is a valid command awaiting in `cmd_buffer_lookahead` - this buffer
       becomes ready simply when the next data gets fetched to the `cmd_buffer`
     - there is a valid command in `cmd_buffer` - `cmd_buffer` becomes ready
       when the BankMachine sends wdata_ready/rdata_valid back to the crossbar

    Parameters
    ----------
    n : int
        Bank number
    address_width : int
        LiteDRAMInterface address width
    address_align : int
        Address alignment depending on burst length
    nranks : int
        Number of separate DRAM chips (width of chip select)
    settings : ControllerSettings
        LiteDRAMController settings

    Attributes
    ----------
    req : Record(cmd_layout)
        Stream of requests from LiteDRAMCrossbar
    refresh_req : Signal(), in
        Indicates that refresh needs to be done, connects to Refresher.cmd.valid
    refresh_gnt : Signal(), out
        Indicates that refresh permission has been granted, satisfying timings
    cmd : Endpoint(cmd_request_rw_layout)
        Stream of commands to the Multiplexer
    """
    def __init__(self, n, address_width, address_align, nranks, settings, timing_regs, precharge_time_sig):
        self.req = req = Record(cmd_layout(address_width))
        self.refresh_req = refresh_req = Signal()
        self.refresh_gnt = refresh_gnt = Signal()

        a  = settings.geom.addressbits
        ba = settings.geom.bankbits + log2_int(nranks)
        self.cmd = cmd = stream.Endpoint(cmd_request_rw_layout(a, ba))

        self.timer = Signal(max(timing_regs['tRP'].nbits, timing_regs['tRCD'].nbits) + 1)
        self.timer_done = Signal()

        # # #

        self.comb += self.timer_done.eq(self.timer == 0)
        self.sync += If(~self.timer_done, self.timer.eq(self.timer - 1))

        # # #

        auto_precharge = Signal()

        # Command buffer ---------------------------------------------------------------------------
        cmd_buffer_layout    = [("we", 1), ("addr", len(req.addr))]
        cmd_buffer_lookahead = stream.SyncFIFO(
            cmd_buffer_layout, settings.cmd_buffer_depth,
            buffered=settings.cmd_buffer_buffered,
            custom_fifo_cls=SimpleSyncFIFO
        )
        cmd_buffer = stream.Buffer(cmd_buffer_layout)       # 1 depth buffer to sync row_hit
        self.submodules += cmd_buffer_lookahead, cmd_buffer
        self.comb += [
            req.connect(cmd_buffer_lookahead.sink, keep={"valid", "ready", "we", "addr"}),
            cmd_buffer_lookahead.source.connect(cmd_buffer.sink),
            cmd_buffer.source.ready.eq(req.wdata_ready | req.rdata_valid),
            req.lock.eq(cmd_buffer_lookahead.source.valid | cmd_buffer.source.valid),
        ]

        slicer = _AddressSlicer(settings.geom.colbits, address_align)

        # Row tracking -----------------------------------------------------------------------------
        row        = Signal(settings.geom.rowbits)
        row_opened = Signal()
        row_hit    = Signal()
        row_open   = Signal()
        row_close  = Signal()

        row_hit_reeval = Signal()

        self.sync += [
            If(cmd_buffer.sink.ready & cmd_buffer.sink.valid,
                row_hit.eq(row == slicer.row(cmd_buffer_lookahead.source.addr))
            ),
            If(row_hit_reeval,
                row_hit.eq(1),
            ),
        ]
        self.sync += \
            If(row_close,
                row_opened.eq(0)
            ).Elif(row_open,
                row_opened.eq(1),
                row.eq(slicer.row(cmd_buffer.source.addr))
            )

        # Address generation -----------------------------------------------------------------------
        row_col_n_addr_sel = Signal()
        pre_n_addr_sel = Signal()
        pre_sig = Signal(12)
        if settings.phy.memtype != "DDR5":
            self.comb += [pre_sig.eq((auto_precharge << 10))]
        else:
            self.comb += [pre_sig.eq((~auto_precharge) << 11)]
        self.comb += [
            cmd.ba.eq(n),
            If(row_col_n_addr_sel,
                cmd.a.eq(slicer.row(cmd_buffer.source.addr))
            ).Elif(pre_n_addr_sel,
                cmd.a.eq(0),
            ).Else(
                cmd.a.eq(pre_sig | slicer.col(cmd_buffer.source.addr))
            )
        ]

        # tWTP (write-to-precharge) controller -----------------------------------------------------
        self.submodules.twtpcon = twtpcon = tXXDController(precharge_time_sig)
        self.comb += twtpcon.valid.eq(cmd.valid & cmd.ready & cmd.is_write)

        # tRC (activate-activate) controller -------------------------------------------------------
        self.submodules.trccon = trccon = tXXDController(timing_regs['tRC'])
        self.comb += trccon.valid.eq(cmd.valid & cmd.ready & row_open)

        # tRAS (activate-precharge) controller -----------------------------------------------------
        self.submodules.trascon = trascon = tXXDController(timing_regs['tRAS'])
        self.comb += trascon.valid.eq(cmd.valid & cmd.ready & row_open)

        if settings.phy.memtype == "DDR5":
            self.submodules.tccd = tccd = tXXDController(timing_regs['tCCD'])
            self.comb += tccd.valid.eq(cmd.valid & cmd.ready & cmd.is_read)
            self.submodules.tccdwr = tccdwr = tXXDController(timing_regs['tCCD_WR'])
            self.comb += tccdwr.valid.eq(cmd.valid & cmd.ready & cmd.is_write)

            R2W_delay = Signal(4)
            self.comb += R2W_delay.eq(int((14 + 8 + settings.phy.nphases - 1)/ settings.phy.nphases))
            self.submodules.trtw = trtw = tXXDController(R2W_delay)
            self.comb += trtw.valid.eq(cmd.valid & cmd.ready & cmd.is_read)

            W2R_delay = Signal(len(timing_regs['tWR']))
            self.sync += W2R_delay.eq(timing_regs['tWR'] - timing_regs["tRTP"])
            self.submodules.twtr = twtr = tXXDController(W2R_delay)
            self.comb += twtr.valid.eq(cmd.valid & cmd.ready & cmd.is_write)

        # Auto Precharge generation ----------------------------------------------------------------
        # generate auto precharge when current and next cmds are to different rows
        if settings.with_auto_precharge:
            self.comb += \
                If(cmd_buffer_lookahead.source.valid & cmd_buffer.source.valid,
                    If(slicer.row(cmd_buffer_lookahead.source.addr) !=
                       slicer.row(cmd_buffer.source.addr),
                        auto_precharge.eq(row_close == 0)
                    )
                )

        # Control and command generation FSM -------------------------------------------------------
        # Note: tRRD, tFAW, tCCD, tWTR timings are enforced by the multiplexer
        def ddr5_write_next_state():
            if settings.phy.memtype != "DDR5":
                return []
            write_after_write = Signal()
            self.comb += write_after_write.eq(
                cmd_buffer_lookahead.source.valid & cmd_buffer_lookahead.source.we)

            return [If(cmd.ready & write_after_write,
                        NextState("TW2W"),
                    ).Elif(cmd.ready,
                        NextState("TW2R")
                    )]

        def ddr5_read_next_state():
            if settings.phy.memtype != "DDR5":
                return []
            read_after_read = Signal()
            self.comb += read_after_read.eq(
                cmd_buffer_lookahead.source.valid & ~cmd_buffer_lookahead.source.we)

            return [If(cmd.ready & read_after_read,
                        NextState("TR2R"),
                    ).Elif(cmd.ready,
                        NextState("TR2W")
                    )]

        self.last_addr = CSRStatus(size=len(cmd_buffer_lookahead.source.addr),
                                   name=f"last_addr_{n}");
        self.last_active_row = CSRStatus(size=len(cmd.a),
                                         name=f"last_active_row_{n}");
        self.sync += [
            If(cmd_buffer.source.valid & cmd_buffer.source.ready,
                self.last_addr.status.eq(cmd_buffer.source.addr)
            ),
            If(cmd.valid & cmd.ready & row_open,
                self.last_active_row.status.eq(cmd.a)
            )
        ]
        self.submodules.fsm = fsm = FSM()
        fsm.act("REGULAR",
            If(refresh_req,
                NextState("REFRESH")
            ).Elif(cmd_buffer.source.valid & row_opened & row_hit,
                cmd.valid.eq(1),
                If(cmd_buffer.source.we,
                    req.wdata_ready.eq(cmd.ready),
                    cmd.is_write.eq(1),
                    cmd.we.eq(1),
                    *(ddr5_write_next_state())
                ).Else(
                    req.rdata_valid.eq(cmd.ready),
                    cmd.is_read.eq(1),
                    *(ddr5_read_next_state())
                ),
                cmd.cas.eq(1),
                If(cmd.ready & auto_precharge,
                   NextState("AUTOPRECHARGE")
                )
            ).Elif(cmd_buffer.source.valid & row_opened,
                NextState("PRECHARGE")
            ).Elif(cmd_buffer.source.valid,
                NextState("ACTIVATE")
            )
        )
        fsm.act("PRECHARGE",
            # Note: we are presenting the column address, A10 is always low
            If(twtpcon.ready & trascon.ready,
                cmd.valid.eq(1),
                If(cmd.ready,
                    NextValue(self.timer, timing_regs['tRP'] - 1),
                    NextState("TRP")
                ),
                pre_n_addr_sel.eq(1),
                cmd.ras.eq(1),
                cmd.we.eq(1),
                cmd.is_cmd.eq(1)
            ),
            row_close.eq(1)
        )
        fsm.act("AUTOPRECHARGE",
            If(twtpcon.ready & trascon.ready,
                NextValue(self.timer, timing_regs['tRP'] - 1),
                NextState("TRP")
            ),
            row_close.eq(1)
        )
        fsm.act("TRP",
            If(self.timer_done,
                NextState("ACTIVATE")
            )
        )
        fsm.act("ACTIVATE",
            row_hit_reeval.eq(1),
            If(trccon.ready,
                row_col_n_addr_sel.eq(1),
                row_open.eq(1),
                cmd.valid.eq(1),
                cmd.is_cmd.eq(1),
                If(cmd.ready,
                    NextValue(self.timer, timing_regs['tRCD'] - 1),
                    NextState("TRCD")
                ),
                cmd.ras.eq(1)
            )
        )
        fsm.act("TRCD",
            If(self.timer_done,
                NextState("REGULAR")
            )
        )
        fsm.act("REFRESH",
            If(twtpcon.ready,
                refresh_gnt.eq(1),
            ),
            row_close.eq(1),
            cmd.is_cmd.eq(1),
            If(~refresh_req,
                NextState("REGULAR")
            )
        )
        if settings.phy.memtype == "DDR5":
            fsm.act("TR2R",
                If(tccd.ready,
                    NextState("REGULAR"),
                ),
            )
            fsm.act("TW2W",
                If(tccdwr.ready,
                    NextState("REGULAR"),
                ),
            )
            fsm.act("TR2W",
                If(trtw.ready,
                    NextState("REGULAR"),
                ),
            )
            fsm.act("TW2R",
                If(twtr.ready,
                    NextState("REGULAR"),
                ),
            )
