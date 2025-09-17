#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen.fhdl.module import Module
from migen.genlib.record import Record

class BasePHYDQPadInput(Record):
    @staticmethod
    def data_layout(nphases, dq_dqs_ratio):
        base_layout = [
            (f"dq{i}_oe", 2*nphases) for i in range(1)
        ] + [
            (f"dq{i}_o", 2*nphases) for i in range(dq_dqs_ratio)
        ]
        base_layout.append(("dm_n_o", 2*nphases))
        return base_layout
    def __init__(self, nphases, dq_dqs_ratio):
        layout = self.data_layout(nphases, dq_dqs_ratio)
        Record.__init__(self, layout)


class BasePHYDQPadOutput(Record):
    @staticmethod
    def data_layout(nphases, dq_dqs_ratio):
        base_layout = [
            (f"dqs_t_i", 2*nphases) for i in range(1)
        ] + [
            (f"dq{i}_i", 2*nphases) for i in range(dq_dqs_ratio)
        ]
        return base_layout
    def __init__(self, nphases, dq_dqs_ratio):
        phy = self.data_layout(nphases, dq_dqs_ratio)
        self.nphases = nphases
        self.dq_dqs_ratio = dq_dqs_ratio
        Record.__init__(self, phy)


class BasePHYDQPadOutputBuffer(Module):
    @classmethod
    def get_delay(cls, nphases):
        return nphases
    def __init__(self, src, target):
        for name, _ in src.layout:
            self.sync += getattr(target, name).eq(getattr(src, name))


class BasePHYDQPhyInput(Record):
    @staticmethod
    def data_layout(nphases, dq_dqs_ratio):
        dfi_layout = [
            ("rddata", 2*dq_dqs_ratio),
        ]
        return dfi_layout
    def __init__(self, nphases, dq_dqs_ratio):
        dfi = self.data_layout(nphases, dq_dqs_ratio)
        layout = [(f"p{i}", dfi) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]


class BasePHYDQPhyInputCTRL(Record):
    @staticmethod
    def data_layout(nphases):
        base_layout = [
            ("rddata_en", 1),
        ]
        return base_layout
    def __init__(self, nphases):
        layout = [(f"p{i}", self.data_layout(nphases)) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]


class BasePHYDQPhyOutputCTRL(Record):
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


class BasePHYDQPhyOutput(Record):
    @staticmethod
    def data_layout(nphases, dq_dqs_ratio):
        base_layout = [
            ("wrdata", 2*dq_dqs_ratio),
        ]
        base_layout.append(("wrdata_mask", dq_dqs_ratio//4))
        return base_layout
    def __init__(self, nphases, dq_dqs_ratio):
        layout = [(f"p{i}", self.data_layout(nphases, dq_dqs_ratio)) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]


class BasePHYDQPhyOutputBuffer(Module):
    @classmethod
    def get_delay(cls, nphases):
        return nphases
    def __init__(self, src, target):
        for src_phase, target_phase in zip(src.phases, target.phases):
            for name, _ in src_phase.layout:
                self.sync += getattr(target_phase, name).eq(getattr(src_phase, name))
