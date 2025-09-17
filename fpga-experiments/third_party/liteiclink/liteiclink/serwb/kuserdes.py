#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.misc import BitSlip, WaitTimer

from litex.build.io import *

from litex.soc.interconnect import stream
from litex.soc.cores.code_8b10b import Encoder, Decoder

from liteiclink.serwb.datapath import TXDatapath, RXDatapath

# KU SerDes Clocking -------------------------------------------------------------------------------

class _KUSerdesClocking(Module):
    def __init__(self, pads, mode="master"):
        self.refclk = Signal()

        # # #

        # In Master mode, generate the linerate/10 clock. Slave will re-multiply it.
        if mode == "master":
            self.submodules.converter = converter = stream.Converter(40, 8)
            self.comb += [
                converter.sink.valid.eq(1),
                converter.source.ready.eq(1),
                converter.sink.data.eq(Replicate(Signal(10, reset=0b1111100000), 4)),
            ]
            self.specials += [
                Instance("OSERDESE3",
                    p_DATA_WIDTH         = 8,
                    p_INIT               = 0,
                    p_IS_CLK_INVERTED    = 0,
                    p_IS_CLKDIV_INVERTED = 0,
                    p_IS_RST_INVERTED    = 0,

                    i_RST    = ResetSignal("sys"),
                    i_CLK    = ClockSignal("sys4x"),
                    i_CLKDIV = ClockSignal("sys"),
                    i_D      = converter.source.data,
                    o_OQ     = self.refclk,
                ),
                DifferentialOutput(self.refclk, pads.clk_p, pads.clk_n)
            ]

        # In Slave mode, multiply the clock provided by Master with a PLL/MMCM.
        elif mode == "slave":
            self.specials += DifferentialInput(pads.clk_p, pads.clk_n, self.refclk)

# KU SerDes TX -------------------------------------------------------------------------------------

class _KUSerdesTX(Module):
    def __init__(self, pads):
        # Control
        self.idle  = idle  = Signal()
        self.comma = comma = Signal()

        # Datapath
        self.sink = sink = stream.Endpoint([("data", 32)])

        # # #


        # Datapath
        self.submodules.datapath = datapath = TXDatapath(8)
        self.comb += [
            sink.connect(datapath.sink),
            datapath.source.ready.eq(1),
            datapath.idle.eq(idle),
            datapath.comma.eq(comma)
        ]

        # Output Data (DDR with sys4x)
        self.data = data = Signal(8)
        data_serialized  = Signal()
        self.comb += data.eq(datapath.source.data)
        self.specials += [
              Instance("OSERDESE3",
                p_DATA_WIDTH         = 8,
                p_INIT               = 0,
                p_IS_CLK_INVERTED    = 0,
                p_IS_CLKDIV_INVERTED = 0,
                p_IS_RST_INVERTED    = 0,

                i_RST    = ResetSignal("sys"),
                i_CLK    = ClockSignal("sys4x"),
                i_CLKDIV = ClockSignal("sys"),
                i_D      = data,
                o_OQ     = data_serialized,
            ),
            DifferentialOutput(data_serialized, pads.tx_p, pads.tx_n)
        ]

# KU SerDes RX -------------------------------------------------------------------------------------

class _KUSerdesRX(Module):
    def __init__(self, pads):
        # Control
        self.delay_rst     = Signal()
        self.delay_inc     = Signal()
        self.shift = shift = Signal(6)

        # Status
        self.idle  = idle = Signal()
        self.comma = comma = Signal()

        # Datapath
        self.source = source = stream.Endpoint([("data", 32)])

        # # #

        # Data input (DDR with sys4x)
        data_nodelay      = Signal()
        data_delayed      = Signal()
        self.data = data  = Signal(8)
        self.specials += [
            DifferentialInput(pads.rx_p, pads.rx_n, data_nodelay),
            Instance("IDELAYE3",
                p_CASCADE          = "NONE",
                p_UPDATE_MODE      = "ASYNC",
                p_REFCLK_FREQUENCY = 200.0,
                p_IS_CLK_INVERTED  = 0,
                p_IS_RST_INVERTED  = 0,
                p_DELAY_FORMAT     = "COUNT",
                p_DELAY_SRC        = "IDATAIN",
                p_DELAY_TYPE       = "VARIABLE",
                p_DELAY_VALUE      = 0,

                i_CLK     = ClockSignal("sys"),
                i_RST     = self.delay_rst,
                i_LOAD    = 0,
                i_INC     = 1,
                i_EN_VTC  = 0,
                i_CE      = self.delay_inc,
                i_IDATAIN = data_nodelay,
                o_DATAOUT = data_delayed
            ),
            Instance("ISERDESE3",
                p_IS_CLK_INVERTED   = 0,
                p_IS_CLK_B_INVERTED = 1,
                p_DATA_WIDTH        = 8,

                i_D      = data_delayed,
                i_RST    = ResetSignal("sys"),
                i_CLK    = ClockSignal("sys4x"),
                i_CLK_B  = ClockSignal("sys4x"), # Locally inverted
                i_CLKDIV = ClockSignal("sys"),
                o_Q      = data
            )
        ]

        # Datapath
        self.submodules.datapath = datapath = RXDatapath(8)
        self.comb += [
            datapath.sink.valid.eq(1),
            datapath.sink.data.eq(data),
            datapath.shift.eq(shift),
            datapath.source.connect(source),
            idle.eq(datapath.idle),
            comma.eq(datapath.comma)
        ]

# KU SerDes ----------------------------------------------------------------------------------------

@ResetInserter()
class KUSerdes(Module):
    def __init__(self, pads, mode="master"):
        self.submodules.clocking = _KUSerdesClocking(pads, mode)
        self.submodules.tx       = _KUSerdesTX(pads)
        self.submodules.rx       = _KUSerdesRX(pads)
