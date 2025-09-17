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

class BasePHYDMPath(Module):
    write_addjust = 0
    min_write_latency = None
    max_write_latency = None

    @classmethod
    def get_min_max_supported_latencies(cls, nphases, address_delay, buffer_delay,
            ca_cdc_min_max_delay, wr_cdc_min_max_delay):
        # Buffer incoming data + preamble buffer - address_delay - max CA CDC delay + min WDQ CDC delay
        cls.min_write_latency = nphases + 2 - 1 - address_delay - ca_cdc_min_max_delay[1].sys4x +\
             wr_cdc_min_max_delay[0].sys4x + buffer_delay
        if cls.min_write_latency <  0:
            cls.write_addjust = -cls.min_write_latency
        # 64 (max CLW) + 1 (2N) + min CA CDC delay - max WDQ CDC delay
        cls.max_write_latency = 68 + 1 + ca_cdc_min_max_delay[1].sys4x - wr_cdc_min_max_delay[1].sys4x

        return (cls.min_write_latency, cls.max_write_latency, cls.write_addjust)

    def __init__(self, dfi, dfi_ctrl, out, CSRs, default_write_latency=0, SyncFIFO_cls=SyncFIFO):
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

        wr_data_delay   = Signal(max=wr_dq_max_delay + 1, reset=wr_reset_value + 2)
        wr_data_index   = Signal(max=wr_dq_max_delay // nphases + 1)
        wr_data_offset  = Signal(max=nphases) if nphases > 1 else Signal(1, reset=0)

        self.sync += [
            If(CSRs['dly_sel'] & CSRs['ck_wddly_inc'] & \
               (wr_data_delay < wr_dq_max_delay),
                wr_data_delay.eq(wr_data_delay + 1),
            ).Elif(CSRs['dly_sel'] & CSRs['ck_wddly_rst'],
                wr_data_delay.eq(wr_reset_value + 2),
            ),
        ]

        self.comb += [
            wr_data_index.eq(wr_data_delay[nphases_log:]),
            wr_data_offset.eq(wr_data_delay[:nphases_log]),
        ]

        # Write Mask Path --------------------------------------------------------------------------
        wr_fifo = SyncFIFO_cls(width=nphases*2, depth=wrtap, fwft=False)
        self.submodules += wr_fifo

        self.comb += [
            wr_fifo.din.eq(Cat(phase.wrdata_mask for phase in dfi.phases)),
            If(wr_data_index > 0,
                wr_fifo.we.eq(reduce(or_, [phase.wrdata_en for phase in dfi_ctrl.phases])),
            ),
        ]

        wr_dm               = Signal(2*nphases)
        wr_fifo_dm          = Signal(2*nphases)
        wr_input_dm         = Signal(2*nphases)
        wr_register_dm      = Signal(2*nphases)
        wr_fifo_data_valid  = Signal()

        self.sync += wr_fifo_data_valid.eq(wr_fifo.re & wr_fifo.readable)
        self.sync += [
            wr_input_dm.eq(Cat([phase.wrdata_mask for phase in dfi.phases])),
        ]
        self.comb += [
            If(wr_data_index > 0,
                If(wr_fifo_data_valid,
                    wr_fifo_dm.eq(wr_fifo.dout),
                ),
            ).Else(
                wr_fifo_dm.eq(wr_input_dm),
            ),
        ]

        wr_cases_comb = {}
        wr_cases_sync = {}

        wr_cases_comb = {0: [wr_dm.eq(wr_fifo_dm)]}
        wr_cases_sync = {0: [wr_register_dm.eq(0)]}

        for i in range(1, nphases):
            wr_cases_comb[i] = [
                wr_dm.eq(Cat(wr_register_dm[:i*2], wr_fifo_dm[:(nphases-i)*2])),
            ]
            wr_cases_sync[i] = [
                wr_register_dm.eq(wr_fifo_dm[(nphases-i)*2:]),
            ]

        self.comb += [Case(wr_data_offset, wr_cases_comb)]
        self.sync += [Case(wr_data_offset, wr_cases_sync)]

        # DM ---------------------------------------------------------------------------------------
        # With DM enabled, masking is performed only when the command used is WRITE-MASKED.
        self.comb += out.dm_n_o.eq(~wr_dm)
