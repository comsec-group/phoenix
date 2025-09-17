#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from operator import xor, and_, or_
from functools import reduce

from migen.fhdl.structure import Signal, If, Cat, Replicate
from migen.fhdl.module import Module
from migen.genlib.record import Record

class PHYResetInput(Record):
    @staticmethod
    def data_layout():
        dfi_layout = [
            ("reset_n", 1),
        ]
        return dfi_layout
    def __init__(self, nphases):
        dfi = self.data_layout()
        layout = [(f"p{i}", dfi) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]
        for phase in self.phases:
            phase.reset_n.reset=~0


class PHYResetOutput(Record):
    @staticmethod
    def data_layout():
        dfi_layout = [
            ("reset_n", 2),
        ]
        return dfi_layout
    def __init__(self, nphases):
        dfi = self.data_layout()
        layout = [(f"p{i}", dfi) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]
        for phase in self.phases:
            phase.reset_n.reset=~0


class PHYAddressSlicerInput(Record):
    @staticmethod
    def data_layout(nranks):
        dfi_layout = [
            ("address", 14),
            ("cs_n", nranks),
            ("mode_2n", 1),
        ]
        return dfi_layout
    def __init__(self, nphases, nranks):
        dfi = self.data_layout(nranks)
        layout = [(f"p{i}", dfi) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]
        for phase in self.phases:
            getattr(phase, f"cs_n").reset = 2**nranks-1


class PHYAddressSlicerOutput(Record):
    @staticmethod
    def data_layout(nranks, nphases):
        dfi_layout = [
            *[(f"ca{i}", 2) for i in range(14)],
            *[(f"cs_n{i}", 2) for i in range(nranks)],
            ("par0", 2),
        ]
        return dfi_layout
    def __init__(self, nphases, nranks):
        dfi = self.data_layout(nranks, nphases)
        layout = [(f"p{i}", dfi) for i in range(nphases)]
        Record.__init__(self, layout)
        self.phases = [getattr(self, f"p{i}") for i in range(nphases)]
        for phase in self.phases:
            for i in range(nranks):
                getattr(phase, f"cs_n{i}").reset = 3


class PHYAddressSlicerRemap(Module):
    @classmethod
    def get_delay(cls, nphases):
        return 0
    def __init__(self, dfi_in, slicer_out, prefix):
        layout = [name for name, _ in slicer_out.layout[0][1]]
        for s_phase, t_phase in zip(dfi_in.phases, slicer_out.phases):
            for name in layout:
                if name == "mode_2n":
                    self.comb += getattr(t_phase, name).eq(
                        getattr(s_phase, name))
                else:
                    self.comb += getattr(t_phase, name).eq(
                        getattr(getattr(s_phase, prefix), name))


class _DFIAddressBuffer(Module):
    @classmethod
    def get_delay(cls, nphases):
        return nphases
    def __init__(self, src, target):
        for src_phase, target_phase in zip(src.phases, target.phases):
            for name, _ in src_phase.layout:
                self.sync += getattr(target_phase, name).eq(getattr(src_phase, name))


class PHYAddressSlicer(Module):
    @classmethod
    def get_delay(cls, nphases):
        return _DFIAddressBuffer.get_delay(nphases) + nphases # base buffer + Slicer delay

    def __init__(self, slicer_out, slicer_in, rdimm_mode, par_enable, par_value, nphases, nranks):
        # Buffer DFI -------------------------------------------------------------------------------
        cmd_buff = PHYAddressSlicerInput(nphases, nranks)
        self.submodules += _DFIAddressBuffer(slicer_in, cmd_buff)

        # DDR5 CS ----------------------------------------------------------------------------------
        carry_cs_n = Signal(nranks, reset=2**nranks-1)
        self.sync += [
            carry_cs_n.eq(cmd_buff.phases[-1].cs_n),
        ]

        for j, phase in enumerate(slicer_out.phases):
            for rank in range(nranks):
                cs_n = getattr(phase, f'cs_n{rank}')
                self.sync += [
                    If(~cmd_buff.phases[j].mode_2n | rdimm_mode,
                        cs_n[0].eq(cmd_buff.phases[j].cs_n[rank]),
                    ).Else(
                        cs_n[0].eq(carry_cs_n[rank] if j == 0 else cmd_buff.phases[j-1].cs_n[rank]),
                    ),
                    cs_n[1].eq(cmd_buff.phases[j].cs_n[rank]),
                ]

        # DDR5 CA ----------------------------------------------------------------------------------
        # RDIMM 2N mode ----------------------------------------------------------------------------
        mem   = Signal(max(3, nphases))

        take_lower_bits   = Signal(nphases)
        take_lower_bits_m = Signal(nphases)
        take_lower_bits_1 = Signal(nphases)
        take_lower_bits_2 = Signal(nphases)
        for i in range(1, len(take_lower_bits)):
            self.comb += take_lower_bits_1[i].eq(~reduce(and_, cmd_buff.phases[i-1].cs_n))
        for i in range(3, len(take_lower_bits)):
            self.comb += take_lower_bits_2[i].eq(
                ~reduce(and_, cmd_buff.phases[i-3].cs_n) & ~cmd_buff.phases[i-3].address[1]
            )

        self.comb += take_lower_bits_m.eq(
            Cat(cmd_buff.phases[i].mode_2n for i in range(nphases)))
        for i in range(0, 3, nphases):
            for j in range(nphases):
                if i+j >= 3:
                    break
                arr = []
                if i+j+nphases < 3:
                    arr.append(mem[i+j+nphases])
                if i + j < 1:
                    arr.append(~reduce(and_, cmd_buff.phases[nphases-1+i+j].cs_n))
                if 0 <= nphases-3 + i+j:
                    idx = nphases-3+i+j
                    arr.append(~reduce(and_, cmd_buff.phases[idx].cs_n) & ~cmd_buff.phases[idx].address[1])
                self.sync += mem[i+j].eq(reduce(or_, arr))

        for i in range(nphases):
            self.comb += take_lower_bits[i].eq(
                (take_lower_bits_1[i] | take_lower_bits_2[i] | mem[i]) & take_lower_bits_m[i]
            )

        # CA Slicer --------------------------------------------------------------------------------
        for j, phase in enumerate(slicer_out.phases):
            for bit in range(7):
                sig = getattr(phase, f'ca{bit}')
                self.sync += [
                    If(rdimm_mode & cmd_buff.phases[j].mode_2n,
                        If(~take_lower_bits[j],
                            sig.eq(Replicate(cmd_buff.phases[j].address[bit], 2)),
                        ).Else(
                            sig.eq(Replicate(cmd_buff.phases[j].address[bit + 7], 2)),
                        )
                    ).Elif(rdimm_mode,
                        sig.eq(Cat([cmd_buff.phases[j].address[bit + 7*i] for i in range (2)])),
                    ).Else(
                        sig.eq(Cat([cmd_buff.phases[j].address[bit] for _ in range (2)])),
                    ),
                ]

        for j, phase in enumerate(slicer_out.phases):
            for bit in range(7, 14):
                _ca = getattr(phase, f'ca{bit}')
                self.sync += [
                    If(~rdimm_mode,
                        _ca.eq(Replicate(cmd_buff.phases[j].address[bit], 2)),
                    ).Else(
                        _ca.eq(Replicate(0, 2)),
                    ),
                ]

        # DDR5 PAR ---------------------------------------------------------------------------------
        self.sync += [
            phase.par0.eq(reduce(xor, cmd_buff.phases[n_phase].address[7*i:7+7*i]) & par_enable | par_value)
                    for n_phase, phase in enumerate(slicer_out.phases) for i in range(2)]
