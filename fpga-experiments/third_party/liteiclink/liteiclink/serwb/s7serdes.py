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

# S7 SerDes Clocking -------------------------------------------------------------------------------

class _S7SerdesClocking(Module):
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
                Instance("OSERDESE2",
                    p_DATA_WIDTH     = 8,
                    p_TRISTATE_WIDTH = 1,
                    p_DATA_RATE_OQ   = "DDR",
                    p_DATA_RATE_TQ   = "BUF",
                    p_SERDES_MODE    = "MASTER",

                    i_OCE    = 1,
                    i_RST    = ResetSignal("sys"),
                    i_CLK    = ClockSignal("sys4x"),
                    i_CLKDIV = ClockSignal("sys"),
                    i_D1     = converter.source.data[0],
                    i_D2     = converter.source.data[1],
                    i_D3     = converter.source.data[2],
                    i_D4     = converter.source.data[3],
                    i_D5     = converter.source.data[4],
                    i_D6     = converter.source.data[5],
                    i_D7     = converter.source.data[6],
                    i_D8     = converter.source.data[7],
                    o_OQ     = self.refclk,
                ),
                DifferentialOutput(self.refclk, pads.clk_p, pads.clk_n)
            ]

        # In Slave mode, multiply the clock provided by Master with a PLL/MMCM.
        elif mode == "slave":
            self.specials += DifferentialInput(pads.clk_p, pads.clk_n, self.refclk)

# S7 SerDes TX -------------------------------------------------------------------------------------

class _S7SerdesTX(Module):
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

        # Data output (DDR with sys4x)
        self.data = data = Signal(8)
        data_serialized  = Signal()
        self.comb += data.eq(datapath.source.data)
        self.specials += [
            Instance("OSERDESE2",
                p_DATA_WIDTH     = 8,
                p_TRISTATE_WIDTH = 1,
                p_DATA_RATE_OQ   = "DDR",
                p_DATA_RATE_TQ   = "BUF",
                p_SERDES_MODE    = "MASTER",

                i_OCE    = 1,
                i_RST    = ResetSignal("sys"),
                i_CLK    = ClockSignal("sys4x"),
                i_CLKDIV = ClockSignal("sys"),
                i_D1     = data[0],
                i_D2     = data[1],
                i_D3     = data[2],
                i_D4     = data[3],
                i_D5     = data[4],
                i_D6     = data[5],
                i_D7     = data[6],
                i_D8     = data[7],
                o_OQ     = data_serialized,
            ),
            DifferentialOutput(data_serialized, pads.tx_p, pads.tx_n)
        ]

# S7 SerDes RX -------------------------------------------------------------------------------------

class _S7SerdesRX(Module):
    def __init__(self, pads):
        # Control
        self.delay_rst     = Signal()
        self.delay_inc     = Signal()
        self.shift         = Signal()

        # Status
        self.idle  = idle = Signal()
        self.comma = comma = Signal()

        # Datapath
        self.source = source = stream.Endpoint([("data", 32)])

        # # #

        _shift = Signal(3)
        self.sync += If(self.shift, _shift.eq(_shift + 1))

        # Data input (DDR with sys4x)
        data_nodelay      = Signal()
        data_delayed      = Signal()
        self.data = data  = Signal(8)
        self.specials += [
            DifferentialInput(pads.rx_p, pads.rx_n, data_nodelay),
            Instance("IDELAYE2",
                p_DELAY_SRC             = "IDATAIN",
                p_SIGNAL_PATTERN        = "DATA",
                p_CINVCTRL_SEL          = "FALSE",
                p_HIGH_PERFORMANCE_MODE = "TRUE",
                p_REFCLK_FREQUENCY      = 200.0,
                p_PIPE_SEL              = "FALSE",
                p_IDELAY_TYPE           = "VARIABLE",
                p_IDELAY_VALUE          = 0,

                i_C        = ClockSignal(),
                i_LD       = self.delay_rst,
                i_CE       = self.delay_inc,
                i_LDPIPEEN = 0,
                i_INC      = 1,
                i_IDATAIN  = data_nodelay,
                o_DATAOUT  = data_delayed,
            ),
            Instance("ISERDESE2",
                p_DATA_WIDTH     = 8,
                p_DATA_RATE      = "DDR",
                p_SERDES_MODE    = "MASTER",
                p_INTERFACE_TYPE = "NETWORKING",
                p_NUM_CE         = 1,
                p_IOBDELAY       = "IFD",

                i_DDLY    = data_delayed,
                i_CE1     = 1,
                i_RST     = ResetSignal("sys"),
                i_CLK     = ClockSignal("sys4x"),
                i_CLKB    =~ClockSignal("sys4x"),
                i_CLKDIV  = ClockSignal("sys"),
                i_BITSLIP = self.shift,
                o_Q8      = data[0],
                o_Q7      = data[1],
                o_Q6      = data[2],
                o_Q5      = data[3],
                o_Q4      = data[4],
                o_Q3      = data[5],
                o_Q2      = data[6],
                o_Q1      = data[7],
            )
        ]

        # Datapath
        self.submodules.datapath = datapath = RXDatapath(8)
        self.comb += [
            datapath.sink.valid.eq(1),
            datapath.sink.data.eq(data),
            datapath.shift.eq(self.shift & (_shift == 0b111)),
            datapath.source.connect(source),
            idle.eq(datapath.idle),
            comma.eq(datapath.comma)
        ]

# S7 SerDes ----------------------------------------------------------------------------------------

@ResetInserter()
class S7Serdes(Module):
    def __init__(self, pads, mode="master"):
        self.submodules.clocking = _S7SerdesClocking(pads, mode)
        self.submodules.tx       = _S7SerdesTX(pads)
        self.submodules.rx       = _S7SerdesRX(pads)
