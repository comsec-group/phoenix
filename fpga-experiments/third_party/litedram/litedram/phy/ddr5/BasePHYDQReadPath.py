#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import or_, add
from functools import reduce

from migen.fhdl.structure import Signal, If, Cat, Replicate, Case, Array
from migen.fhdl.module import Module
from migen.genlib.record import Record
from migen.genlib.fifo import SyncFIFO

from litedram.common import ShiftRegister
from litedram.phy.ddr5.BasePHYDQInterfaces import BasePHYDQPadOutputBuffer, BasePHYDQPadOutput

class BasePHYDQReadPath(Module):
    min_read_latency = None
    min_read_latency_no_CDC = None
    max_read_latency = None
    max_read_latency_no_CDC = None
    des_latency = None
    read_latency = None
    buffer_delay = 0

    @classmethod
    def get_min_max_supported_latencies(
            cls, nphases, address_delay, buffer_delay,
            ca_CDC_delay, rd_CDC_delay, rd_en_CDC_delay, ser_latency, des_latency):
        # Delay is:
        # command_delay, CDC and serialization
        # plus command length - 1
        # plus preamble
        # plus data deserialization and CDC
        cls.min_read_latency_no_CDC = address_delay + ca_CDC_delay[0].sys4x + ser_latency.sys4x + 1 + \
            2 + BasePHYDQPadOutputBuffer.get_delay(nphases)
        cls.min_read_latency = cls.min_read_latency_no_CDC + des_latency.sys4x + rd_CDC_delay[0].sys4x
        # Delay added by rddata_en buffer and by CDC, same as for wrdata_en
        cls.buffer_delay = buffer_delay + rd_en_CDC_delay[0].sys4x
        cls.des_latency = des_latency.sys4x
        # min latency + 66 (max CL) + 1 (2N) + worst case CA and RD delay
        cls.max_read_latency_no_CDC = cls.min_read_latency_no_CDC + 66 + 1 + \
            (ca_CDC_delay[1].sys4x - ca_CDC_delay[0].sys4x)
        cls.max_read_latency = cls.max_read_latency_no_CDC + rd_CDC_delay[1].sys4x + des_latency.sys4x
        cls.read_latency = (cls.max_read_latency + nphases - 1) // nphases

        return cls.min_read_latency - BasePHYDQPadOutputBuffer.get_delay(nphases), cls.max_read_latency

    # Read Control Path ------------------------------------------------------------------------
    # Creates a delay line of read commands coming from the DFI interface. The output is used to
    # signal a valid read data to the DFI interface.
    #
    # The read data valid is asserted for 1 sys_clk cycle when the data is available on the DFI
    # interface, the latency is the sum of the minimal PHY and user added delays.
    def __init__(self, dfi, dfi_ctrl, phy, rd_re, rd_valids, dq_dqs_ratio, CSRs,
                    default_read_latency=0, SyncFIFO_cls=SyncFIFO):
        nphases = len(dfi.phases)
        nphases_log = nphases.bit_length() - 1
        assert nphases > 1 and (nphases & (nphases-1)) == 0
        buffer_phy = BasePHYDQPadOutput(phy.nphases, phy.dq_dqs_ratio)
        self.submodules += BasePHYDQPadOutputBuffer(phy, buffer_phy)

        read_latency = (self.max_read_latency_no_CDC - self.buffer_delay + \
                        self.des_latency + nphases -1) // nphases

        default_read_latency = default_read_latency - 2 if default_read_latency > 1 else 0
        preamble_reset_value = self.min_read_latency_no_CDC + self.des_latency + \
            default_read_latency - 2 - self.buffer_delay

        self.submodules.dqs_preamble = _BasePHYDQSPreambleReadPath(
            preamble_reset_value, read_latency,
            self.max_read_latency_no_CDC - 2 - self.buffer_delay,
            dfi_ctrl, buffer_phy, CSRs
        )

        # Read Path
        rddata_en_input = Signal(nphases)
        for i, phase in enumerate(dfi_ctrl.phases):
            self.comb += rddata_en_input[i].eq(phase.rddata_en | CSRs['wlevel_en'])

        # Read window ----------------------------------------------------------------------
        rddata_ens = [
            ShiftRegister(
                signal = rddata_en_input[i],
                ntaps  = read_latency + 1
            ) for i in range(nphases)
        ]
        for i, rs in enumerate(rddata_ens):
            setattr(self.submodules, f"Read_SR_{i}", rs)

        rd_reset_value = preamble_reset_value+2

        rd_window     = Signal(nphases)
        rd_delay      = Signal(max=nphases*read_latency, reset=rd_reset_value)
        rd_index      = Signal(max=read_latency)
        rd_index_plus = Signal(max=read_latency + 1)
        rd_offset     = Signal(max=nphases) if nphases > 1 else Signal(1, reset=0)

        self.sync += [
            If(CSRs['dly_sel'] & CSRs['ck_rdly_inc'] & \
               (rd_delay < self.max_read_latency_no_CDC - self.buffer_delay),
                rd_delay.eq(rd_delay + 1),
            ).Elif(CSRs['dly_sel'] & CSRs['ck_rdly_rst'],
                rd_delay.eq(rd_reset_value),
            ),
            CSRs['ck_rddly_dq'].eq(rd_delay),
            rd_index_plus.eq(rd_index + 1),
        ]

        self.comb += [
            rd_index.eq(rd_delay[nphases_log:]),
            rd_offset.eq(rd_delay[:nphases_log]),
        ]

        rd_index_p = [Signal(max=read_latency) for _ in range(nphases)]
        rd_cases = {}
        for i in range(nphases):
            first_part  = [rd_index_p[j].eq(rd_index_plus) for j in range(i)]
            second_part = [rd_index_p[j].eq(rd_index) for j in range(i, nphases)]
            rd_cases[i] = first_part + second_part

        self.comb += [
            Case(rd_offset,
                rd_cases,
            ),
            rd_window.eq(Cat([rddata_ens[i].taps[rd_index_p[i]] for i in range(nphases)])),
        ]

        # Read Data Path ----------------------------------------------------------------------------
        # The rd_window can present any arbitrary (1*0*)* pattern of length nphases.
        # We detect where one full DFI phase of data finishes and where other starts
        # by counting how many valid bits are set in the rd_window, and how many
        # are set in range [0:i-1], for the i = {0, .., nphases-1}.
        # When data for full DFI phase are collected, they are stored in FIFO and await
        # for settings.read_latency-1 to pass before being presented on DFI bus.

        # depth only 8, as nibbles are close to each other
        rd_fifo = SyncFIFO(width=dq_dqs_ratio*nphases*2, depth=8, fwft=False)
        self.submodules += rd_fifo

        rddata_cnt          = Signal(max=nphases)
        rddata_intermediate = Array(Signal(2*dq_dqs_ratio) for _ in range(nphases))
        rddata_sel          = Array(Signal(2*dq_dqs_ratio) for _ in range(nphases))

        rddata_cnt_tmps      = [Signal(max=nphases) for _ in range(nphases)]
        rddata_cnt_and_tmp   = [Signal(max=2*nphases) for _ in range(nphases)]
        rddata_cnt_all_valid = Signal(max=2*nphases)

        self.comb += rddata_cnt_all_valid.eq(rddata_cnt + reduce(add, rd_window))

        for i in range(nphases):
            dq_start  = i*2
            dq_end    = (i+1)*2
            self.comb += [
                rddata_cnt_tmps[i].eq(reduce(add, rd_window[:i], 0)),
                rddata_cnt_and_tmp[i].eq(rddata_cnt + rddata_cnt_tmps[i]),
                If(rd_window[i] & ~rddata_cnt_and_tmp[i][nphases_log] & rddata_cnt_all_valid[nphases_log],
                    rddata_sel[rddata_cnt_and_tmp[i][:nphases_log]].eq(
                        Cat([getattr(buffer_phy, f'dq{dq}_i')[2*i] for dq in range(dq_dqs_ratio)],
                            [getattr(buffer_phy, f'dq{dq}_i')[2*i+1] for dq in range(dq_dqs_ratio)])),
                ),
                If(i < rddata_cnt,
                    rddata_sel[i].eq(rddata_intermediate[i]),
                ),
            ]

            self.sync += [
                If(rd_window[i] & (rddata_cnt_and_tmp[i][nphases_log] | ~rddata_cnt_all_valid[nphases_log]),
                    rddata_intermediate[rddata_cnt_and_tmp[i][:nphases_log]].eq(
                        Cat([getattr(buffer_phy, f'dq{dq}_i')[2*i] for dq in range(dq_dqs_ratio)],
                            [getattr(buffer_phy, f'dq{dq}_i')[2*i+1] for dq in range(dq_dqs_ratio)])),
                )
            ]

        self.sync += [
            If(reduce(or_, rd_window),
                rddata_cnt.eq(rddata_cnt_all_valid[:nphases_log]),
            ),
        ]

        rd_readable = Signal()
        rd_valids.append(rd_readable)
        self.comb += [
            rd_fifo.din.eq(0),
            rd_fifo.we.eq(0),
            If(reduce(or_, rd_window),
                If(rddata_cnt_all_valid[nphases_log],
                    rd_fifo.din.eq(Cat(rddata_sel)),
                    rd_fifo.we.eq(1),
                ),
            ),
            rd_readable.eq(rd_fifo.readable),
            rd_fifo.re.eq(rd_re & rd_fifo.readable),
            Cat(phase.rddata for phase in dfi.phases).eq(rd_fifo.dout),
        ]


class _BasePHYDQSPreambleReadPath(Module):
    def __init__(self, reset_value, read_latency, max_read_latency, dfi_ctrl, phy, CSRs):
        nphases = len(dfi_ctrl.phases)
        nphases_log = nphases.bit_length() - 1
        # Read Preamble window -------------------------------------------------------------
        rddata_preamble_ens = [
            ShiftRegister(
                signal = phase.rddata_en,
                ntaps  = read_latency
            ) for phase in dfi_ctrl.phases
        ]
        for i, rs in enumerate(rddata_preamble_ens):
            setattr(self.submodules, f"Preamble_SR_{i}", rs)

        rd_preamble_window      = Signal(nphases)
        rd_last_preamble_window = Signal(nphases)
        rd_preamble         = Signal(max=nphases*read_latency, reset=reset_value)
        rd_preamble_index   = Signal(max=read_latency)
        rd_preamble_p_index = Signal(max=read_latency + 1)
        rd_preamble_offset  = Signal(max=nphases) if nphases > 1 else Signal(1, reset=0)

        self.sync += [
            If(CSRs['dly_sel'] & CSRs['ck_rdly_inc'] & \
               (rd_preamble < max_read_latency),
                rd_preamble.eq(rd_preamble + 1),
            ).Elif(CSRs['dly_sel'] & CSRs['ck_rdly_rst'],
                rd_preamble.eq(reset_value),
            ),
            CSRs['ck_rddly_preamble'].eq(rd_preamble),
            rd_preamble_p_index.eq(rd_preamble_index + 1),
        ]
        self.comb += [
            rd_preamble_index.eq(rd_preamble[nphases_log:]),
            rd_preamble_offset.eq(rd_preamble[:nphases_log]),
        ]

        rd_preamble_index_p = [Signal(max=read_latency) for _ in range(nphases)]
        rd_preamble_cases = {}
        for i in range(nphases):
            first_part  = [rd_preamble_index_p[j].eq(rd_preamble_p_index) for j in range(i)]
            second_part = [rd_preamble_index_p[j].eq(rd_preamble_index) for j in range(i, nphases)]
            rd_preamble_cases[i] = first_part + second_part

        self.comb += [
            Case(rd_preamble_offset, rd_preamble_cases),
            rd_preamble_window.eq(
                Cat([rddata_preamble_ens[i].taps[rd_preamble_index_p[i]] for i in range(nphases)])
            ),
        ]
        self.sync += [rd_last_preamble_window.eq(rd_preamble_window)]

        rd_preamble_rdy = Signal(max=2*nphases)
        self.comb += [
            If(~rd_last_preamble_window[-1] & rd_preamble_window[0],
                rd_preamble_rdy.eq(1)
            ),
        ]
        for i in range(1, nphases):
            self.comb += [
                If(~rd_preamble_window[i-1] & rd_preamble_window[i],
                    rd_preamble_rdy.eq(2*i | 1)
                ),
            ]

        rd_sampled_preamble = Signal(2*2)
        rd_preamble_cnt     = Signal()
        rd_preamble_cases_sync = {}
        dqs_t_i = phy.dqs_t_i
        for i in range(nphases):
            if i+1 < nphases:
                rd_preamble_cases_sync[i] = [
                    rd_sampled_preamble.eq(dqs_t_i[i*2:i*2+4]),
                    rd_preamble_cnt.eq(0),
                ]
            else:
                rd_preamble_cases_sync[i] = [
                    rd_sampled_preamble[0:2].eq(dqs_t_i[i*2:i*2+2]),
                    rd_preamble_cnt.eq(1),
                ]

        self.sync += [
            If(rd_preamble_rdy[0],
                Case(rd_preamble_rdy[1:], rd_preamble_cases_sync),
            ),
            If(rd_preamble_cnt == 1,
                rd_sampled_preamble[2:4].eq(dqs_t_i[0:2]),
                rd_preamble_cnt.eq(0),
            ),
        ]
        self.comb += If(CSRs['dly_sel'],
            CSRs['preamble'].eq(rd_sampled_preamble),
        )


class BasePHYDQRetimeReadPath(Module):
    def __init__(self, read_latency, dfi, dfi_ctrl, rd_fifo_valid, rd_fifo_re, CSRs, prefix):
        nphases = len(dfi.phases)
        # Return data from fifo
        rddata_en_input = Signal(nphases)
        # Assume RDDATA width is nphases(8)
        # TODO: handle 8, 16 and 18 read lengths
        # 18 - read with CRC
        next_valid_rddata_en = Signal(nphases.bit_length()-1)
        rddata_en_reduced    = Signal()
        for i, phase in enumerate(dfi_ctrl.phases):
            self.comb += rddata_en_input[i].eq(phase.rddata_en | CSRs['wlevel_en'])

        rddata_en_cases = {}
        rddata_en_next_cases = {}
        for i in range(nphases):
            rddata_en_cases[i] = [
                rddata_en_reduced.eq(reduce(or_, rddata_en_input[i:]))
            ]
            _intermediate_if = If(
                (next_valid_rddata_en == i) & rddata_en_input[i],
                next_valid_rddata_en.eq(i)
            )
            for j in range(i+1, nphases):
                _intermediate_if = _intermediate_if.Elif(
                    (next_valid_rddata_en == i) & rddata_en_input[j],
                    next_valid_rddata_en.eq(j)
                )
            rddata_en_next_cases[i] = _intermediate_if

        self.comb += [Case(next_valid_rddata_en, rddata_en_cases)]
        self.sync += [Case(next_valid_rddata_en, rddata_en_next_cases)]

        rddata_out_en = ShiftRegister(
            signal = rddata_en_reduced,
            ntaps  = read_latency + 2
        )
        setattr(self.submodules, f"Read_FIFO_SR", rddata_out_en)

        # TODO: Use CSR to set read delay
        rddata_valid   = Signal()
        rddata_valid_d = Signal()

        self.comb += rddata_valid.eq(rddata_out_en.taps[-1])
        self.sync += rddata_valid_d.eq(rddata_valid)

        self.comb += [
            getattr(phase, prefix).rddata_valid.eq(rddata_valid_d) for phase in dfi.phases
        ]

        self.comb += [
            rd_fifo_re.eq((rddata_valid & rd_fifo_valid) | CSRs['discard_rd_fifo'])
        ]
