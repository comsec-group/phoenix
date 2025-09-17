#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.io import *
from migen.genlib.misc import WaitTimer

from litex.soc.interconnect import stream
from litex.soc.cores.code_8b10b import K, StreamEncoder, StreamDecoder

from liteiclink.serwb.scrambler import Scrambler, Descrambler

# TXDatapath ---------------------------------------------------------------------------------------

class TXDatapath(Module):
    def __init__(self, phy_dw, with_scrambling=False):
        self.idle   = idle   = Signal()
        self.comma  = comma  = Signal()
        self.sink   = sink   = stream.Endpoint([("data", 32)])
        self.source = source = stream.Endpoint([("data", phy_dw)])

        # # #

        # Scrambler
        if with_scrambling:
            self.submodules.scrambler = scrambler = Scrambler()

        # Line coding
        self.submodules.encoder = encoder = StreamEncoder(nwords=4)

        # Converter
        self.submodules.converter = converter = stream.Converter(40, phy_dw)

        # Dataflow
        if with_scrambling:
            self.comb += sink.connect(scrambler.sink)
            self.comb += scrambler.source.connect(encoder.sink)
        else:
            self.comb += sink.connect(encoder.sink, omit={"data"}),
            self.comb += encoder.sink.d.eq(sink.data)
        self.comb += encoder.source.connect(converter.sink)
        self.comb += converter.source.connect(source)

        # Send K28.5 if comma asserted.
        self.comb += If(comma,
            sink.ready.eq(0),
            encoder.sink.valid.eq(1),
            encoder.sink.k.eq(0b1),
            encoder.sink.d.eq(K(28,5)),
        )

        # Send Idle if idle asserted.
        self.comb += If(idle,
            sink.ready.eq(0),
            converter.sink.valid.eq(1),
            converter.sink.data.eq(0),
        )

# RXAligner ----------------------------------------------------------------------------------------

class RXAligner(Module):
    def __init__(self, phy_dw, shift=None):
        self.shift  = Signal() if shift is None else shift
        self.sink   = sink   = stream.Endpoint([("data", phy_dw)])
        self.source = source = stream.Endpoint([("data", phy_dw)])

        # # #

        _shift = Signal()
        self.sync += [
            If(self.shift,
                _shift.eq(1),
            ).Elif(sink.valid & sink.ready,
                _shift.eq(0),
            )
        ]

        self.comb += sink.connect(source)
        self.comb += If(_shift,
            source.valid.eq(0),
            sink.ready.eq(1)
        )


# RXDatapath ---------------------------------------------------------------------------------------

class RXDatapath(Module):
    def __init__(self, phy_dw, with_scrambling=False):
        self.shift  = shift  = Signal(6)
        self.sink   = sink   = stream.Endpoint([("data", phy_dw)])
        self.source = source = stream.Endpoint([("data", 32)])
        self.idle   = idle   = Signal()
        self.comma  = comma  = Signal()

        # # #

        # Aligner
        self.submodules.aligner = aligner = RXAligner(phy_dw, shift)

        # Converter
        self.submodules.converter = converter = stream.Converter(phy_dw, 40)

        # Line Coding
        self.submodules.decoder = decoder = StreamDecoder(nwords=4)

        # Descrambler
        if with_scrambling:
            self.submodules.descrambler = descrambler = Descrambler()

        # Dataflow
        self.comb += [
            sink.connect(aligner.sink),
            aligner.source.connect(converter.sink),
            converter.source.connect(decoder.sink),
         ]
        if with_scrambling:
            self.comb += decoder.source.connect(descrambler.sink)
            self.comb += descrambler.source.connect(source)
        else:
            self.comb += decoder.source.connect(source, omit={"d", "k"})
            self.comb += source.data.eq(decoder.source.d)

        # Decode Idle
        idle_timer = WaitTimer(32)
        self.submodules += idle_timer
        self.sync += If(converter.source.valid,
            idle_timer.wait.eq(
                (converter.source.data == 0) |
                (converter.source.data == (2**40-1))
            )
        )
        self.comb += idle.eq(idle_timer.done)

        # Decode Comma
        self.sync += If(decoder.source.valid,
            comma.eq(
                (decoder.source.k == 1) &
                (decoder.source.d == K(28, 5))
            )
        )
