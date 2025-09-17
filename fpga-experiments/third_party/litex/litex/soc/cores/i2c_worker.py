#
# This file is part of LiteX.
#
# Copyright (c) 2024 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import math
from dataclasses import KW_ONLY, dataclass
from enum import IntEnum

import param
from migen import FSM, Cat, If, Module, NextState, NextValue, Signal
from migen.genlib import fifo

from litex.soc.interconnect.csr import CSR, AutoCSR, CSRField, CSRStatus, CSRStorage


class I2CState(IntEnum):
    IDLE = 0
    RUN_I2C = 1
    START_FROM_ACK = 2
    START_FROM_NACK = 3
    START = 4
    DATA_BIT = 5
    DATA = 6
    STOP_FROM_NACK = 7
    STOP = 8
    ABORT = 9
    CLR_FIFO = 10

    @classmethod
    def encode(self):
        return list(map(lambda c: c.value, self))

    @classmethod
    def __len__(self):
        return 11


@dataclass
class I2CQueueEntry(param.Parameterized):
    """
    Queue entries have a following format:

    |20           |19  |18  |17        |16   |15|14|13|12|11|10|9|8     |7|6|5|4|3|2|1|0|
    |Abort on NACK|Idle|Stop|Data State|Start|Reserved           |(N)ACK|Data           |
    """
    _: KW_ONLY
    data: int = param.Integer(0, bounds=(0, 2**8 - 1))
    ack: int = param.Integer(0, bounds=(0, 1))
    s_start: int = param.Integer(0, bounds=(0, 1))
    s_data: int = param.Integer(0, bounds=(0, 1))
    s_stop: int = param.Integer(0, bounds=(0, 1))
    s_idle: int = param.Integer(0, bounds=(0, 1))
    abort_on_nack: int = param.Integer(0, bounds=(0, 1))

    @property
    def width(self):
        return 21

    @property
    def rsvd(self):
        return 0

    @property
    def fields_struct(self):
        return {
            "data": (0, 8),
            "ack": (8, 1),
            "rsvd": (9, 7),
            "s_start": (16, 1),
            "s_data": (17, 1),
            "s_stop": (18, 1),
            "s_idle": (19, 1),
            "abort_on_nack": (20, 1)
        }

    def field_offset(self, field):
        return self.fields_struct[field][0]

    def field_length(self, field):
        return self.fields_struct[field][1]

    def pack(self):
        """Pack the `I2CQueueEntry` dataclass into the I2CWorker's FIFO entry
        internal representation.
        """
        ret = 0
        fields = self.fields_struct.keys()
        for f in fields:
            offset, length = self.fields_struct[f]
            ret |= (getattr(self, f) & (2**length - 1)) << offset
        return ret

    def from_int(self, value):
        fields = self.fields_struct.keys()
        for f in fields:
            if f == "rsvd":
                continue
            offset, length = self.fields_struct[f]
            setattr(self, f, (value >> offset) & (2**length - 1))
        return self


class I2CWorker(Module, AutoCSR):
    """Simple I2C Master worker.

    I2C worker operates by sending data from the write queue and collecting responses
    in the read queue.

    Queue entries format is defined by `I2CQueueEntry`.

    If the data or ACK/NACK bits are set to 1, the worker will not drive the SDA bus,
    allowing the device to set correct values. This simplifies the implementation,
    as read/write operations are always done through the write fifo. It also
    allows for I2C SDA loopback.

    Supported features:
        * Clock stretching
        * Start and stop
        * Repeated start

    Known limitations:
        * Unsupported arbitration
    """
    def __init__(self, sys_freq, bus_freq, fifo_depth=128):
        # Get the number of cycles for low/high periods
        ratio = math.ceil(math.ceil(sys_freq/bus_freq)/4)
        self._start = CSR()
        self._ctrl = CSRStorage(fields=[
            CSRField("clr_fifos", size=1, offset=0),
            CSRField("reset_fsm", size=1, offset=8)],
            name="i2c_ctrl")
        self._state = CSRStatus(fields=[
            CSRField("ready", size=1, offset=0),
            CSRField("fsm_state", size=8, offset=8)],
            name="i2c_state")
        self._fifo = CSR(size=I2CQueueEntry().width, name="fifos_access_port")
        self._fifo_w = CSRStatus(fields=[
            CSRField("fifo_depth", size=8, offset=0, reset=fifo_depth),
            CSRField("fifo_entries", size=8, offset=8)],
            name="write_fifo_state")
        self._fifo_r = CSRStatus(fields=[
            CSRField("fifo_depth", size=8, offset=0, reset=fifo_depth),
            CSRField("fifo_entries", size=8, offset=8)],
            name="read_fifo_state")

        self.scl_o = scl_o = Signal()
        self.scl_oe = scl_oe = Signal()
        self.scl_i = scl_i = Signal()
        self.sda_o = sda_o = Signal()
        self.sda_oe = sda_oe = Signal()
        self.sda_i = sda_i = Signal()

        # Req FIFO
        write_fifo = fifo.SyncFIFOBuffered(
            width=len(self._fifo.r),
            depth=fifo_depth
        )
        # Resp FIFO
        read_fifo = fifo.SyncFIFOBuffered(
            width=len(self._fifo.w),
            depth=fifo_depth
        )
        self.submodules += [write_fifo, read_fifo]
        # Force FIFO clear
        _clr = Signal()

        # Timer
        timer = Signal(max=ratio, reset=0)
        timer_ready = Signal()
        timer_start = Signal()
        timer_strb = Signal()
        timer_done = Signal()

        self.sync += [
            timer_done.eq(0),
            If(timer_start,
                timer_ready.eq(0),
                timer.eq(ratio-1),
            ).Elif(~timer_ready,
                timer.eq(timer - 1),
            ),
            If(timer == 0,
                timer_ready.eq(1)
            ),
            timer_strb.eq(0),
            If(timer == 0 & ~timer_ready,
                timer_strb.eq(1)
            )
        ]

        # FIFO control and state
        _next_w_entry = Signal()

        self.comb += [
            self._fifo.w.eq(read_fifo.dout),
            read_fifo.re.eq(self._fifo.we | _clr),
            write_fifo.din.eq(self._fifo.r),
            write_fifo.we.eq(self._fifo.re),
            write_fifo.re.eq(_next_w_entry | _clr),
            self._fifo_w.fields.fifo_depth.eq(fifo_depth),
            self._fifo_r.fields.fifo_depth.eq(fifo_depth),
            self._fifo_w.fields.fifo_entries.eq(write_fifo.level),
            self._fifo_r.fields.fifo_entries.eq(read_fifo.level),
        ]

        # Sampler
        _scl_sample = Signal()
        _sda_sample = Signal()
        self.sync += [
            If(timer_strb,
                _scl_sample.eq(scl_i),
                _sda_sample.eq(sda_i),
            )
        ]

        # Worker FSM
        _recv = Signal(9)
        _send = Signal(9)

        # Worker's flags
        _s_start = Signal()
        _s_data = Signal()
        _s_stop = Signal()
        _s_idle = Signal()
        _s_abort_on_nack = Signal()

        self.comb += [
            _send.eq(Cat(write_fifo.dout[8], write_fifo.dout[:8])),
            read_fifo.din.eq(Cat(_recv[1:9], _recv[0])),
            _s_start.eq(write_fifo.dout[16]),
            _s_data.eq(write_fifo.dout[17]),
            _s_stop.eq(write_fifo.dout[18]),
            _s_idle.eq(write_fifo.dout[19]),
            _s_abort_on_nack.eq(write_fifo.dout[20]),
        ]
        # Bit set: 0        | 1
        # Context: Free bus | NACK
        _ctx = Signal(2)
        _state_ctx = Signal(4)

        def fsm_body_with_reset(*body):
            if not isinstance(body, list):
                body = [body]
            return [If(self._ctrl.fields.reset_fsm,
               NextState(I2CState.IDLE),
            ).Else(*body)]

        fsm = FSM(reset_state=I2CState.IDLE)
        self.submodules += fsm
        fsm.act(I2CState.IDLE,
            self._state.fields.ready.eq(1),
            NextValue(sda_o, 1),
            NextValue(sda_oe, 0),
            NextValue(scl_o, 1),
            NextValue(scl_oe, 0),
            NextValue(_ctx, 1),
            If(self._start.re & self._ctrl.fields.clr_fifos,
                NextValue(_clr, 1),
                NextState(I2CState.CLR_FIFO),
            ).Elif(self._start.re,
                NextValue(_state_ctx, 0),
                NextState(I2CState.RUN_I2C),
            )
        )
        fsm.act(I2CState.RUN_I2C,
            *fsm_body_with_reset(
                If(write_fifo.readable & read_fifo.writable,
                    If(_s_start & _ctx[0],
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.START),
                    ).Elif(_s_start & _ctx[1],
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.START_FROM_NACK),
                    ).Elif(_s_start,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.START_FROM_ACK),
                    ).Elif(_s_data,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.DATA),
                    ).Elif(_s_stop & _ctx[1],
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.STOP_FROM_NACK)
                    ).Elif(_s_stop,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.STOP)
                    ).Elif(_s_idle,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.IDLE)
                    ).Else(
                        # Empty entry
                        _next_w_entry.eq(1)
                    )
                )
            )
        )
        fsm.act(I2CState.START_FROM_ACK,
            *fsm_body_with_reset(
                If((_state_ctx == 0) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 1),
                ).Elif((_state_ctx) == 1,
                    If(timer_ready & ~timer_strb,
                        timer_start.eq(1),
                        If(_sda_sample,
                            NextValue(_state_ctx, 2),
                        )
                    )
                ).Elif((_state_ctx == 2) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 0),
                    NextState(I2CState.START_FROM_NACK),
                ),
                NextValue(sda_oe, 0),
                NextValue(sda_o, 1),
                NextValue(scl_oe, 1),
                NextValue(scl_o, 0),
            )
        )
        fsm.act(I2CState.START_FROM_NACK,
            *fsm_body_with_reset(
                If((_state_ctx == 0) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 1),
                ).Elif((_state_ctx == 1),
                    If(timer_ready & ~timer_strb,
                        timer_start.eq(1),
                        If(_scl_sample,
                            NextValue(_state_ctx, 2),
                        )
                    )
                ).Elif((_state_ctx == 2) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 0),
                    NextState(I2CState.START),
                ),
                NextValue(sda_oe, 0),
                NextValue(sda_o, 1),
                NextValue(scl_oe, 0),
                NextValue(scl_o, 1),
            )
        )
        fsm.act(I2CState.START,
            *fsm_body_with_reset(
                If((_state_ctx == 0) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 1),
                ).Elif((_state_ctx == 1) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 2),
                ).Elif((_state_ctx == 2) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 3),
                ).Elif((_state_ctx == 3) & timer_ready,
                    If(_s_data,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.DATA),
                    ).Elif(_s_stop,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.STOP),
                    ).Else(
                        _next_w_entry.eq(1),
                        NextState(I2CState.RUN_I2C),
                    )
                ),
                If((_state_ctx == 3),
                    NextValue(scl_oe, 1),
                    NextValue(scl_o, 0),
                    NextValue(sda_oe, 1),
                    NextValue(sda_o, 0),
                ).Else(
                    NextValue(sda_oe, 1),
                    NextValue(sda_o, 0),
                )
            )
        )
        _bit_access = Signal(4)
        _bit_ctx = Signal(3)
        fsm.act(I2CState.DATA_BIT,
            *fsm_body_with_reset(
                If((_bit_ctx == 0) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_bit_ctx, 1),
                ).Elif((_bit_ctx == 1) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_bit_ctx, 2),
                ).Elif((_bit_ctx == 2),
                    If(timer_ready & ~timer_strb,
                        timer_start.eq(1),
                        If(_scl_sample == 1,
                            NextValue(_recv.part(_bit_access, 1), _sda_sample),
                            NextValue(_bit_ctx, 3),
                        )
                    )
                ).Elif((_bit_ctx == 3) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_bit_ctx, 4),
                ).Elif((_bit_ctx == 4) & timer_ready,
                    NextValue(_state_ctx, _state_ctx + 1),
                    NextState(I2CState.DATA)
                ),
                If(_bit_ctx == 0,
                    NextValue(scl_oe, 1),
                    NextValue(scl_o, 0),
                ).Elif(_bit_ctx == 1,
                    NextValue(scl_oe, 1),
                    NextValue(scl_o, 0),
                ).Elif(_bit_ctx == 2,
                    NextValue(scl_oe, 0),
                    NextValue(scl_o, 1),
                ).Elif(_bit_ctx == 3,
                    NextValue(scl_oe, 0),
                    NextValue(scl_o, 1),
                ).Elif(_bit_ctx == 4,
                    NextValue(scl_oe, 1),
                    NextValue(scl_o, 0),
                ),
                NextValue(sda_oe, ~_send.part(_bit_access, 1)),
                NextValue(sda_o, _send.part(_bit_access, 1)),
            )
        )
        fsm.act(I2CState.DATA,
            *fsm_body_with_reset(
                [
                    If((_state_ctx == i),
                       NextValue(_bit_access, 8 - i),
                       NextValue(_bit_ctx, 0),
                       NextState(I2CState.DATA_BIT)
                       ) for i in range(9)
                ] + [
                 If((_state_ctx == 9),
                    read_fifo.we.eq(1),
                    If(_recv[0],
                        NextValue(_ctx, 2)
                    ).Else(
                        NextValue(_ctx, 0),
                    ),
                    If(_s_abort_on_nack & _recv[0],
                        NextState(I2CState.ABORT),
                    ).Elif(_s_stop,
                        NextValue(_state_ctx, 0),
                        If(_recv[0],
                            NextValue(_state_ctx, 0),
                            NextState(I2CState.STOP_FROM_NACK),
                        ).Else(
                            NextValue(_state_ctx, 0),
                            NextState(I2CState.STOP),
                        )
                    ).Else(
                        _next_w_entry.eq(1),
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.RUN_I2C),
                    ),
                ),
                ]
            )
        )
        fsm.act(I2CState.STOP_FROM_NACK,
            *fsm_body_with_reset(
                If((_state_ctx == 0) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 1),
                ).Elif((_state_ctx == 1) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 2),
                ).Elif((_state_ctx == 2) & timer_ready,
                    NextValue(_state_ctx, 0),
                    NextState(I2CState.STOP)
                ),
                If((_state_ctx == 0) | (_state_ctx == 1),
                    NextValue(scl_oe, 1),
                    NextValue(scl_o, 0),
                ).Else(
                    NextValue(scl_oe, 1),
                    NextValue(scl_o, 0),
                    NextValue(sda_oe, 1),
                    NextValue(sda_o, 0),
                )
            )
        )
        fsm.act(I2CState.STOP,
            *fsm_body_with_reset(
                If((_state_ctx == 0) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 1),
                ).Elif((_state_ctx == 1) & timer_ready,
                    If(timer_ready & ~timer_strb,
                        timer_start.eq(1),
                        If(_scl_sample,
                            NextValue(_state_ctx, 2),
                        )
                    )
                ).Elif((_state_ctx == 2) & timer_ready,
                    timer_start.eq(1),
                    NextValue(_state_ctx, 3),
                ).Elif((_state_ctx == 3) & timer_ready,
                    If(timer_ready & ~timer_strb,
                        timer_start.eq(1),
                        If(_sda_sample,
                            NextValue(_state_ctx, 4),
                        )
                    )
                ).Elif((_state_ctx == 4) & timer_ready,
                    _next_w_entry.eq(1),
                    If(_s_idle,
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.IDLE),
                    ).Else(
                        NextValue(_ctx, 1),
                        NextValue(_state_ctx, 0),
                        NextState(I2CState.RUN_I2C),
                    )
                ),
                If((_state_ctx == 0) | (_state_ctx == 1) | (_state_ctx == 2),
                    NextValue(scl_oe, 0),
                    NextValue(scl_o, 0),
                    NextValue(sda_oe, 1),
                    NextValue(sda_o, 0),
                ).Else(
                    NextValue(scl_oe, 0),
                    NextValue(scl_o, 0),
                    NextValue(sda_oe, 0),
                    NextValue(sda_o, 0),
                )
            )
        )
        fsm.act(I2CState.ABORT,
            self._state.fields.ready.eq(0),
            *fsm_body_with_reset()
        )
        fsm.act(I2CState.CLR_FIFO,
            self._state.fields.ready.eq(0),
            If(~read_fifo.readable & ~write_fifo.readable,
               NextValue(_clr, 0),
               NextState(I2CState.IDLE)
            )
        )
        fsm.finalize()
        self.comb += self._state.fields.fsm_state.eq(fsm.state)
