#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import math

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream
from litex.soc.cores.prbs import PRBSTX, PRBSRX
from litex.soc.cores.code_8b10b import Encoder, Decoder

from liteiclink.serdes.gty_ultrascale_init import GTYRXInit, GTYTXInit
from liteiclink.serdes.clock_aligner import BruteforceClockAligner

from liteiclink.serdes.common import *

# GTY Channel PLL ----------------------------------------------------------------------------------

class GTYChannelPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate):
        self.refclk = refclk
        self.reset  = Signal()
        self.lock   = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

    @staticmethod
    def compute_config(refclk_freq, linerate):
        for n1 in [4, 5]:
            for n2 in [1, 2, 3, 4, 5]:
                for m in [1, 2]:
                    vco_freq = refclk_freq*(n1*n2)/m
                    if 2.0e9 <= vco_freq <= 6.25e9:
                        for d in 1, 2, 4, 8: # CHECKME: 16, 32 not supported when using CPLL.
                            current_linerate = vco_freq*2/d
                            if current_linerate == linerate:
                                return {"n1": n1, "n2": n2, "m": m, "d": d,
                                        "vco_freq": vco_freq,
                                        "clkin": refclk_freq,
                                        "linerate": linerate}
        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))

    def __repr__(self):
        r = """
GTYChannelPLL
==============
  overview:
  ---------
       +--------------------------------------------------+
       |                                                  |
       |   +-----+  +---------------------------+ +-----+ |
       |   |     |  | Phase Frequency Detector  | |     | |
CLKIN +----> /M  +-->       Charge Pump         +-> VCO +---> CLKOUT
       |   |     |  |       Loop Filter         | |     | |
       |   +-----+  +---------------------------+ +--+--+ |
       |              ^                              |    |
       |              |    +-------+    +-------+    |    |
       |              +----+  /N2  <----+  /N1  <----+    |
       |                   +-------+    +-------+         |
       +--------------------------------------------------+
                            +-------+
                   CLKOUT +->  2/D  +-> LINERATE
                            +-------+
  config:
  -------
    CLKIN    = {clkin}MHz
    CLKOUT   = CLKIN x (N1 x N2) / M = {clkin}MHz x ({n1} x {n2}) / {m}
             = {vco_freq}GHz
    LINERATE = CLKOUT x 2 / D = {vco_freq}GHz x 2 / {d}
             = {linerate}GHz
""".format(clkin    = self.config["clkin"]/1e6,
           n1       = self.config["n1"],
           n2       = self.config["n2"],
           m        = self.config["m"],
           vco_freq = self.config["vco_freq"]/1e9,
           d        = self.config["d"],
           linerate = self.config["linerate"]/1e9)
        return r

# GTY Quad PLL -------------------------------------------------------------------------------------

class GTYQuadPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate):
        self.clk    = Signal()
        self.refclk = Signal()
        self.reset  = Signal()
        self.lock   = Signal()
        self.config = config = self.compute_config(refclk_freq, linerate)

        # # #

        use_qpll0 = config["qpll"] == "qpll0"
        use_qpll1 = config["qpll"] == "qpll1"

        self.specials += Instance("GTYE4_COMMON",
            p_AEN_QPLL0_FBDIV       = 0b1,
            p_AEN_QPLL1_FBDIV       = 0b1,
            p_AEN_SDM0TOGGLE        = 0b0,
            p_AEN_SDM1TOGGLE        = 0b0,
            p_A_SDM0TOGGLE          = 0b0,
            p_A_SDM1DATA_HIGH       = 0b000000000,
            p_A_SDM1DATA_LOW        = 0b0000000000000000,
            p_A_SDM1TOGGLE          = 0b0,

            p_BIAS_CFG0             = 0b0000000000000000,
            p_BIAS_CFG1             = 0b0000000000000000,
            p_BIAS_CFG2             = 0b0000010100100100,
            p_BIAS_CFG3             = 0b0000000001000001,
            p_BIAS_CFG4             = 0b0000000000010000,
            p_BIAS_CFG_RSVD         = 0b0000000000000000,
            p_COMMON_CFG0           = 0b0000000000000000,
            p_COMMON_CFG1           = 0b0000000000000000,

            p_POR_CFG               = 0b0000000000000000,
            p_PPF0_CFG              = 0b0000101100000000,  # FIXME: 12g: 0b0000011000000000, 10g: 0b0000010000000000
            p_PPF1_CFG              = 0b0000011000000000,

            p_QPLL0_CFG0            = 0b0011001100011100,
            p_QPLL0_CFG1            = 0b1101000000111000,
            p_QPLL0_CFG1_G3         = 0b1101000000111000,
            p_QPLL0_CFG2            = 0b0000111111000001,  # FIXME: 0b0000111111000000,
            p_QPLL0_CFG2_G3         = 0b0000111111000001,  # FIXME: 0b0000111111000000,
            p_QPLL0_CFG3            = 0b0000000100100000,
            p_QPLL0_CFG4            = 0b0000000000000001,
            p_QPLL0_CP              = 0b0011111111,
            p_QPLL0_CP_G3           = 0b0000001111,
            p_QPLL0_INIT_CFG0       = 0b0000001010110010,
            p_QPLL0_INIT_CFG1       = 0b00000000,
            p_QPLL0_LOCK_CFG        = 0b0010010111101000,
            p_QPLL0_LOCK_CFG_G3     = 0b0010010111101000,
            p_QPLL0_LPF             = 0b1101111111,        # FIXME: 0b1000111111,
            p_QPLL0_LPF_G3          = 0b0111010101,
            p_QPLL0_PCI_EN          = 0b0,
            p_QPLL0_RATE_SW_USE_DRP = 0b1,
            p_QPLL0_FBDIV           = config["n"],
            p_QPLL0_FBDIV_G3        = 160,
            p_QPLL0_REFCLK_DIV      = config["m"],
            p_QPLL0CLKOUT_RATE      = {1:"FULL", 2:"HALF"}[config["clkout_rate"]],
            p_QPLL0_SDM_CFG0        = 0b0000000010000000,
            p_QPLL0_SDM_CFG1        = 0b0000000000000000,
            p_QPLL0_SDM_CFG2        = 0b0000000000000000,

            p_QPLL1_CFG0            = 0b0011001100011100,
            p_QPLL1_CFG1            = 0b1101000000111000,
            p_QPLL1_CFG1_G3         = 0b1101000000111000,
            p_QPLL1_CFG2            = 0b0000111111000000, # FIXME: 0b0000111111000011,
            p_QPLL1_CFG2_G3         = 0b0000111111000000, # FIXME: 0b0000111111000011
            p_QPLL1_CFG3            = 0b0000000100100000,
            p_QPLL1_CFG4            = 0b0000000000000010,
            p_QPLL1_CP              = 0b0011111111,
            p_QPLL1_CP_G3           = 0b0001111111,
            p_QPLL1_INIT_CFG0       = 0b0000001010110010,
            p_QPLL1_INIT_CFG1       = 0b00000000,
            p_QPLL1_LOCK_CFG        = 0b0010010111101000,
            p_QPLL1_LOCK_CFG_G3     = 0b0010010111101000,
            p_QPLL1_LPF             = 0b1100111111,       # FIXME: 0b1000011111,
            p_QPLL1_LPF_G3          = 0b0111010100,
            p_QPLL1_PCI_EN          = 0b0,
            p_QPLL1_RATE_SW_USE_DRP = 0b1,
            p_QPLL1_FBDIV           = config["n"],
            p_QPLL1_FBDIV_G3        = 80,
            p_QPLL1_REFCLK_DIV      = config["m"],
            p_QPLL1CLKOUT_RATE      = {1:"FULL", 2:"HALF"}[config["clkout_rate"]],
            p_QPLL1_SDM_CFG0        = 0b0000000000000000, # FIXME: 0b0000000010000000,
            p_QPLL1_SDM_CFG1        = 0b0000000000000000,
            p_QPLL1_SDM_CFG2        = 0b0000000000000000,

            # Common
            i_GTREFCLK00      = refclk if use_qpll0 else 0,
            i_GTREFCLK01      = refclk if use_qpll1 else 0,
            i_GTREFCLK10      = 0,
            i_GTREFCLK11      = 0,
            i_QPLLRSVD1       = 0,
            i_QPLLRSVD2       = 0,
            i_QPLLRSVD3       = 0,
            i_QPLLRSVD4       = 0,
            i_BGBYPASSB       = 1,
            i_BGMONITORENB    = 1,
            i_BGPDB           = 1,
            i_BGRCALOVRD      = 0b11111,
            i_BGRCALOVRDENB   = 0b1,
            i_RCALENB         = 1,

            # QPLL0
            i_SDM0DATA        = round(config["f"]*(2**24)),
            i_SDM0WIDTH       = 24,
            i_SDM0RESET       = 0b0,
            i_SDM0TOGGLE      = 0b0,
            i_QPLL0CLKRSVD0   = 0,
            i_QPLL0CLKRSVD1   = 0,
            i_QPLL0LOCKDETCLK = ClockSignal(),
            i_QPLL0LOCKEN     = 1,
            o_QPLL0LOCK       = self.lock   if use_qpll0 else Signal(),
            o_QPLL0OUTCLK     = self.clk    if use_qpll0 else Signal(),
            o_QPLL0OUTREFCLK  = self.refclk if use_qpll0 else Signal(),
            i_QPLL0PD         = 0           if use_qpll0 else 1,
            i_QPLL0REFCLKSEL  = 0b001,
            i_QPLL0RESET      = self.reset,

            # QPLL1
            i_SDM1DATA        = round(config["f"]*(2**24)),
            i_SDM1WIDTH       = 24,
            i_SDM1RESET       = 0b0,
            i_SDM1TOGGLE      = 0b0,
            i_QPLL1CLKRSVD0   = 0,
            i_QPLL1CLKRSVD1   = 0,
            i_QPLL1LOCKDETCLK = ClockSignal(),
            i_QPLL1LOCKEN     = 1,
            o_QPLL1LOCK       = self.lock   if use_qpll1 else Signal(),
            o_QPLL1OUTCLK     = self.clk    if use_qpll1 else Signal(),
            o_QPLL1OUTREFCLK  = self.refclk if use_qpll1 else Signal(),
            i_QPLL1PD         = 0           if use_qpll1 else 1,
            i_QPLL1REFCLKSEL  = 0b001,
            i_QPLL1RESET      = self.reset,
        )

    @staticmethod
    def compute_config(refclk_freq, linerate):
        # FIXME: cleanup.
        assert linerate <= 32.75e9
        for d in [1, 2, 4, 8, 16]:
            pllclk_out = (linerate*d)/2

            if linerate > 16.375e9:
                rate = 1 # Full
            else:
                rate = 2 # Half
            vco_freq = pllclk_out*rate
            print("vco_freq:", vco_freq)
            if 8e9 <= vco_freq <= 13e9:
                qpll = "qpll1"
            elif 9.8e9 <= vco_freq <= 16.375e9:
                qpll = "qpll0"
            else:
                qpll = None
            if qpll is not None:
                for m in [1, 2, 3, 4]:
                    n_f = (vco_freq/refclk_freq)*m
                    if 16 <= n_f <= 160:
                        n = math.floor(n_f)
                        f = n_f - n  # FIXME: round((n_f - n)*(2**24))/(2**24)
                        vco_freq_calc = refclk_freq*(n +f)/m
                        clkout_calc   = vco_freq_calc/rate
                        linerate_calc = clkout_calc*2/d
                        return {"n": n, "m": m, "d": d, "f": f,
                                "vco_freq": vco_freq_calc,
                                "qpll": qpll,
                                "clkin": refclk_freq,
                                "clkout_rate": rate,
                                "clkout": clkout_calc,
                                "linerate": linerate_calc}

        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))

    def __repr__(self):
        config = self.config
        r = """
GTYQuadPLL
===========
  overview:
  ---------
       +----------------------------------------------------------------------------+
       |                                          +------------+                    |
       |   +-----+  +---------------------------+ |   QPLL0    |    +-+-+           |
       |   |     |  | Phase Frequency Detector  +->    VCO     |    |   |   +-----+ |
CLKIN +----> /M  +-->       Charge Pump         | +------------+--->+/2 +-->|     | |
       |   |     |  |       Loop Filter         +->   QPLL1    | |  |   |   |  M  | |
       |   +-----+  +---------------------------+ |    VCO     | |  +---+   |  U  | +---> CLKOUT
       |              ^                           +-----+------+ +--------->|  X  | |
       |              |   +---------------+             |                   |     | |
       |              +---+    /N Frac    + <-----------+                   +-----+ |
       |                  +---------------+                                         |
       +----------------------------------------------------------------------------+
                               +-------+
                      CLKOUT +->  2/D  +-> LINERATE
                               +-------+
  config:
  -------
    CLKIN    = {clkin}MHz
    CLKOUT   = CLKIN x N.Fractional / (clkout_rate x M) = {clkin}MHz x {n_f} / ({clkout_rate} x {m})
             = {clkout}GHz
    VCO      = {vco_freq}GHz ({qpll})
    LINERATE = CLKOUT x 2 / D = {clkout}GHz x 2 / {d}
             = {linerate}GHz
""".format(clkin          = config["clkin"]/1e6,
           n_f            = config["n"] + config["f"],
           m              = config["m"],
           clkout_rate    = config["clkout_rate"],
           clkout         = config["clkout"]/1e9,
           vco_freq       = config["vco_freq"]/1e9,
           qpll           = config["qpll"].upper(),
           d              = config["d"],
           linerate       = config["linerate"]/1e9)
        return r

# GTY ----------------------------------------------------------------------------------------------

class GTY(Module, AutoCSR):
    def __init__(self, pll, tx_pads, rx_pads, sys_clk_freq,
        data_width          = 20,
        tx_buffer_enable    = False,
        rx_buffer_enable    = False,
        clock_aligner       = True,
        clock_aligner_comma = 0b0101111100,
        tx_polarity         = 0,
        rx_polarity         = 0):
        assert data_width in [20, 40, 80]

        # TX controls
        self.tx_enable              = Signal(reset=1)
        self.tx_ready               = Signal()
        self.tx_inhibit             = Signal()
        self.tx_produce_square_wave = Signal()
        self.tx_produce_pattern     = Signal()
        self.tx_pattern             = Signal(data_width)
        self.tx_prbs_config         = Signal(2)

        # RX controls
        self.rx_enable      = Signal(reset=1)
        self.rx_ready       = Signal()
        self.rx_align       = Signal(reset=1)
        self.rx_prbs_config = Signal(2)
        self.rx_prbs_pause  = Signal()
        self.rx_prbs_errors = Signal(32)

        # DRP
        self.drp = DRPInterface()

        # Loopback
        self.loopback = Signal(3)

        # # #

        use_cpll  = isinstance(pll, GTYChannelPLL)
        use_qpll0 = isinstance(pll, GTYQuadPLL) and pll.config["qpll"] == "qpll0"
        use_qpll1 = isinstance(pll, GTYQuadPLL) and pll.config["qpll"] == "qpll1"

        self.nwords = nwords = data_width//10

        self.submodules.encoder = ClockDomainsRenamer("tx")(Encoder(nwords, True))
        self.decoders = [ClockDomainsRenamer("rx")(Decoder(True)) for _ in range(nwords)]
        self.submodules += self.decoders

        # Transceiver direct clock outputs (useful to specify clock constraints)
        self.txoutclk = Signal()
        self.rxoutclk = Signal()

        self.tx_clk_freq = pll.config["linerate"]/data_width
        self.rx_clk_freq = pll.config["linerate"]/data_width

        # Control/Status CDC
        tx_produce_square_wave = Signal()
        tx_produce_pattern     = Signal()
        tx_pattern             = Signal(20)
        tx_prbs_config         = Signal(2)

        rx_prbs_config = Signal(2)
        rx_prbs_pause  = Signal()
        rx_prbs_errors = Signal(32)

        self.specials += [
            MultiReg(self.tx_produce_square_wave, tx_produce_square_wave, "tx"),
            MultiReg(self.tx_produce_pattern, tx_produce_pattern, "tx"),
            MultiReg(self.tx_pattern, tx_pattern, "tx"),
            MultiReg(self.tx_prbs_config, tx_prbs_config, "tx"),
        ]

        self.specials += [
            MultiReg(self.rx_prbs_config, rx_prbs_config, "rx"),
            MultiReg(self.rx_prbs_pause, rx_prbs_pause, "rx"),
            MultiReg(rx_prbs_errors, self.rx_prbs_errors, "sys"),
        ]

        # # #

        # TX init ----------------------------------------------------------------------------------
        self.submodules.tx_init = tx_init = GTYTXInit(sys_clk_freq, buffer_enable=tx_buffer_enable)
        self.comb += [
            self.tx_ready.eq(tx_init.done),
            tx_init.restart.eq(~self.tx_enable)
        ]

        # RX init ----------------------------------------------------------------------------------
        self.submodules.rx_init = rx_init = GTYRXInit(sys_clk_freq, buffer_enable=rx_buffer_enable)
        self.comb += [
            self.rx_ready.eq(rx_init.done),
            rx_init.restart.eq(~self.rx_enable)
        ]

        # PLL ----------------------------------------------------------------------------------
        self.comb += [
            tx_init.plllock.eq(pll.lock),
            rx_init.plllock.eq(pll.lock),
            pll.reset.eq(tx_init.pllreset)
        ]

        # DRP mux ----------------------------------------------------------------------------------
        self.submodules.drp_mux = drp_mux = DRPMux()
        drp_mux.add_interface(self.drp)

        # GTYE4_CHANNEL instance -------------------------------------------------------------------
        class Open(Signal): pass
        txdata = Signal(data_width)
        rxdata = Signal(data_width)
        rxphaligndone = Signal()
        self.gty_params = dict(
            p_ACJTAG_DEBUG_MODE            = 0b0,
            p_ACJTAG_MODE                  = 0b0,
            p_ACJTAG_RESET                 = 0b0,
            p_ADAPT_CFG0                   = 0b0000000000000000,
            p_ADAPT_CFG1                   = 0b1111100000011100 if pll.config["linerate"] < 10e9 else
                                             0b1111101100011100,
            p_ADAPT_CFG2                   = 0b0000000000000000,
            p_ALIGN_COMMA_DOUBLE           = "FALSE",
            p_ALIGN_COMMA_ENABLE           = 0b0000000000,
            p_ALIGN_COMMA_WORD             = 1,
            p_ALIGN_MCOMMA_DET             = "FALSE",
            p_ALIGN_MCOMMA_VALUE           = 0b1010000011,
            p_ALIGN_PCOMMA_DET             = "FALSE",
            p_ALIGN_PCOMMA_VALUE           = 0b0101111100,
            p_A_RXOSCALRESET               = 0b0,
            p_A_RXPROGDIVRESET             = 0b0,
            p_A_RXTERMINATION              = 0b1,
            p_A_TXDIFFCTRL                 = 0b01100,
            p_A_TXPROGDIVRESET             = 0b0,
            p_CBCC_DATA_SOURCE_SEL         = "ENCODED",
            p_CDR_SWAP_MODE_EN             = 0b0,
            p_CFOK_PWRSVE_EN               = 0b1,
            p_CHAN_BOND_KEEP_ALIGN         = "FALSE",
            p_CHAN_BOND_MAX_SKEW           = 1,
            p_CHAN_BOND_SEQ_1_1            = 0b0000000000,
            p_CHAN_BOND_SEQ_1_2            = 0b0000000000,
            p_CHAN_BOND_SEQ_1_3            = 0b0000000000,
            p_CHAN_BOND_SEQ_1_4            = 0b0000000000,
            p_CHAN_BOND_SEQ_1_ENABLE       = 0b1111,
            p_CHAN_BOND_SEQ_2_1            = 0b0000000000,
            p_CHAN_BOND_SEQ_2_2            = 0b0000000000,
            p_CHAN_BOND_SEQ_2_3            = 0b0000000000,
            p_CHAN_BOND_SEQ_2_4            = 0b0000000000,
            p_CHAN_BOND_SEQ_2_ENABLE       = 0b1111,
            p_CHAN_BOND_SEQ_2_USE          = "FALSE",
            p_CHAN_BOND_SEQ_LEN            = 1,
            p_CH_HSPMUX                    = 0b0010000000100000 if pll.config["linerate"] < 15e9 else
                                             0b0100000001000000 if pll.config["linerate"] < 20e9 else
                                             0b0110000001100000,
            p_CKCAL1_CFG_0                 = 0b1100000011000000 if pll.config["linerate"] < 20e9 else
                                             0b0100000001000000,
            p_CKCAL1_CFG_1                 = 0b0001000011000000 if pll.config["linerate"] < 20e9 else
                                             0b0001000001000000,
            p_CKCAL1_CFG_2                 = 0b0010000000001000,
            p_CKCAL1_CFG_3                 = 0b0000000000000000,
            p_CKCAL2_CFG_0                 = 0b1100000011000000 if pll.config["linerate"] < 20e9 else
                                             0b0100000001000000,
            p_CKCAL2_CFG_1                 = 0b1000000011000000 if pll.config["linerate"] < 20e9 else
                                             0b0000000001000000,
            p_CKCAL2_CFG_2                 = 0b0001000000000000,
            p_CKCAL2_CFG_3                 = 0b0000000000000000,
            p_CKCAL2_CFG_4                 = 0b0000000000000000,
            p_CLK_CORRECT_USE              = "FALSE",
            p_CLK_COR_KEEP_IDLE            = "FALSE",
            p_CLK_COR_MAX_LAT              = 20 if not rx_buffer_enable else {20:6, 40:12, 80:24}[data_width],
            p_CLK_COR_MIN_LAT              = 18 if not rx_buffer_enable else {20:4, 40: 8, 80:16}[data_width],
            p_CLK_COR_PRECEDENCE           = "TRUE",
            p_CLK_COR_REPEAT_WAIT          = 0,
            p_CLK_COR_SEQ_1_1              = 0b0000000000,
            p_CLK_COR_SEQ_1_2              = 0b0000000000,
            p_CLK_COR_SEQ_1_3              = 0b0000000000,
            p_CLK_COR_SEQ_1_4              = 0b0000000000,
            p_CLK_COR_SEQ_1_ENABLE         = 0b1111,
            p_CLK_COR_SEQ_2_1              = 0b0000000000,
            p_CLK_COR_SEQ_2_2              = 0b0000000000,
            p_CLK_COR_SEQ_2_3              = 0b0000000000,
            p_CLK_COR_SEQ_2_4              = 0b0000000000,
            p_CLK_COR_SEQ_2_ENABLE         = 0b1111,
            p_CLK_COR_SEQ_2_USE            = "FALSE",
            p_CLK_COR_SEQ_LEN              = 1,
            p_CPLL_CFG0                    = 0b0000000111111010,
            p_CPLL_CFG1                    = 0b0000000000101011,
            p_CPLL_CFG2                    = 0b0000000000000010,
            p_CPLL_CFG3                    = 0b0000000000000000,
            p_CPLL_FBDIV                   = 1 if (use_qpll0 | use_qpll1) else pll.config["n2"],
            p_CPLL_FBDIV_45                = 4 if (use_qpll0 | use_qpll1) else pll.config["n1"],
            p_CPLL_INIT_CFG0               = 0b0000001010110010,
            p_CPLL_LOCK_CFG                = 0b0000000111101000,
            p_CPLL_REFCLK_DIV              = 1 if (use_qpll0 | use_qpll1) else pll.config["m"],
            p_CTLE3_OCAP_EXT_CTRL          = 0b000,
            p_CTLE3_OCAP_EXT_EN            = 0b0,
            p_DDI_CTRL                     = 0b00,
            p_DDI_REALIGN_WAIT             = 15,
            p_DEC_MCOMMA_DETECT            = "FALSE",
            p_DEC_PCOMMA_DETECT            = "FALSE",
            p_DEC_VALID_COMMA_ONLY         = "FALSE",
            p_DELAY_ELEC                   = 0b0,
            p_DMONITOR_CFG0                = 0b0000000000,
            p_DMONITOR_CFG1                = 0b00000000,
            p_ES_CLK_PHASE_SEL             = 0b0,
            p_ES_CONTROL                   = 0b000000,
            p_ES_ERRDET_EN                 = "FALSE",
            p_ES_EYE_SCAN_EN               = "FALSE",
            p_ES_HORZ_OFFSET               = 0b000000000000,
            p_ES_PRESCALE                  = 0b00000,
            p_ES_QUALIFIER0                = 0b0000000000000000,
            p_ES_QUALIFIER1                = 0b0000000000000000,
            p_ES_QUALIFIER2                = 0b0000000000000000,
            p_ES_QUALIFIER3                = 0b0000000000000000,
            p_ES_QUALIFIER4                = 0b0000000000000000,
            p_ES_QUALIFIER5                = 0b0000000000000000,
            p_ES_QUALIFIER6                = 0b0000000000000000,
            p_ES_QUALIFIER7                = 0b0000000000000000,
            p_ES_QUALIFIER8                = 0b0000000000000000,
            p_ES_QUALIFIER9                = 0b0000000000000000,
            p_ES_QUAL_MASK0                = 0b0000000000000000,
            p_ES_QUAL_MASK1                = 0b0000000000000000,
            p_ES_QUAL_MASK2                = 0b0000000000000000,
            p_ES_QUAL_MASK3                = 0b0000000000000000,
            p_ES_QUAL_MASK4                = 0b0000000000000000,
            p_ES_QUAL_MASK5                = 0b0000000000000000,
            p_ES_QUAL_MASK6                = 0b0000000000000000,
            p_ES_QUAL_MASK7                = 0b0000000000000000,
            p_ES_QUAL_MASK8                = 0b0000000000000000,
            p_ES_QUAL_MASK9                = 0b0000000000000000,
            p_ES_SDATA_MASK0               = 0b0000000000000000,
            p_ES_SDATA_MASK1               = 0b0000000000000000,
            p_ES_SDATA_MASK2               = 0b0000000000000000,
            p_ES_SDATA_MASK3               = 0b0000000000000000,
            p_ES_SDATA_MASK4               = 0b0000000000000000,
            p_ES_SDATA_MASK5               = 0b0000000000000000,
            p_ES_SDATA_MASK6               = 0b0000000000000000,
            p_ES_SDATA_MASK7               = 0b0000000000000000,
            p_ES_SDATA_MASK8               = 0b0000000000000000,
            p_ES_SDATA_MASK9               = 0b0000000000000000,
            p_EYESCAN_VP_RANGE             = 0b0,
            p_EYE_SCAN_SWAP_EN             = 0b0,
            p_FTS_DESKEW_SEQ_ENABLE        = 0b1111,
            p_FTS_LANE_DESKEW_CFG          = 0b1111,
            p_FTS_LANE_DESKEW_EN           = "FALSE",
            p_GEARBOX_MODE                 = 0b00000,
            p_ISCAN_CK_PH_SEL2             = 0b0,
            p_LOCAL_MASTER                 = 0b1,
            p_LPBK_BIAS_CTRL               = 4,
            p_LPBK_EN_RCAL_B               = 0b0,
            p_LPBK_EXT_RCAL                = 0b1000,
            p_LPBK_IND_CTRL0               = 5,
            p_LPBK_IND_CTRL1               = 5,
            p_LPBK_IND_CTRL2               = 5,
            p_LPBK_RG_CTRL                 = 2,
            p_OOBDIVCTL                    = 0b00,
            p_OOB_PWRUP                    = 0b0,
            p_PCI3_AUTO_REALIGN            = "OVR_1K_BLK",
            p_PCI3_PIPE_RX_ELECIDLE        = 0b0,
            p_PCI3_RX_ASYNC_EBUF_BYPASS    = 0b00,
            p_PCI3_RX_ELECIDLE_EI2_ENABLE  = 0b0,
            p_PCI3_RX_ELECIDLE_H2L_COUNT   = 0b000000,
            p_PCI3_RX_ELECIDLE_H2L_DISABLE = 0b000,
            p_PCI3_RX_ELECIDLE_HI_COUNT    = 0b000000,
            p_PCI3_RX_ELECIDLE_LP4_DISABLE = 0b0,
            p_PCI3_RX_FIFO_DISABLE         = 0b0,
            p_PCIE3_CLK_COR_EMPTY_THRSH    = 0b00000,
            p_PCIE3_CLK_COR_FULL_THRSH     = 0b010000,
            p_PCIE3_CLK_COR_MAX_LAT        = 0b00100,
            p_PCIE3_CLK_COR_MIN_LAT        = 0b00000,
            p_PCIE3_CLK_COR_THRSH_TIMER    = 0b001000,
            p_PCIE_64B_DYN_CLKSW_DIS       = "FALSE",
            p_PCIE_BUFG_DIV_CTRL           = 0b0001000000000000 if pll.config["linerate"] < 10e9 else
                                             0b0011010100000000,
            p_PCIE_GEN4_64BIT_INT_EN       = "FALSE",
            p_PCIE_PLL_SEL_MODE_GEN12      = 0b00 if pll.config["linerate"] < 10e9 else 0b10,
            p_PCIE_PLL_SEL_MODE_GEN3       = 0b11 if pll.config["linerate"] < 10e9 else 0b10,
            p_PCIE_PLL_SEL_MODE_GEN4       = 0b10 if pll.config["linerate"] < 10e9 else 0b10,
            p_PCIE_RXPCS_CFG_GEN3          = 0b0000101010100101,
            p_PCIE_RXPMA_CFG               = 0b0010100000001010,
            p_PCIE_TXPCS_CFG_GEN3          = 0b0010010010100100,
            p_PCIE_TXPMA_CFG               = 0b0010100000001010,
            p_PCS_PCIE_EN                  = "FALSE",
            p_PCS_RSVD0                    = 0b0000000000000000,
            p_PD_TRANS_TIME_FROM_P2        = 0b000000111100,
            p_PD_TRANS_TIME_NONE_P2        = 0b00011001,
            p_PD_TRANS_TIME_TO_P2          = 0b01100100,
            p_PREIQ_FREQ_BST               = 0 if pll.config["linerate"] < 15e9 else
                                             1 if pll.config["linerate"] < 20e9 else 2,
            p_RATE_SW_USE_DRP              = 0b1,
            p_RCLK_SIPO_DLY_ENB            = 0b0,
            p_RCLK_SIPO_INV_EN             = 0b0,
        )
        self.gty_params.update(
            p_RTX_BUF_CML_CTRL             = 0b011 if pll.config["linerate"] < 15e9 else
                                             0b101 if pll.config["linerate"] < 20e9 else
                                             0b110,
            p_RTX_BUF_TERM_CTRL            = 0b00,
            p_RXBUFRESET_TIME              = 0b00011,
            p_RXBUF_ADDR_MODE              = "FAST",
            p_RXBUF_EIDLE_HI_CNT           = 0b1000,
            p_RXBUF_EIDLE_LO_CNT           = 0b0000,
            p_RXBUF_EN                     = "TRUE" if rx_buffer_enable else "FALSE",
            p_RXBUF_RESET_ON_CB_CHANGE     = "TRUE",
            p_RXBUF_RESET_ON_COMMAALIGN    = "FALSE",
            p_RXBUF_RESET_ON_EIDLE         = "FALSE",
            p_RXBUF_RESET_ON_RATE_CHANGE   = "TRUE",
            p_RXBUF_THRESH_OVFLW           = 0 if not rx_buffer_enable else {20:61, 40:57, 80:49}[data_width],
            p_RXBUF_THRESH_OVRD            = "TRUE" if rx_buffer_enable else "FALSE",
            p_RXBUF_THRESH_UNDFLW          = 4 if not rx_buffer_enable else {20:1, 40:3, 80:7}[data_width],
            p_RXCDRFREQRESET_TIME          = 0b00001,
            p_RXCDRPHRESET_TIME            = 0b00001,
            p_RXCDR_CFG0                   = 0b0000000000000011,
            p_RXCDR_CFG0_GEN3              = 0b0000000000000011,
            p_RXCDR_CFG1                   = 0b0000000000000000,
            p_RXCDR_CFG1_GEN3              = 0b0000000000000000,
            p_RXCDR_CFG2                   = 0b0000001001101001 if data_width < 80 else 0b0000000111101001,
            p_RXCDR_CFG2_GEN2              = 0b1001101001,
            p_RXCDR_CFG2_GEN3              = 0b0000001001101001,
            p_RXCDR_CFG2_GEN4              = 0b0000000101100100,
            p_RXCDR_CFG3                   = 0b0000000000010010,
            p_RXCDR_CFG3_GEN2              = 0b010010,
            p_RXCDR_CFG3_GEN3              = 0b0000000000010010,
            p_RXCDR_CFG3_GEN4              = 0b0000000000010010,
            p_RXCDR_CFG4                   = 0b0101110011110110,
            p_RXCDR_CFG4_GEN3              = 0b0101110011110110,
            p_RXCDR_CFG5                   = 0b1011010001101011,
            p_RXCDR_CFG5_GEN3              = 0b0001010001101011,
            p_RXCDR_FR_RESET_ON_EIDLE      = 0b0,
            p_RXCDR_HOLD_DURING_EIDLE      = 0b0,
            p_RXCDR_LOCK_CFG0              = 0b0010001000000001,
            p_RXCDR_LOCK_CFG1              = 0b1001111111111111,
            p_RXCDR_LOCK_CFG2              = 0b000000000000000,
            p_RXCDR_LOCK_CFG3              = 0b0000000000000000,
            p_RXCDR_LOCK_CFG4              = 0b0000000000000000,
            p_RXCDR_PH_RESET_ON_EIDLE      = 0b0,
            p_RXCFOK_CFG0                  = 0b0000000000000000,
            p_RXCFOK_CFG1                  = 0b1000000000010101,
            p_RXCFOK_CFG2                  = 0b0000001010101110,
            p_RXCKCAL1_IQ_LOOP_RST_CFG     = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXCKCAL1_I_LOOP_RST_CFG      = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXCKCAL1_Q_LOOP_RST_CFG      = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXCKCAL2_DX_LOOP_RST_CFG     = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXCKCAL2_D_LOOP_RST_CFG      = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXCKCAL2_S_LOOP_RST_CFG      = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXCKCAL2_X_LOOP_RST_CFG      = 0b0000000000000000 if pll.config["linerate"] < 20e9 else 0b0000000000000100,
            p_RXDFELPMRESET_TIME           = 0b0001111,
            p_RXDFELPM_KL_CFG0             = 0b000000000000000,
            p_RXDFELPM_KL_CFG1             = 0b1010000010000010,
            p_RXDFELPM_KL_CFG2             = 0b0000000100000000,
            p_RXDFE_CFG0                   = 0b0000101000000000,
            p_RXDFE_CFG1                   = 0b0000000000000000,
            p_RXDFE_GC_CFG0                = 0b0000000000000000,
            p_RXDFE_GC_CFG1                = 0b1000000000000000,
            p_RXDFE_GC_CFG2                = 0b1111111111100000,
            p_RXDFE_H2_CFG0                = 0b0000000000000000,
            p_RXDFE_H2_CFG1                = 0b0000000000000010,
            p_RXDFE_H3_CFG0                = 0b0000000000000000,
            p_RXDFE_H3_CFG1                = 0b1000000000000010,
            p_RXDFE_H4_CFG0                = 0b0000000000000000,
            p_RXDFE_H4_CFG1                = 0b1000000000000010,
            p_RXDFE_H5_CFG0                = 0b0000000000000000,
            p_RXDFE_H5_CFG1                = 0b1000000000000010,
            p_RXDFE_H6_CFG0                = 0b0000000000000000,
            p_RXDFE_H6_CFG1                = 0b1000000000000010,
            p_RXDFE_H7_CFG0                = 0b0000000000000000,
            p_RXDFE_H7_CFG1                = 0b1000000000000010,
            p_RXDFE_H8_CFG0                = 0b0000000000000000,
            p_RXDFE_H8_CFG1                = 0b1000000000000010,
            p_RXDFE_H9_CFG0                = 0b0000000000000000,
            p_RXDFE_H9_CFG1                = 0b1000000000000010,
            p_RXDFE_HA_CFG0                = 0b0000000000000000,
            p_RXDFE_HA_CFG1                = 0b1000000000000010,
            p_RXDFE_HB_CFG0                = 0b0000000000000000,
            p_RXDFE_HB_CFG1                = 0b1000000000000010,
            p_RXDFE_HC_CFG0                = 0b0000000000000000,
            p_RXDFE_HC_CFG1                = 0b1000000000000010,
            p_RXDFE_HD_CFG0                = 0b0000000000000000,
            p_RXDFE_HD_CFG1                = 0b1000000000000010,
            p_RXDFE_HE_CFG0                = 0b0000000000000000,
            p_RXDFE_HE_CFG1                = 0b1000000000000010,
            p_RXDFE_HF_CFG0                = 0b0000000000000000,
            p_RXDFE_HF_CFG1                = 0b1000000000000010,
            p_RXDFE_KH_CFG0                = 0b1000000000000000,
            p_RXDFE_KH_CFG1                = 0b1111111000000000,
            p_RXDFE_KH_CFG2                = 0b0000001000000000 if pll.config["linerate"] < 20e9 else 0b0010100000011100,
            p_RXDFE_KH_CFG3                = 0b0100000100000001 if pll.config["linerate"] < 20e9 else 0b0100000100100000,
            p_RXDFE_OS_CFG0                = 0b0010000000000000,
            p_RXDFE_OS_CFG1                = 0b1000000000000000,
            p_RXDFE_UT_CFG0                = 0b0000000000000000,
            p_RXDFE_UT_CFG1                = 0b0000000000000011,
            p_RXDFE_UT_CFG2                = 0b0000000000000000,
            p_RXDFE_VP_CFG0                = 0b0000000000000000,
            p_RXDFE_VP_CFG1                = 0b0000000000110011,
            p_RXDLY_CFG                    = 0b0000000000010000,
            p_RXDLY_LCFG                   = 0b0000000000110000,
            p_RXELECIDLE_CFG               = "SIGCFG_4",
            p_RXGBOX_FIFO_INIT_RD_ADDR     = 3 if data_width == 80 else 4,
            p_RXGEARBOX_EN                 = "FALSE",
            p_RXISCANRESET_TIME            = 0b00001,
            p_RXLPM_CFG                    = 0b0000000000000000,
            p_RXLPM_GC_CFG                 = 0b1111100000000000,
            p_RXLPM_KH_CFG0                = 0b0000000000000000,
            p_RXLPM_KH_CFG1                = 0b1010000000000010,
            p_RXLPM_OS_CFG0                = 0b0000000000000000,
            p_RXLPM_OS_CFG1                = 0b1000000000000010,
            p_RXOOB_CFG                    = 0b000000110,
            p_RXOOB_CLK_CFG                = "PMA",
            p_RXOSCALRESET_TIME            = 0b00011,
            p_RXOUT_DIV                    = pll.config["d"],
            p_RXPCSRESET_TIME              = 0b00011,
            p_RXPHBEACON_CFG               = 0b0000000000000000,
            p_RXPHDLY_CFG                  = 0b0010000001110000,
            p_RXPHSAMP_CFG                 = 0b0010000100000000,
            p_RXPHSLIP_CFG                 = 0b1001100100110011,
            p_RXPH_MONITOR_SEL             = 0b00000,
            p_RXPI_CFG0                    = 0b0000001100000001 if use_cpll else
                                             0b0000000100000000 if pll.config["linerate"] < 15e9 else
                                             0b0011000000000010 if pll.config["linerate"] < 20e9 else
                                             0b0011000000000100,
            p_RXPI_CFG1                    = 0b0000000011111100 if use_cpll else
                                             0b0000000001010100 if pll.config["linerate"] < 20e9 else
                                             0b0000000000000000,
            p_RXPMACLK_SEL                 = "DATA",
            p_RXPMARESET_TIME              = 0b00011,
            p_RXPRBS_ERR_LOOPBACK          = 0b0,
            p_RXPRBS_LINKACQ_CNT           = 15,
            p_RXREFCLKDIV2_SEL             = 0b0,
            p_RXSLIDE_AUTO_WAIT            = 7,
            p_RXSLIDE_MODE                 = "OFF",
            p_RXSYNC_MULTILANE             = 0b0,
            p_RXSYNC_OVRD                  = 0b0,
            p_RXSYNC_SKIP_DA               = 0b0,
            p_RX_AFE_CM_EN                 = 0b0,
            p_RX_BIAS_CFG0                 = 0b0001001010110000,
            p_RX_BUFFER_CFG                = 0b000000,
            p_RX_CAPFF_SARC_ENB            = 0b0,
            p_RX_CLK25_DIV                 = 7,
            p_RX_CLKMUX_EN                 = 0b1,
            p_RX_CLK_SLIP_OVRD             = 0b00000,
            p_RX_CM_BUF_CFG                = 0b1010,
            p_RX_CM_BUF_PD                 = 0b0,
            p_RX_CM_SEL                    = 0b11,
            p_RX_CM_TRIM                   = 0b1010,
            p_RX_CTLE_PWR_SAVING           = 0b0,
            p_RX_CTLE_RES_CTRL             = 0b0000,
            p_RX_DATA_WIDTH                = data_width,
            p_RX_DDI_SEL                   = 0b000000,
            p_RX_DEFER_RESET_BUF_EN        = "TRUE",
            p_RX_DEGEN_CTRL                = 0b111,
            p_RX_DFELPM_CFG0               = 10,
            p_RX_DFELPM_CFG1               = 0b1,
            p_RX_DFELPM_KLKH_AGC_STUP_EN   = 0b1,
            p_RX_DFE_AGC_CFG1              = 0b100,
            p_RX_DFE_KL_LPM_KH_CFG0        = 3,
            p_RX_DFE_KL_LPM_KH_CFG1        = 2,
            p_RX_DFE_KL_LPM_KL_CFG0        = 0b11,
            p_RX_DFE_KL_LPM_KL_CFG1        = 2,
            p_RX_DFE_LPM_HOLD_DURING_EIDLE = 0b0,
            p_RX_DISPERR_SEQ_MATCH         = "TRUE",
            p_RX_DIVRESET_TIME             = 0b00001,
            p_RX_EN_CTLE_RCAL_B            = 0b0,
            p_RX_EN_SUM_RCAL_B             = 0,
            p_RX_EYESCAN_VS_CODE           = 0b0000000,
            p_RX_EYESCAN_VS_NEG_DIR        = 0b0,
            p_RX_EYESCAN_VS_RANGE          = 0b10,
            p_RX_EYESCAN_VS_UT_SIGN        = 0b0,
            p_RX_FABINT_USRCLK_FLOP        = 0b0,
            p_RX_I2V_FILTER_EN             = 0b1,
            p_RX_INT_DATAWIDTH             = 0 if data_width == 20 else 1 if data_width == 40 else 2,
            p_RX_PMA_POWER_SAVE            = 0b0,
            p_RX_PMA_RSV0                  = 0b0000000000101111,
            p_RX_PROGDIV_CFG               = 0.0,
            p_RX_PROGDIV_RATE              = 0b0000000000000001,
            p_RX_RESLOAD_CTRL              = 0b0000,
            p_RX_RESLOAD_OVRD              = 0b0,
            p_RX_SAMPLE_PERIOD             = 0b111,
            p_RX_SIG_VALID_DLY             = 11,
            p_RX_SUM_DEGEN_AVTT_OVERITE    = 1,
            p_RX_SUM_DFETAPREP_EN          = 0b0,
            p_RX_SUM_IREF_TUNE             = 0b0000,
            p_RX_SUM_RES_CTRL              = 0b00,
            p_RX_SUM_VCMTUNE               = 0b1001,
            p_RX_SUM_VCM_BIAS_TUNE_EN      = 0b1,
            p_RX_SUM_VCM_OVWR              = 0b0,
            p_RX_SUM_VREF_TUNE             = 0b100,
            p_RX_TUNE_AFE_OS               = 0b10,
            p_RX_VREG_CTRL                 = 0b010,
            p_RX_VREG_PDB                  = 0b1,
            p_RX_WIDEMODE_CDR              = 0b10 if data_width == 80 else 0b00,
            p_RX_WIDEMODE_CDR_GEN3         = 0b00,
            p_RX_WIDEMODE_CDR_GEN4         = 0b01,
            p_RX_XCLK_SEL                  = "RXDES" if rx_buffer_enable else "RXUSR",
            p_RX_XMODE_SEL                 = 0b1 if pll.config["linerate"] < 15e9 else 0b0,
            p_SAMPLE_CLK_PHASE             = 0b0,
            p_SAS_12G_MODE                 = 0b0,
            p_SATA_BURST_SEQ_LEN           = 0b1111,
            p_SATA_BURST_VAL               = 0b100,
            p_SATA_CPLL_CFG                = "VCO_3000MHZ",
            p_SATA_EIDLE_VAL               = 0b100,
            p_SHOW_REALIGN_COMMA           = "TRUE",
            p_SIM_DEVICE                   = "ULTRASCALE_PLUS",
            p_SIM_MODE                     = "FAST",
            p_SIM_RECEIVER_DETECT_PASS     = "TRUE",
            p_SIM_RESET_SPEEDUP            = "TRUE",
            p_SIM_TX_EIDLE_DRIVE_LEVEL     = "Z",
            p_SRSTMODE                     = 0,
            p_TAPDLY_SET_TX                = 0b00,
            p_TERM_RCAL_CFG                = 0b100001000000010,
            p_TERM_RCAL_OVRD               = 0b001,
            p_TRANS_TIME_RATE              = 0b00001110,
            p_TST_RSV0                     = 0b00000000,
            p_TST_RSV1                     = 0b00000000,
            p_USB_POLL_SATA_MAX_BURST      = 8,
            p_USB_POLL_SATA_MIN_BURST      = 4,
            p_USB_U1_SATA_MAX_WAKE         = 7,
            p_USB_U1_SATA_MIN_WAKE         = 4,
            p_USB_PING_SATA_MIN_INIT       = 12,
            p_USB_PING_SATA_MAX_INIT       = 21,
            p_USB_U2_SAS_MAX_COM           = 64,
            p_USB_U2_SAS_MIN_COM           = 36,
        )
        self.gty_params.update(
            p_TXBUF_EN                   = "TRUE" if tx_buffer_enable else "FALSE",
            p_TXBUF_RESET_ON_RATE_CHANGE = "TRUE",
            p_TXDLY_CFG                  = 0b1000000000010000,
            p_TXDLY_LCFG                 = 0b0000000000110000,
            p_TXDRV_FREQBAND             = 0b0 if pll.config["linerate"] < 15e9 else 0b1,
            p_TXFE_CFG0                  = 0b0000001111000010,
            p_TXFE_CFG1                  = 0b0110110000000000 if pll.config["linerate"] < 15e9 else
                                           0b1010101000000000,
            p_TXFE_CFG2                  = 0b0110110000000000 if pll.config["linerate"] < 15e9 else
                                           0b1010101000000000,
            p_TXFE_CFG3                  = 0b0110110000000000 if pll.config["linerate"] < 15e9 else
                                           0b1010101000000000,
            p_TXFIFO_ADDR_CFG            = "LOW",
            p_TXGBOX_FIFO_INIT_RD_ADDR   = 4,
            p_TXGEARBOX_EN               = "FALSE",
            p_TXOUT_DIV                  = pll.config["d"],
            p_TXPCSRESET_TIME            = 0b00011,
            p_TXPHDLY_CFG0               = 0b0110000001110000,
            p_TXPHDLY_CFG1               = 0b0000000000001111,
            p_TXPH_CFG                   = 0b0000011100100011 if (data_width == 80) | (not tx_buffer_enable) else
                                           0b0000001100100011,
            p_TXPH_CFG2                  = 0b0000000000000000,
            p_TXPH_MONITOR_SEL           = 0b00000,
            p_TXPI_CFG0                  = 0b0000001100000000 if pll.config["linerate"] < 15e9 else
                                           0b0011000100000000 if pll.config["linerate"] < 20e9 else
                                           0b0011000000000000,
            p_TXPI_CFG1                  = 0b0111010101010101 if use_cpll else
                                           0b0001000000000000 if pll.config["linerate"] < 15e9 else
                                           0b0000000000000000,
            p_TXPI_GRAY_SEL              = 0b0,
            p_TXPI_INVSTROBE_SEL         = 0b0,
            p_TXPI_PPM                   = 0b0,
            p_TXPI_PPM_CFG               = 0b00000000,
            p_TXPI_SYNFREQ_PPM           = 0b001,
            p_TXPMARESET_TIME            = 0b00011,
            p_TXREFCLKDIV2_SEL           = 0b0,
            p_TXSWBST_BST                = 0b1,
            p_TXSWBST_EN                 = 0b0,
            p_TXSWBST_MAG                = 4,
            p_TXSYNC_MULTILANE           = 0b0,
            p_TXSYNC_OVRD                = 0b0,
            p_TXSYNC_SKIP_DA             = 0b0,
            p_TX_CLK25_DIV               = 7,
            p_TX_CLKMUX_EN               = 0b1,
            p_TX_DATA_WIDTH              = data_width,
            p_TX_DCC_LOOP_RST_CFG        = 0b0000000000000100,
            p_TX_DEEMPH0                 = 0b000000,
            p_TX_DEEMPH1                 = 0b000000,
            p_TX_DEEMPH2                 = 0b000000,
            p_TX_DEEMPH3                 = 0b000000,
            p_TX_DIVRESET_TIME           = 0b00001,
            p_TX_DRIVE_MODE              = "DIRECT",
            p_TX_EIDLE_ASSERT_DELAY      = 0b100,
            p_TX_EIDLE_DEASSERT_DELAY    = 0b011,
			p_TX_FABINT_USRCLK_FLOP      = 0b0,
            p_TX_FIFO_BYP_EN             = 0 if tx_buffer_enable else 1,
            p_TX_IDLE_DATA_ZERO          = 0b0,
            p_TX_INT_DATAWIDTH           = 0 if data_width == 20 else 1 if data_width == 40 else 2,
            p_TX_LOOPBACK_DRIVE_HIZ      = "FALSE",
            p_TX_MAINCURSOR_SEL          = 0b0,
            p_TX_MARGIN_FULL_0           = 0b1011000,
            p_TX_MARGIN_FULL_1           = 0b1010111,
            p_TX_MARGIN_FULL_2           = 0b1010101,
            p_TX_MARGIN_FULL_3           = 0b1010011,
            p_TX_MARGIN_FULL_4           = 0b1010001,
            p_TX_MARGIN_LOW_0            = 0b1001100,
            p_TX_MARGIN_LOW_1            = 0b1001011,
            p_TX_MARGIN_LOW_2            = 0b1001000,
            p_TX_MARGIN_LOW_3            = 0b1000010,
            p_TX_MARGIN_LOW_4            = 0b1000000,
            p_TX_PHICAL_CFG0             = 0b0000000000100000,
            p_TX_PHICAL_CFG1             = 0b0000000001000000,
            p_TX_PI_BIASSET              = 0 if pll.config["linerate"] < 15e9 else
                                           1 if pll.config["linerate"] < 20e9 else 2,
            p_TX_PMADATA_OPT             = 0b0,
            p_TX_PMA_POWER_SAVE          = 0b0,
            p_TX_PMA_RSV0                = 0b0000000000000000,
            p_TX_PMA_RSV1                = 0b0000000000000000,
            p_TX_PROGCLK_SEL             = "PREPI",
            p_TX_PROGDIV_CFG             = data_width*pll.config["d"]/2,
            p_TX_PROGDIV_RATE            = 0b0000000000000001,
            p_TX_RXDETECT_CFG            = 0b00000000110010,
            p_TX_RXDETECT_REF            = 5,
            p_TX_SAMPLE_PERIOD           = 0b111,
            p_TX_SW_MEAS                 = 0b00,
            p_TX_VREG_CTRL               = 0b011,
            p_TX_VREG_PDB                = 0b1,
            p_TX_VREG_VREFSEL            = 0b10,
            p_TX_XCLK_SEL                = "TXOUT" if tx_buffer_enable else "TXUSR",
            p_USE_PCS_CLK_PHASE_SEL      = 0b0,
            p_Y_ALL_MODE                 = 0b0,

            p_USB_BOTH_BURST_IDLE        = 0b0,
            p_USB_BURSTMAX_U3WAKE        = 0b1111111,
            p_USB_BURSTMIN_U3WAKE        = 0b1100011,
            p_USB_CLK_COR_EQ_EN          = 0b0,
            p_USB_EXT_CNTL               = 0b1,
            p_USB_IDLEMAX_POLLING        = 0b1010111011,
            p_USB_IDLEMIN_POLLING        = 0b0100101011,
            p_USB_LFPSPING_BURST         = 0b000000101,
            p_USB_LFPSPOLLING_BURST      = 0b000110001,
            p_USB_LFPSPOLLING_IDLE_MS    = 0b000000100,
            p_USB_LFPSU1EXIT_BURST       = 0b000011101,
            p_USB_LFPSU2LPEXIT_BURST_MS  = 0b001100011,
            p_USB_LFPSU3WAKE_BURST_MS    = 0b111110011,
            p_USB_LFPS_TPERIOD           = 0b0011,
            p_USB_LFPS_TPERIOD_ACCURATE  = 0b1,
            p_USB_MODE                   = 0b0,
            p_USB_PCIE_ERR_REP_DIS       = 0b0,
            p_USB_PING_SATA_MAX_INIT     = 21,
            p_USB_PING_SATA_MIN_INIT     = 12,
            p_USB_POLL_SATA_MAX_BURST    = 8,
            p_USB_POLL_SATA_MIN_BURST    = 4,
            p_USB_RAW_ELEC               = 0b0,
            p_USB_RXIDLE_P0_CTRL         = 0b1,
            p_USB_TXIDLE_TUNE_ENABLE     = 0b1,
            p_USB_U1_SATA_MAX_WAKE       = 7,
            p_USB_U1_SATA_MIN_WAKE       = 4,
            p_USB_U2_SAS_MAX_COM         = 64,
            p_USB_U2_SAS_MIN_COM         = 36,
        )
        self.gty_params.update(
            # Reset modes
            i_GTTXRESETSEL    = 0,
            i_GTRXRESETSEL    = 0,
            i_RESETOVRD       = 0,

            # DRP
            i_DRPADDR         = drp_mux.addr,
            i_DRPCLK          = drp_mux.clk,
            i_DRPDI           = drp_mux.di,
            o_DRPDO           = drp_mux.do,
            i_DRPEN           = drp_mux.en,
            o_DRPRDY          = drp_mux.rdy,
            i_DRPWE           = drp_mux.we,

            # CPLL
            i_GTREFCLK0       = 0 if (use_qpll0 | use_qpll1) else pll.refclk,
            i_GTREFCLK1       = 0,
            i_CPLLRESET       = 0,
            i_CPLLPD          = 0 if (use_qpll0 | use_qpll1) else pll.reset,
            o_CPLLLOCK        = Signal() if (use_qpll0 | use_qpll1) else pll.lock,
            i_CPLLLOCKEN      = 1,
            i_CPLLREFCLKSEL   = 0b001,
            i_TSTIN           = 2**20-1,
            i_CPLLFREQLOCK    = 0,
            i_CPLLLOCKDETCLK  = 0,

            # QPLL
            i_QPLL0CLK        = 0 if (use_cpll | use_qpll1) else pll.clk,
            i_QPLL0REFCLK     = 0 if (use_cpll | use_qpll1) else pll.refclk,
            i_QPLL1CLK        = 0 if (use_cpll | use_qpll0) else pll.clk,
            i_QPLL1REFCLK     = 0 if (use_cpll | use_qpll0) else pll.refclk,
            i_QPLL0FREQLOCK   = 0,
            i_QPLL1FREQLOCK   = 0,

            # 8B10B
            i_RX8B10BEN       = 0,
            i_TX8B10BEN       = 0,

            # TX clock
            i_TXRATE          = 0b000,
            o_TXOUTCLK        = self.txoutclk,
            i_TXSYSCLKSEL     = 0b00 if use_cpll else 0b10 if use_qpll0 else 0b11,
            i_TXPLLCLKSEL     = 0b00 if use_cpll else 0b11 if use_qpll0 else 0b10,
            i_TXOUTCLKSEL     = 0b010 if tx_buffer_enable else 0b101,

            # TX Startup/Reset
            i_GTTXRESET       = tx_init.gtXxreset,
            i_TXPMARESET      = 0,
            i_TXPCSRESET      = 0,
            o_TXRESETDONE     = tx_init.Xxresetdone,
            i_TXPHDLYRESET    = 0,
            i_TXDLYSRESET     = tx_init.Xxdlysreset,
            o_TXDLYSRESETDONE = tx_init.Xxdlysresetdone,
            i_TXPHALIGN       = 0,
            i_TXPHALIGNEN     = 0,
            i_TXPHINIT        = 0,
            o_TXPHINITDONE    = 0,
            o_TXPHALIGNDONE   = tx_init.Xxphaligndone,
            i_TXUSERRDY       = tx_init.Xxuserrdy,
            i_TXPHDLYPD       = 1 if tx_buffer_enable else 0,
            i_TXPHOVRDEN      = 0,
            i_TXMAINCURSOR    = 0x50,
            i_TXSYNCMODE      = 1,

            # TX Buffer bypass
            i_TXDLYBYPASS     = 1 if tx_buffer_enable else 0,
            i_TXDLYEN         = 0,

            # TX data
            i_TXCTRL0         = Cat(*[txdata[10*i+8] for i in range(nwords)]),
            i_TXCTRL1         = Cat(*[txdata[10*i+9] for i in range(nwords)]),
            i_TXDATA          = Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
            i_TXUSRCLK        = ClockSignal("tx"),
            i_TXUSRCLK2       = ClockSignal("tx"),

            # TXPI
            i_TXPIPPMEN       = 0,
            i_TXPIPPMOVRDEN   = 0,
            i_TXPIPPMPD       = 0 if tx_buffer_enable else 1,
            i_TXPIPPMSEL      = 1 if tx_buffer_enable else 0,
            i_TXPIPPMSTEPSIZE = 0b00000,
            i_TXPISOPD        = 0,


            # TX electrical
            i_TXPD            = 0b00,
            i_TXDIFFCTRL      = 0b11000,
            i_TXINHIBIT       = self.tx_inhibit,

            # Internal Loopback
            i_LOOPBACK        = self.loopback,

            # RX Startup/Reset
            i_GTRXRESET       = rx_init.gtXxreset,
            i_RXPMARESET      = 0,
            i_RXPCSRESET      = 0,
            o_RXRESETDONE     = rx_init.Xxresetdone,
            i_RXDLYSRESET     = rx_init.Xxdlysreset,
            o_RXPHALIGNDONE   = rxphaligndone,
            i_RXSYNCALLIN     = rxphaligndone,
            i_RXUSERRDY       = rx_init.Xxuserrdy,
            i_RXSYNCIN        = 0,
            i_RXSYNCMODE      = 1,
            o_RXSYNCDONE      = rx_init.Xxsyncdone,
            i_RXDLYBYPASS     = 1 if rx_buffer_enable else 0,
            i_RXPHDLYPD       = 1 if rx_buffer_enable else 0,
            i_RXBUFRESET      = 0,
            i_RXDLYEN         = 0,
            o_GTPOWERGOOD     = Open(),

            # CDR
            i_RXCDRFREQRESET   = 0,
            i_RXCDRHOLD        = 1 if self.loopback == 0b001 else 0,
            i_RXCDROVRDEN      = 0,
            i_RXCDRRESET       = 0,
            i_RXCHBONDEN       = 0,

            # COMMA DETECT
            i_RXCOMMADETEN     = 0,
            i_RXMCOMMAALIGNEN  = 0,
            i_RXPCOMMAALIGNEN  = 0,

            # RX AFE
            i_RXDFEXYDEN       = 1,
            i_RXLPMEN          = 1,

            # RX clock
            i_RXRATE          = 0b000,
            i_RXSYSCLKSEL     = 0b00 if use_cpll else 0b10 if use_qpll0 else 0b11,
            i_RXOUTCLKSEL     = 0b010,
            i_RXPLLCLKSEL     = 0b00 if use_cpll else 0b11 if use_qpll0 else 0b10,
            o_RXOUTCLK        = self.rxoutclk,
            i_RXUSRCLK        = ClockSignal("rx"),
            i_RXUSRCLK2       = ClockSignal("rx"),

            # RX data
            o_RXCTRL0         = Cat(*[rxdata[10*i+8] for i in range(nwords)]),
            o_RXCTRL1         = Cat(*[rxdata[10*i+9] for i in range(nwords)]),
            o_RXDATA          = Cat(*[rxdata[10*i:10*i+8] for i in range(nwords)]),

            # RX electrical
            i_RXPD            = 0b00,
            i_RXELECIDLEMODE  = 0b11,

            # Polarity
            i_TXPOLARITY      = tx_polarity,
            i_RXPOLARITY      = rx_polarity,

            # Pads
            i_GTYRXP          = rx_pads.p,
            i_GTYRXN          = rx_pads.n,
            o_GTYTXP          = tx_pads.p,
            o_GTYTXN          = tx_pads.n
        )

        # TX clocking ------------------------------------------------------------------------------
        tx_reset_deglitched = Signal()
        tx_reset_deglitched.attr.add("no_retiming")
        self.sync += tx_reset_deglitched.eq(~tx_init.done)
        self.clock_domains.cd_tx = ClockDomain()
        if not tx_buffer_enable:
            tx_bufg_div = pll.config["clkin"]/self.tx_clk_freq
        else:
            tx_bufg_div = 1
        assert tx_bufg_div == int(tx_bufg_div)
        self.specials += [
            Instance("BUFG_GT", i_I=self.txoutclk, o_O=self.cd_tx.clk,
                i_DIV=int(tx_bufg_div)-1),
            AsyncResetSynchronizer(self.cd_tx, tx_reset_deglitched)
        ]

        # RX clocking ------------------------------------------------------------------------------
        rx_reset_deglitched = Signal()
        rx_reset_deglitched.attr.add("no_retiming")
        self.sync.tx += rx_reset_deglitched.eq(~rx_init.done)
        self.clock_domains.cd_rx = ClockDomain()
        self.specials += [
            Instance("BUFG_GT", i_I=self.rxoutclk, o_O=self.cd_rx.clk),
            AsyncResetSynchronizer(self.cd_rx, rx_reset_deglitched)
        ]

        # TX Datapath and PRBS ---------------------------------------------------------------------
        self.submodules.tx_prbs = ClockDomainsRenamer("tx")(PRBSTX(data_width, reverse=True))
        self.comb += self.tx_prbs.config.eq(tx_prbs_config)
        self.comb += [
            self.tx_prbs.i.eq(Cat(*[self.encoder.output[i] for i in range(nwords)])),
            If(tx_produce_square_wave,
                # square wave @ linerate/data_width for scope observation
                txdata.eq(Signal(data_width, reset=(1<<(data_width//2))-1))
            ).Elif(tx_produce_pattern,
                txdata.eq(tx_pattern)
            ).Else(
                txdata.eq(self.tx_prbs.o)
            )
        ]

        # RX Datapath and PRBS ---------------------------------------------------------------------
        self.submodules.rx_prbs = ClockDomainsRenamer("rx")(PRBSRX(data_width, reverse=True))
        self.comb += [
            self.rx_prbs.config.eq(rx_prbs_config),
            self.rx_prbs.pause.eq(rx_prbs_pause),
            rx_prbs_errors.eq(self.rx_prbs.errors)
        ]
        for i in range(nwords):
            self.comb += self.decoders[i].input.eq(rxdata[10*i:10*(i+1)])
        self.comb += self.rx_prbs.i.eq(rxdata)

        # Clock Aligner ----------------------------------------------------------------------------
        if clock_aligner:
            clock_aligner = BruteforceClockAligner(clock_aligner_comma, self.tx_clk_freq)
            self.submodules.clock_aligner = clock_aligner
            ps_restart = PulseSynchronizer("tx", "sys")
            self.submodules += ps_restart
            self.comb += [
                clock_aligner.rxdata.eq(rxdata),
                ps_restart.i.eq(clock_aligner.restart),
                rx_init.restart.eq((ps_restart.o & self.rx_align) | ~self.rx_enable),
                self.rx_ready.eq(clock_aligner.ready)
            ]

    def add_stream_endpoints(self):
        self.sink   =   sink = stream.Endpoint([("data", self.nwords*8), ("ctrl", self.nwords)])
        self.source = source = stream.Endpoint([("data", self.nwords*8), ("ctrl", self.nwords)])

        self.comb += sink.ready.eq(1)
        self.comb += source.valid.eq(1)
        for i in range(self.nwords):
            self.comb += [
                self.encoder.k[i].eq(sink.ctrl[i]),
                self.encoder.d[i].eq(sink.data[8*i:8*(i+1)]),
                source.ctrl[i].eq(self.decoders[i].k),
                source.data[8*i:8*(i+1)].eq(self.decoders[i].d),
            ]

    def add_base_control(self, auto_enable=True):
        if hasattr(self, "clock_aligner"):
            self._clock_aligner_disable  = CSRStorage(fields=[
                CSRField("disable", size=1, values=[
                    ("``0b0``", "Clock aligner enabled."),
                    ("``0b1``", "Clock aligner disabled.")
                ])
            ])
        self._tx_enable = CSRStorage(fields=[
                CSRField("enable", size=1, values=[
                    ("``0b0``", "TX disabled."),
                    ("``0b1``", "TX enabled.")
                ], reset=int(auto_enable))
            ])
        self._tx_ready = CSRStatus(fields=[
                CSRField("ready", size=1, values=[
                    ("``0b0``", "TX not initialized."),
                    ("``0b1``", "TX initialized and ready.")
                ])
            ])
        self._tx_inhibit = CSRStorage(fields=[
                CSRField("inhibit", size=1, values=[
                    ("``0b0``", "Normal operation."),
                    ("``0b1``", "TX inhibited.")
                ])
            ])
        self._tx_produce_square_wave = CSRStorage(fields=[
                CSRField("enable", size=1, values=[
                    ("``0b0``", "Normal operation."),
                    ("``0b1``", "TX square wave genration enabled (linerate observation/checks).")
                ])
            ])
        self._rx_enable = CSRStorage(fields=[
                CSRField("enable", size=1, values=[
                    ("``0b0``", "RX disabled."),
                    ("``0b1``", "RX enabled.")
                ], reset=int(auto_enable))
            ])
        self._rx_ready = CSRStatus(fields=[
                CSRField("ready", size=1, values=[
                    ("``0b0``", "RX not initialized."),
                    ("``0b1``", "RX initialized and ready.")
                ])
            ])
        if hasattr(self, "clock_aligner"):
            self.comb += self.clock_aligner.disable.eq(self._clock_aligner_disable.fields.disable)
        self.comb += [
            self.tx_enable.eq(self._tx_enable.fields.enable),
            self._tx_ready.fields.ready.eq(self.tx_ready),
            self.tx_inhibit.eq(self._tx_inhibit.fields.inhibit),
            self.tx_produce_square_wave.eq(self._tx_produce_square_wave.fields.enable),
            self.rx_enable.eq(self._rx_enable.fields.enable),
            self._rx_ready.fields.ready.eq(self.rx_ready),
        ]

    def add_prbs_control(self):
        self._tx_prbs_config = CSRStorage(fields=[
            CSRField("config", size=2, values=[
                ("``0b00``", "PRBS   Disabled."),
                ("``0b01``", "PRBS7  Enabled."),
                ("``0b10``", "PRBS15 Enabled."),
                ("``0b11``", "PRBS31 Enabled."),
            ])
        ])
        self._rx_prbs_config = CSRStorage(fields=[
            CSRField("config", size=2, values=[
                ("``0b00``", "PRBS   Disabled."),
                ("``0b01``", "PRBS7  Enabled."),
                ("``0b10``", "PRBS15 Enabled."),
                ("``0b11``", "PRBS31 Enabled."),
            ]),
            CSRField("pause", size=1, description="Pause RX PRBS."),
        ])
        self._rx_prbs_errors = CSRStatus(32, description="RX PRBS errors.")
        self.comb += [
            self.tx_prbs_config.eq(self._tx_prbs_config.fields.config),
            self.rx_prbs_config.eq(self._rx_prbs_config.fields.config),
            self.rx_prbs_pause.eq(self._rx_prbs_config.fields.pause),
            self._rx_prbs_errors.status.eq(self.rx_prbs_errors)
        ]

    def add_loopback_control(self):
        self._loopback = CSRStorage(fields=[
            CSRField("config", size=3, values=[
                ("``0b000``", "Normal operation."),
                ("``0b001``", "Near-End PCS Loopback."),
                ("``0b010``", "Near-End PMA Loopback."),
                ("``0b100``", "Far-End PMA Loopback."),
                ("``0b110``", "Far-End PCS Loopback."),
            ])
        ])
        self.comb += self.loopback.eq(self._loopback.fields.config)

    def add_polarity_control(self):
        self._tx_polarity  = CSRStorage(fields=[
            CSRField("swap", size=1, values=[
                ("``0b0``", "Normal operation."),
                ("``0b1``", "TX polarity swap (equivalent to P/N swap)."),
            ])
        ])
        self._rx_polarity  = CSRStorage(fields=[
            CSRField("swap", size=1, values=[
                ("``0b0``", "Normal operation."),
                ("``0b1``", "RX polarity swap (equivalent to P/N swap)."),
            ])
        ])
        self.gty_params.update(
            i_TXPOLARITY = self._tx_polarity.fields.swap,
            i_RXPOLARITY = self._rx_polarity.fields.swap,
        )

    def add_electrical_control(self):
        self._tx_diffctrl       = CSRStorage(5, reset=0b11000, description="TX Driver Swing Control, see UG578.")
        self._tx_postcursor     = CSRStorage(5, reset=0b00000, description="TX Post Cursor Pre-emphasis Control, see UG578.")
        self._tx_precursor      = CSRStorage(5, reset=0b00000, description="TX Pre Cursor Pre-emphasis Control, see UG578.")
        self.gty_params.update(
            i_TXDIFFCTRL      = self._tx_diffctrl.storage,
            i_TXPOSTCURSOR    = self._tx_postcursor.storage,
            i_TXPRECURSOR     = self._tx_precursor.storage,
        )

    def add_controls(self, auto_enable=True):
        self.add_base_control(auto_enable)
        self.add_prbs_control()
        self.add_loopback_control()
        self.add_polarity_control()
        self.add_electrical_control()

    def add_clock_cycles(self):
        self.clock_latch    = CSRStorage(description="Write to latch TX/RX clock cycles")
        self.clock_tx_cycles = CSRStorage(32, description="TX clock cycles")
        self.clock_rx_cycles = CSRStorage(32, description="RX clock cycles")

        tx_cycles = Signal(32)
        rx_cycles = Signal(32)
        self.sync.tx += tx_cycles.eq(tx_cycles + 1)
        self.sync.rx += rx_cycles.eq(rx_cycles + 1)

        self.sync += If(self.clock_latch.re,
            self.clock_tx_cycles.storage.eq(tx_cycles),
            self.clock_rx_cycles.storage.eq(rx_cycles),
        )

    def do_finalize(self):
        self.specials += Instance("GTYE4_CHANNEL", **self.gty_params)
