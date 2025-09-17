#
# This file is part of LiteX.
#
# Copyright (c) 2019 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2024 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import Record, run_simulation

from litex.gen.sim import passive
from litex.soc.cores.bitbang import I2CMaster, SPIMaster
from litex.soc.cores.i2c_worker import I2CQueueEntry, I2CState


@passive
def loopback(pads):
    while True:
        if (yield pads.scl.oe):
            yield pads.scl.i.eq(pads.scl.o)
        else:
            yield pads.scl.i.eq(1)
        if (yield pads.sda.oe):
            yield pads.sda.i.eq(pads.sda.o)
        else:
            yield pads.sda.i.eq(1)
        yield


def get_i2c_pads():
    return Record([("scl", [("o", 1), ("oe", 1), ("i", 1)]),
                   ("sda", [("o", 1), ("oe", 1), ("i", 1)])])


def i2c_master_output_bitbang(val):
    scl_o = 0
    scl_oe = (val ^ 1) & 1
    sda_o = 0
    sda_oe = ((val >> 1) & ~(val >> 2)) & 1
    return (scl_o, scl_oe, sda_o, sda_oe)


def generate_i2c_test_data(length, byte_subset=[0x55, 0xAA, 0xFF, 0x00]):
    sub_len = len(byte_subset)
    return [(byte_subset[i % sub_len], i & 1) for i in range(length)]


class TestBitBangI2C(unittest.TestCase):

    def test_i2c_master_syntax(self):
        i2c_master = I2CMaster()
        self.assertEqual(hasattr(i2c_master, "pads"), 1)
        i2c_master = I2CMaster(Record(I2CMaster.pads_layout))

    def test_i2c_master(self):
        def generator(i2c):
            yield
            yield i2c.pads.sda.i.eq(1)
            yield
            self.assertEqual((yield i2c._r.fields.sda), 1)
            yield i2c.pads.sda.i.eq(0)
            yield
            self.assertEqual((yield i2c._r.fields.sda), 0)
            for i in range(8):
                yield from i2c._w.write(i)
                scl_o, scl_oe, sda_o, sda_oe = i2c_master_output_bitbang(i)
                self.assertEqual((yield i2c.pads.scl.o), scl_o)
                self.assertEqual((yield i2c.pads.scl.oe), scl_oe)
                self.assertEqual((yield i2c.pads.sda.o), sda_o)
                self.assertEqual((yield i2c.pads.sda.oe), sda_oe)

        i2c_master = I2CMaster(pads=get_i2c_pads(), sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, [generator(i2c_master)])
        self.assertEqual(hasattr(i2c_master, "pads"), 1)


class TestI2C(unittest.TestCase):

    @passive
    def check_start(self, pads):
        self.detect_start = False
        self.start_seen = False
        data_transition = False
        yield
        old_scl = yield pads.scl.i
        old_sda = yield pads.sda.i
        while not self.detect_start:
            old_scl = yield pads.scl.i
            old_sda = yield pads.sda.i
            yield
        while True:
            if old_sda != (yield pads.sda.i) and old_sda == 1:
                data_transition = True
                self.assertEqual(old_scl, (yield pads.scl.i))
                self.assertEqual(old_scl, 1)
            if data_transition and old_scl != (yield pads.scl.i):
                self.assertEqual(old_sda, (yield pads.sda.i))
                self.assertEqual(old_sda, 0)
                self.start_seen = True
            old_scl = yield pads.scl.i
            old_sda = yield pads.sda.i
            yield

    @passive
    def check_stop(self, pads):
        self.detect_stop = False
        self.stop_seen = False
        clk_transition = False
        yield
        old_scl = yield pads.scl.i
        old_sda = yield pads.sda.i
        while not self.detect_stop:
            old_scl = yield pads.scl.i
            old_sda = yield pads.sda.i
            yield
        while True:
            if old_scl != (yield pads.scl.i) and old_scl == 0:
                clk_transition = True
                self.assertEqual(old_sda, (yield pads.sda.i))
                self.assertEqual(old_sda, 0)
            if clk_transition and old_sda != (yield pads.sda.i):
                self.assertEqual(old_scl, (yield pads.scl.i))
                self.assertEqual(old_scl, 1)
                self.stop_seen = True
            old_scl = yield pads.scl.i
            old_sda = yield pads.sda.i
            yield

    @passive
    def check_data(self, pads, _bytes):
        yield
        old_scl = yield pads.scl.i
        for byte, nack in _bytes:
            for i in range(8):
                while not (old_scl == 0 and (yield pads.scl.i) == 1):
                    old_scl = yield pads.scl.i
                    yield
                old_scl = yield pads.scl.i
                bit = yield pads.sda.i
                self.assertEqual((byte >> (7 - i)) & 1, bit)
                yield
            while not (old_scl == 0 and (yield pads.scl.i) == 1):
                old_scl = yield pads.scl.i
                yield
            old_scl = yield pads.scl.i
            bit = yield pads.sda.i
            self.assertEqual(nack, bit)
            yield

    @passive
    def send_data(self, pads, _bytes):
        yield
        old_scl = yield pads.scl.i
        for byte, nack in _bytes:
            for i in range(8):
                while not (old_scl == 1 and (yield pads.scl.i) == 0):
                    old_scl = yield pads.scl.i
                    yield
                old_scl = yield pads.scl.i
                yield pads.sda.i.eq((byte >> (7 - i)) & 1)
                yield
            while not (old_scl == 1 and (yield pads.scl.i) == 0):
                old_scl = yield pads.scl.i
                yield
            old_scl = yield pads.scl.i
            yield pads.sda.i.eq(nack)
            yield

    @passive
    def check_clk(self, pads):
        yield
        old_sda = yield pads.sda.i
        while True:
            if (yield pads.scl.i) == 1:
                self.assertEqual(old_sda, (yield pads.sda.i))
            old_sda = yield pads.sda.i
            yield

    @passive
    def clk_pullup(self, pads):
        while True:
            if (yield pads.scl.oe):
                yield pads.scl.i.eq(pads.scl.o)
            else:
                yield pads.scl.i.eq(1)
            yield

    def test_i2c_master_worker_dis(self):
        def generator(i2c):
            yield
            yield from i2c._sel.write(0)
            yield i2c.pads.sda.i.eq(1)
            yield
            self.assertEqual((yield i2c._r.fields.sda), 1)
            yield i2c.pads.sda.i.eq(0)
            yield
            self.assertEqual((yield i2c._r.fields.sda), 0)
            for i in range(8):
                yield from i2c._w.write(i)
                scl_o, scl_oe, sda_o, sda_oe = i2c_master_output_bitbang(i)
                self.assertEqual((yield i2c.pads.scl.o), scl_o)
                self.assertEqual((yield i2c.pads.scl.oe), scl_oe)
                self.assertEqual((yield i2c.pads.sda.o), sda_o)
                self.assertEqual((yield i2c.pads.sda.oe), sda_oe)

        i2c_master = I2CMaster(pads=get_i2c_pads(), sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, [generator(i2c_master)])

    def test_i2c_master_worker_en(self):
        def generator(i2c):
            yield
            yield from i2c._sel.write(1)
            yield i2c.pads.sda.i.eq(1)
            yield
            self.assertEqual((yield i2c._r.fields.sda), 1)
            yield i2c.pads.sda.i.eq(0)
            yield
            self.assertEqual((yield i2c._r.fields.sda), 0)
            for i in range(8):
                yield from i2c._w.write(i)
                self.assertEqual((yield i2c.pads.scl.o), 0)
                self.assertEqual((yield i2c.pads.scl.oe), 0)
                self.assertEqual((yield i2c.pads.sda.o), 0)
                self.assertEqual((yield i2c.pads.sda.oe), 0)

        i2c_master = I2CMaster(pads=get_i2c_pads(), sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, generator(i2c_master))

    def test_i2c_master_worker_write_fifo_fill(self):
        def generator(i2c):
            yield
            yield from i2c._sel.write(1)
            fifo_depth = (yield i2c.i2c_worker._fifo_w.fields.fifo_depth)
            self.assertEqual(fifo_depth, 128)
            self.assertEqual((yield i2c.i2c_worker._fifo_w.fields.fifo_entries), 0)
            for i in range(fifo_depth):
                yield from i2c.i2c_worker._fifo.write(I2CQueueEntry().pack())
                yield
                self.assertEqual((yield i2c.i2c_worker._fifo_w.fields.fifo_depth), 128)
                self.assertEqual((yield i2c.i2c_worker._fifo_w.fields.fifo_entries), i+1)

        i2c_master = I2CMaster(pads=get_i2c_pads(), sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, generator(i2c_master))

    def test_i2c_master_worker_write_fifo_clr(self):
        def generator(i2c):
            yield
            yield from i2c._sel.write(1)
            fifo_depth = (yield i2c.i2c_worker._fifo_w.fields.fifo_depth)
            for i in range(fifo_depth):
                yield from i2c.i2c_worker._fifo.write(I2CQueueEntry().pack())
            while ((yield i2c.i2c_worker._fifo_w.fields.fifo_entries) != 128):
                yield
            yield i2c.i2c_worker._ctrl.fields.clr_fifos.eq(1)
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            while not ((yield i2c.i2c_worker._state.fields.ready)):
                yield
            self.assertEqual((yield i2c.i2c_worker._fifo_w.fields.fifo_entries), 0)

        i2c_master = I2CMaster(pads=get_i2c_pads(), sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, generator(i2c_master))

    def test_i2c_master_worker_state_rst(self):
        def generator(i2c):
            yield
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            yield i2c.i2c_worker._ctrl.fields.reset_fsm.eq(1)
            yield
            yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.IDLE)
            yield i2c.i2c_worker._ctrl.fields.reset_fsm.eq(0)

        i2c_master = I2CMaster(pads=get_i2c_pads(), sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, generator(i2c_master))

    def test_i2c_master_worker_start(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.start_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(i2c_master, [generator(i2c_master), loopback(pads), self.check_start(pads)])

    def test_i2c_master_worker_start_stop(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1, s_stop=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.start_seen, True)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_start_then_stop(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_stop=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.start_seen, True)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_start_stop_end(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1, s_stop=1, s_idle=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.IDLE)
            self.assertEqual(self.start_seen, True)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_start_stop_then_end(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1, s_stop=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_idle=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.IDLE)
            self.assertEqual(self.start_seen, True)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_start_then_stop_end(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_stop=1, s_idle=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.IDLE)
            self.assertEqual(self.start_seen, True)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_start_then_stop_then_end(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_stop=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_idle=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.IDLE)
            self.assertEqual(self.start_seen, True)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_send_data(self):
        def generator(i2c, _bytes):
            yield from i2c._sel.write(1)
            for byte in _bytes:
                data, ack = byte
                yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(data=data, ack=ack, s_data=1).pack())
                yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            for _ in range(len(_bytes)):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                    yield
                for _ in range(9):
                    self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                        yield
                    self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                        yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
        bytes = [0x55, 0x55, 0x96, 0x96, 0x42, 0x42, 0xAA, 0xAA, 0xFF, 0xFF, 0x00, 0x00]
        data = generate_i2c_test_data(len(bytes), bytes)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master, data), loopback(pads),
             self.check_clk(pads), self.check_data(pads, data)],
        )

    def test_i2c_master_worker_recv_data(self):
        def generator(i2c, _bytes):
            yield from i2c._sel.write(1)
            for _ in range(len(_bytes)):
                yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(data=0xff, ack=1, s_data=1).pack())
                yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            for i in range(len(_bytes)):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                    yield
                for _ in range(9):
                    self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                        yield
                    self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                        yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_entries), len(_bytes))
            i = 0
            while (yield i2c.i2c_worker._fifo_r.fields.fifo_entries) > 0:
                data = yield from i2c.i2c_worker._fifo.read()
                byte, ack = _bytes[i]
                self.assertEqual(data, I2CQueueEntry(data=byte, ack=ack).pack())
                i += 1
                yield

        bytes = [0x55, 0x55, 0x96, 0x96, 0x42, 0x42, 0xAA, 0xAA, 0xFF, 0xFF, 0x00, 0x00]
        data = generate_i2c_test_data(len(bytes), bytes)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master, data), self.clk_pullup(pads),
             self.check_clk(pads), self.send_data(pads, data)],
        )

    def test_i2c_master_worker_read_fifo_fill(self):
        def generator(i2c, _bytes):
            yield from i2c._sel.write(1)
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_depth), 128)
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_entries), 0)
            for byte in _bytes:
                data, ack = byte
                yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(data=data, ack=ack, s_data=1).pack())
                yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            for _ in range(len(_bytes)):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                    yield
                for _ in range(9):
                    self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                        yield
                    self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                        yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_entries), len(_bytes))
            i = 0
            while (yield i2c.i2c_worker._fifo_r.fields.fifo_entries) > 0:
                data = yield from i2c.i2c_worker._fifo.read()
                byte, ack = _bytes[i]
                self.assertEqual(data, I2CQueueEntry(data=byte, ack=ack).pack())
                i += 1
                yield

        data = generate_i2c_test_data(128)
        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master, data), loopback(pads),
             self.check_clk(pads), self.check_data(pads, data)],
        )

    def test_i2c_master_worker_read_fifo_over_fill(self):
        @passive
        def fill(i2c, _bytes):
            i = 0
            while i < len(_bytes):
                data, ack = _bytes[i]
                if (yield i2c.i2c_worker._fifo_w.fields.fifo_entries) < 128:
                    yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(data=data, ack=ack, s_data=1).pack())
                    i += 1
                yield

        def generator(i2c):
            yield from i2c._sel.write(1)
            while (yield i2c.i2c_worker._fifo_w.fields.fifo_entries) < 8:
                yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            for _ in range(128):
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                    yield
                for _ in range(9):
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                        yield
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                        yield
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_entries), 128)
            self.assertEqual((yield i2c.i2c_worker._fifo_w.fields.fifo_entries), 4)

        data = generate_i2c_test_data(132)
        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), fill(i2c_master, data), loopback(pads)],
        )

    def test_i2c_master_worker_read_fifo_clr(self):
        @passive
        def fill(i2c, _bytes):
            for data, ack in _bytes:
                if (yield i2c.i2c_worker._fifo_w.fields.fifo_entries) < 128:
                    yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(data=data, ack=ack, s_data=1).pack())
                yield

        def generator(i2c):
            yield from i2c._sel.write(1)
            while (yield i2c.i2c_worker._fifo_w.fields.fifo_entries) < 8:
                yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            for i in range(128):
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                    yield
                for _ in range(9):
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                        yield
                    while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                        yield
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_entries), 128)
            self.assertEqual((yield i2c.i2c_worker._fifo_w.fields.fifo_entries), 0)
            yield i2c.i2c_worker._ctrl.fields.reset_fsm.eq(1)
            yield
            yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.IDLE)
            yield i2c.i2c_worker._ctrl.fields.reset_fsm.eq(0)
            yield i2c.i2c_worker._ctrl.fields.clr_fifos.eq(1)
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            while not ((yield i2c.i2c_worker._state.fields.ready)):
                yield
            self.assertEqual((yield i2c.i2c_worker._fifo_r.fields.fifo_entries), 0)

        data = generate_i2c_test_data(128)
        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), fill(i2c_master, data), loopback(pads)],
        )

    def test_i2c_master_worker_data_stop(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_data=1, s_stop=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            for _ in range(9):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_data_then_stop(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_data=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_stop=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            for _ in range(9):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_data_nack_then_stop(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(ack=1, s_data=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_stop=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            for _ in range(9):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
            self.detect_stop = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP_FROM_NACK)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP_FROM_NACK):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.STOP)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.STOP):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.stop_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_stop(pads)],
        )

    def test_i2c_master_worker_data_then_start(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_data=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            for _ in range(9):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START_FROM_ACK)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START_FROM_ACK):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START_FROM_NACK)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START_FROM_NACK):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.start_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads)],
        )

    def test_i2c_master_worker_data_nack_then_start(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(ack=1, s_data=1).pack())
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(s_start=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            for _ in range(9):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
            self.detect_start = True
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START_FROM_NACK)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START_FROM_NACK):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.START)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.START):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            self.assertEqual(self.start_seen, True)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads), self.check_start(pads)],
        )

    def test_i2c_master_worker_data_nack_abort(self):
        def generator(i2c):
            yield from i2c._sel.write(1)
            yield from i2c.i2c_worker._fifo.write(I2CQueueEntry(ack=1, s_data=1, abort_on_nack=1).pack())
            yield
            yield from i2c.i2c_worker._start.write(1)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.IDLE):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.RUN_I2C)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.RUN_I2C):
                yield
            for _ in range(9):
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                    yield
                self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA_BIT)
                while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA_BIT):
                    yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.DATA)
            while ((yield i2c.i2c_worker._state.fields.fsm_state) == I2CState.DATA):
                yield
            self.assertEqual((yield i2c.i2c_worker._state.fields.fsm_state), I2CState.ABORT)

        pads = get_i2c_pads()
        i2c_master = I2CMaster(pads=pads, sys_freq=100e6, bus_freq=400e3)
        run_simulation(
            i2c_master,
            [generator(i2c_master), loopback(pads)],
        )


class TestBitBangSPI(unittest.TestCase):
    def test_spi_master_syntax(self):
        spi_master = SPIMaster()
        self.assertEqual(hasattr(spi_master, "pads"), 1)
        spi_master = SPIMaster(Record(SPIMaster.pads_layout))
        self.assertEqual(hasattr(spi_master, "pads"), 1)
