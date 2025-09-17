#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import or_
from functools import reduce

from migen.fhdl.structure import Signal, If, Cat, Replicate, Case
from migen.fhdl.module import Module
from migen.genlib.record import Record
from migen.genlib.fifo import SyncFIFO

from litedram.common import TappedDelayLine
from litedram.phy.ddr5.BasePHYPatternGenerators import DQSPattern

class BasePHYWritePathDQSInput(Record):
    @staticmethod
    def data_layout(nphases):
        base_layout = [
            ("wrdata_en", 1),
        ]
        return base_layout
    def __init__(self, nphases):
        layout = [(f"p{i}", self.data_layout(nphases)) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]


class BasePHYWritePathDQSOutput(Record):
    @staticmethod
    def data_layout(nphases):
        base_layout = [
            ("dqs_t_o", 2*nphases),
            ("dqs_c_o", 2*nphases),
            ("dqs_oe", 2*nphases),
        ]
        return base_layout
    def __init__(self, nphases):
        layout = self.data_layout(nphases)
        Record.__init__(self, layout)


class BasePHYDQSWritePathBuffer(Module):
    @classmethod
    def get_delay(cls, nphases):
        return nphases
    def __init__(self, src, target):
        for src_phase, target_phase in zip(src.phases, target.phases):
            for name, _ in src_phase.layout:
                self.sync += getattr(target_phase, name).eq(getattr(src_phase, name))


class BasePHYWritePathDQS(Module):
    write_addjust = 0
    min_write_latency = None
    max_write_latency = None

    @classmethod
    def get_min_max_supported_latencies(cls, nphases, address_delay, buffer_delay,
            ca_cdc_min_max_delay, wr_cdc_min_max_delay):
        # preamble buffer - address_delay - max CA CDC delay + min WDQ CDC delay + register output
        cls.min_write_latency = nphases + nphases + 2 - 1 - address_delay - ca_cdc_min_max_delay[1].sys4x +\
             wr_cdc_min_max_delay[0].sys4x + buffer_delay + nphases
        if cls.min_write_latency < 0:
            cls.write_addjust = -cls.min_write_latency
        # 64 (max CLW) + 1 (2N) + min CA CDC delay - max WDQ CDC delay
        cls.max_write_latency = 68 + 1 + ca_cdc_min_max_delay[1].sys4x - wr_cdc_min_max_delay[1].sys4x

        return (cls.min_write_latency, cls.write_addjust)


    def __init__(self, dfi, out, CSRs, default_write_latency=0, SyncFIFO_cls=SyncFIFO):
        nphases = len(dfi.phases)
        nphases_log = nphases.bit_length() - 1
        assert nphases > 1 and (nphases & (nphases-1)) == 0

        wrtap = (self.max_write_latency + self.write_addjust + nphases - 1) // nphases
        assert wrtap >= 0

        # Create a delay line of write commands coming from the DFI interface. This taps are used to
        # control DQ/DQS tristates.

        wrdata_en_comb = Signal(nphases)
        self.comb += wrdata_en_comb.eq(Cat([phase.wrdata_en for phase in dfi.phases]))

        wrdata_en = TappedDelayLine(
            signal = wrdata_en_comb,
            ntaps  = wrtap + 2
        )

        self.submodules += wrdata_en

        assert default_write_latency >= self.min_write_latency or default_write_latency == 0, \
        f"default_write_latency={default_write_latency} is to small, min_write_latency={self.min_write_latency}"

        wr_reset_value = 0 if default_write_latency < self.min_write_latency else default_write_latency - self.min_write_latency

        wr_dqs_max_delay = self.max_write_latency + self.write_addjust

        wr_window       = Signal(nphases + 4)
        wr_delay        = Signal(max=wr_dqs_max_delay + 1, reset=wr_reset_value)
        wr_index        = Signal(max=wr_dqs_max_delay // nphases + 1)
        wr_index_1p     = Signal(max=wr_dqs_max_delay // nphases + 2)
        wr_index_2p     = Signal(max=wr_dqs_max_delay // nphases + 3)
        wr_index_3p     = Signal(max=wr_dqs_max_delay // nphases + 4)
        wr_index_4p     = Signal(max=wr_dqs_max_delay // nphases + 5)
        wr_offset       = Signal(max=nphases) if nphases > 1 else Signal(1, reset=0)

        self.sync += [
            If(CSRs['dly_sel'] & CSRs['ck_wdly_inc'] & \
               (wr_delay < wr_dqs_max_delay),
                wr_delay.eq(wr_delay + 1),
            ).Elif(CSRs['dly_sel'] & CSRs['ck_wdly_rst'],
                wr_delay.eq(wr_reset_value),
            ),
            CSRs['ck_wdly_dqs'].eq(wr_delay),
        ]

        self.sync += [
            wr_index.eq(wr_delay[nphases_log:]),
            wr_index_1p.eq(wr_delay[nphases_log:] + 1),
            wr_index_2p.eq(wr_delay[nphases_log:] + 2),
            wr_index_3p.eq(wr_delay[nphases_log:] + 3),
            wr_index_4p.eq(wr_delay[nphases_log:] + 4),
            wr_offset.eq(wr_delay[:nphases_log]),
        ]

        wr_cases = {}
        if nphases > 1:
            for i in range(nphases):
                if 4+i <= nphases:
                    wr_cases[i] = wr_window.eq(
                        Cat(wrdata_en.taps[wr_index_1p][nphases-(4+i):],
                            wrdata_en.taps[wr_index][:nphases-i]
                    ))
                elif 4+i <= 2*nphases:
                    wr_cases[i] = wr_window.eq(
                        Cat(wrdata_en.taps[wr_index_2p][2*nphases-(4+i):],
                            wrdata_en.taps[wr_index_1p],
                            wrdata_en.taps[wr_index][:nphases-i]
                    ))
                else:
                    wr_cases[i] = wr_window.eq(
                        Cat(wrdata_en.taps[wr_index_3p][3*nphases-(4+i):],
                            wrdata_en.taps[wr_index_2p],
                            wrdata_en.taps[wr_index_1p],
                            wrdata_en.taps[wr_index][:nphases-i]
                    ))
        else:
            wr_cases[0] = wr_window.eq(
                Cat(wrdata_en.taps[wr_index_4p],
                    wrdata_en.taps[wr_index_3p],
                    wrdata_en.taps[wr_index_2p],
                    wrdata_en.taps[wr_index_1p],
                    wrdata_en.taps[wr_index]
                ))

        self.sync += [
            Case(wr_offset,
                wr_cases,
            )
        ]

        dqs_oe        = Signal(2*nphases)
        dqs_pattern   = DQSPattern(
            nphases   = nphases,
            wlevel_en = CSRs['wlevel_en'],
        )
        self.comb += dqs_pattern.window.eq(wr_window)
        self.submodules += dqs_pattern

        self.sync += [
            out.dqs_t_o.eq(dqs_pattern.o),
            out.dqs_c_o.eq(~dqs_pattern.o),
            out.dqs_oe.eq(dqs_pattern.oe),
        ]
