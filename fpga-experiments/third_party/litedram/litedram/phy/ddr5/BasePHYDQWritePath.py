#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import or_
from functools import reduce

from migen.fhdl.structure import Signal, If, Cat, Case

from migen.fhdl.module import Module
from migen.genlib.fifo import SyncFIFO

from litedram.common import TappedDelayLine
from litedram.phy.ddr5.BasePHYPatternGenerators import DQOePattern

class BasePHYDQWritePath(Module):
    write_addjust = 0
    min_write_latency = None
    max_write_latency = None

    @classmethod
    def get_min_max_supported_latencies(cls, nphases, address_delay, buffer_delay,
            ca_cdc_min_max_delay, wr_cdc_min_max_delay):
        # Buffer incoming data + preamble buffer - address_delay - max CA CDC delay + min WDQ CDC delay + register output
        cls.min_write_latency = buffer_delay + nphases + nphases + 2 - 1 - address_delay - ca_cdc_min_max_delay[1].sys4x +\
             wr_cdc_min_max_delay[0].sys4x + nphases
        if cls.min_write_latency <  0:
            cls.write_addjust = -cls.min_write_latency
        # 64 (max CLW) + 1 (2N) + min CA CDC delay - max WDQ CDC delay
        cls.max_write_latency = 68 + 1 + ca_cdc_min_max_delay[1].sys4x - wr_cdc_min_max_delay[1].sys4x

        return (cls.min_write_latency, cls.max_write_latency, cls.write_addjust)

    def __init__(self, dfi, dfi_ctrl, out, dq_dqs_ratio, CSRs, default_write_latency=0, SyncFIFO_cls=SyncFIFO):
        nphases = len(dfi.phases)
        nphases_log = nphases.bit_length() - 1
        assert nphases > 1 and (nphases & (nphases-1)) == 0

        wrtap = (self.max_write_latency + self.write_addjust + nphases - 1) // nphases
        assert wrtap >= 0

        # Create a delay line of write commands coming from the DFI interface. This taps are used to
        # control DQ/DQS tristates.

        wrdata_en_comb = Signal(nphases)
        self.comb += wrdata_en_comb.eq(Cat([phase.wrdata_en for phase in dfi_ctrl.phases]))

        wrdata_en = TappedDelayLine(
            signal = wrdata_en_comb,
            ntaps  = wrtap + 2
        )
        self.submodules += wrdata_en

        assert default_write_latency >= self.min_write_latency or default_write_latency == 0, \
        f"default_write_latency={default_write_latency} is to small, min_write_latency={self.min_write_latency}"

        wr_dq_max_delay = self.max_write_latency + self.write_addjust + 2
        wr_reset_value = 0 if default_write_latency < self.min_write_latency else default_write_latency - self.min_write_latency

        wr_data_window   = Signal(nphases+2)
        wr_data_delay    = Signal(max=wr_dq_max_delay + 1, reset=wr_reset_value + 2)
        wr_data_index_n  = Signal(max=wr_dq_max_delay // nphases + 0)
        wr_data_index    = Signal(max=wr_dq_max_delay // nphases + 1)
        wr_data_index_p  = Signal(max=wr_dq_max_delay // nphases + 2)
        wr_data_index_2p = Signal(max=wr_dq_max_delay // nphases + 3)
        wr_data_offset   = Signal(max=nphases) if nphases > 1 else Signal(1, reset=0)

        self.sync += [
            If(CSRs['dly_sel'] & CSRs['ck_wddly_inc'] & \
               (wr_data_delay < wr_dq_max_delay),
                wr_data_delay.eq(wr_data_delay + 1),
            ).Elif(CSRs['dly_sel'] & CSRs['ck_wddly_rst'],
                wr_data_delay.eq(wr_reset_value + 2),
            ),
            CSRs['ck_wdly_dq'].eq(wr_data_delay),
        ]

        self.sync += [
            wr_data_index_n.eq(wr_data_delay[nphases_log:] - 1),
            wr_data_index.eq(wr_data_delay[nphases_log:]),
            wr_data_index_p.eq(wr_data_delay[nphases_log:] + 1),
            wr_data_index_2p.eq(wr_data_delay[nphases_log:] + 2),
            wr_data_offset.eq(wr_data_delay[:nphases_log]),
        ]

        wr_data_cases = {}
        for i in range(nphases):
            if 2+i <= nphases:
                wr_data_cases[i] = wr_data_window.eq(
                    Cat(wrdata_en.taps[wr_data_index_p][nphases-(2+i):],
                        wrdata_en.taps[wr_data_index][:nphases-i]))
            else:
                wr_data_cases[i] = wr_data_window.eq(
                        Cat(wrdata_en.taps[wr_data_index_2p][-1],
                            wrdata_en.taps[wr_data_index_p],
                            wrdata_en.taps[wr_data_index][1]))

        self.sync += [Case(wr_data_offset, wr_data_cases)]

        dq_oe        = Signal(2*nphases)
        dq_pattern   = DQOePattern(
            nphases   = nphases,
            wlevel_en = CSRs['wlevel_en'],
        )
        self.comb += dq_pattern.window.eq(wr_data_window)
        self.submodules += dq_pattern

        self.sync += [getattr(out, f'dq0_oe').eq(dq_pattern.oe)]

        # Write Data Path --------------------------------------------------------------------------
        wr_fifo = SyncFIFO_cls(width=dq_dqs_ratio*nphases*2, depth=wrtap, fwft=False)
        self.submodules += wr_fifo

        self.comb += [
            wr_fifo.din.eq(
                Cat(phase.wrdata for phase in dfi.phases)),
            If(wr_data_index != 0,
                wr_fifo.we.eq(reduce(or_, [phase.wrdata_en for phase in dfi_ctrl.phases])),
            ),
        ]

        wr_data             = Signal(2*nphases*dq_dqs_ratio)
        wr_fifo_data        = Signal(2*nphases*dq_dqs_ratio)
        wr_input_data       = Signal(2*nphases*dq_dqs_ratio)
        wr_register_data    = Signal(2*nphases*dq_dqs_ratio)
        wr_fifo_data_valid  = Signal()
        self.sync += wr_fifo_data_valid.eq(wr_fifo.re & wr_fifo.readable)
        self.sync += [wr_input_data.eq(Cat(
            [phase.wrdata for phase in dfi.phases])),
        ]
        self.sync += [
            If(wr_data_index != 0,
                wr_fifo.re.eq(reduce(or_, wrdata_en.taps[wr_data_index_n])),
            ),
        ]
        self.comb += [
            If(wr_data_index != 0,
                If(wr_fifo_data_valid,
                    wr_fifo_data.eq(wr_fifo.dout),
                ),
            ).Else(
                wr_fifo_data.eq(wr_input_data),
            ),
        ]

        wr_cases_comb = {0: [wr_data.eq(wr_fifo_data)]}
        wr_cases_sync = {0: [wr_register_data.eq(0)]}
        for i in range(1, nphases):
            wr_cases_comb[i] = [
                wr_data.eq(Cat(wr_register_data[:i*2*dq_dqs_ratio], wr_fifo_data[:(nphases-i)*2*dq_dqs_ratio])),
            ]
            wr_cases_sync[i] = [wr_register_data.eq(wr_fifo_data[(nphases-i)*2*dq_dqs_ratio:])]

        self.comb += [Case(wr_data_offset, wr_cases_comb)]
        self.sync += [Case(wr_data_offset, wr_cases_sync)]

        # DQ ----------------------------------------------------------------------------------------
        for bit in range(dq_dqs_ratio):
            _wrdata = [wr_data[i * dq_dqs_ratio + bit] for i in range(2*nphases)]
            self.sync += getattr(out, f'dq{bit}_o').eq(Cat(_wrdata))
