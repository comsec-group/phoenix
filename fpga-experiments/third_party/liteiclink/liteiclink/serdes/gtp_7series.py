#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2017 Sebastien Bourdeauducq <sb@m-labs.hk>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.cores.clock import *
from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream
from litex.soc.cores.prbs import PRBSTX, PRBSRX
from litex.soc.cores.code_8b10b import Encoder, Decoder

from liteiclink.serdes.gtp_7series_init import GTPTXInit, GTPRXInit
from liteiclink.serdes.clock_aligner import BruteforceClockAligner

from liteiclink.serdes.common import *

# GTP Quad PLL -------------------------------------------------------------------------------------

class GTPQuadPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate, channel=0, shared=False):
        assert channel in [0, 1]
        self.channel = channel
        self.clk     = Signal()
        self.refclk  = Signal()
        self.reset   = Signal()
        self.lock    = Signal()
        self.config  = config = self.compute_config(refclk_freq, linerate)

        # DRP
        self.drp = DRPInterface()

        # # #

        if not shared:
            gtpe2_common_params = dict(
                # common
                i_GTREFCLK0    = refclk,
                i_BGBYPASSB    = 1,
                i_BGMONITORENB = 1,
                i_BGPDB        = 1,
                i_BGRCALOVRD   = 0b11111,
                i_RCALENB      = 1,

                i_DRPADDR      = self.drp.addr,
                i_DRPCLK       = self.drp.clk,
                i_DRPDI        = self.drp.di,
                o_DRPDO        = self.drp.do,
                i_DRPEN        = self.drp.en,
                o_DRPRDY       = self.drp.rdy,
                i_DRPWE        = self.drp.we,
            )

            if channel == 0:
                gtpe2_common_params.update(
                    # pll0
                    p_PLL0_FBDIV      = config["n2"],
                    p_PLL0_FBDIV_45   = config["n1"],
                    p_PLL0_REFCLK_DIV = config["m"],
                    i_PLL0LOCKEN      = 1,
                    i_PLL0PD          = 0,
                    i_PLL0REFCLKSEL   = 0b001,
                    i_PLL0RESET       = self.reset,
                    o_PLL0LOCK        = self.lock,
                    o_PLL0OUTCLK      = self.clk,
                    o_PLL0OUTREFCLK   = self.refclk,

                    # pll1 (not used: power down)
                    i_PLL1PD          = 1,
                )
            else:
                gtpe2_common_params.update(
                    # pll0 (not used: power down)
                    i_PLL0PD          = 1,

                    # pll0
                    p_PLL1_FBDIV      = config["n2"],
                    p_PLL1_FBDIV_45   = config["n1"],
                    p_PLL1_REFCLK_DIV = config["m"],
                    i_PLL1LOCKEN      = 1,
                    i_PLL1PD          = 0,
                    i_PLL1REFCLKSEL   = 0b001,
                    i_PLL1RESET       = self.reset,
                    o_PLL1LOCK        = self.lock,
                    o_PLL1OUTCLK      = self.clk,
                    o_PLL1OUTREFCLK   = self.refclk,
                )

            self.specials += Instance("GTPE2_COMMON", **gtpe2_common_params)
        else:
            self.gtrefclk  = refclk
            self.gtgrefclk = 0
            self.refclksel = 0b010

    @staticmethod
    def compute_config(refclk_freq, linerate):
        for n1 in [4, 5]:
            for n2 in [1, 2, 3, 4, 5]:
                for m in [1, 2]:
                    vco_freq = refclk_freq*(n1*n2)/m
                    if 1.6e9 <= vco_freq <= 3.3e9:
                        for d in [1, 2, 4, 8, 16]:
                            current_linerate = vco_freq*2/d
                            if current_linerate == linerate:
                                return {"n1": n1, "n2": n2, "m": m, "d": d,
                                        "vco_freq": vco_freq,
                                        "clkin": refclk_freq,
                                        "linerate": linerate}
        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))

    def __repr__(self):
        config = self.config
        r = """
GTPQuadPLL
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
""".format(clkin    = config["clkin"]/1e6,
           n1       = config["n1"],
           n2       = config["n2"],
           m        = config["m"],
           vco_freq = config["vco_freq"]/1e9,
           d        = config["d"],
           linerate = config["linerate"]/1e9)
        return r

# GTP ----------------------------------------------------------------------------------------------

class GTP(Module, AutoCSR):
    def __init__(self, qpll, tx_pads, rx_pads, sys_clk_freq,
        data_width          = 20,
        tx_buffer_enable    = False,
        rx_buffer_enable    = False,
        clock_aligner       = True,
        clock_aligner_comma = 0b0101111100,
        tx_polarity         = 0,
        rx_polarity         = 0):
        assert data_width in [20]

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

        self.nwords = nwords = data_width//10

        self.submodules.encoder = ClockDomainsRenamer("tx")(Encoder(nwords, True))
        self.decoders = [ClockDomainsRenamer("rx")(Decoder(True)) for _ in range(nwords)]
        self.submodules += self.decoders

        # Transceiver direct clock outputs (useful to specify clock constraints)
        self.txoutclk = Signal()
        self.rxoutclk = Signal()

        self.tx_clk_freq = qpll.config["linerate"]/data_width
        self.rx_clk_freq = qpll.config["linerate"]/data_width

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

        assert qpll.config["linerate"] < 6.6e9
        rxcdr_cfgs = {
            1 : 0x0000107FE406001041010,
            2 : 0x0000107FE206001041010,
            4 : 0x0000107FE106001041010,
            8 : 0x0000107FE086001041010,
           16 : 0x0000107FE086001041010,
        }

        # TX init ----------------------------------------------------------------------------------
        self.submodules.tx_init = tx_init = GTPTXInit(sys_clk_freq, buffer_enable=tx_buffer_enable)
        self.comb += [
            self.tx_ready.eq(tx_init.done),
            tx_init.restart.eq(~self.tx_enable)
        ]

        # RX init ----------------------------------------------------------------------------------
        self.submodules.rx_init = rx_init = GTPRXInit(sys_clk_freq, buffer_enable=rx_buffer_enable)
        self.comb += [
            self.rx_ready.eq(rx_init.done),
            rx_init.restart.eq(~self.rx_enable)
        ]

        # PLL --------------------------------------------------------------------------------------
        self.comb += [
            tx_init.plllock.eq(qpll.lock),
            rx_init.plllock.eq(qpll.lock),
            qpll.reset.eq(tx_init.pllreset)
        ]

        # DRP mux ----------------------------------------------------------------------------------
        self.submodules.drp_mux = drp_mux = DRPMux()
        drp_mux.add_interface(rx_init.drp)
        drp_mux.add_interface(self.drp)

        # GTPE2_CHANNEL instance -------------------------------------------------------------------
        class Open(Signal): pass
        txdata = Signal(data_width)
        rxdata = Signal(data_width)
        rxphaligndone = Signal()
        self.gtp_params = dict(
            # Simulation-Only Attributes
            p_SIM_RECEIVER_DETECT_PASS   = "TRUE",
            p_SIM_TX_EIDLE_DRIVE_LEVEL   = "X",
            p_SIM_RESET_SPEEDUP          = "FALSE",
            p_SIM_VERSION                = "2.0",

            # RX Byte and Word Alignment Attributes
            p_ALIGN_COMMA_DOUBLE         = "FALSE",
            p_ALIGN_COMMA_ENABLE         = 0b1111111111,
            p_ALIGN_COMMA_WORD           = 2 if data_width == 20 else 4,
            p_ALIGN_MCOMMA_DET           = "TRUE",
            p_ALIGN_MCOMMA_VALUE         = 0b1010000011,
            p_ALIGN_PCOMMA_DET           = "TRUE",
            p_ALIGN_PCOMMA_VALUE         = 0b0101111100,
            p_SHOW_REALIGN_COMMA         = "TRUE",
            p_RXSLIDE_AUTO_WAIT          = 7,
            p_RXSLIDE_MODE               = "OFF" if rx_buffer_enable else "PCS",
            p_RX_SIG_VALID_DLY           = 10,

            # RX 8B/10B Decoder Attributes
            p_RX_DISPERR_SEQ_MATCH       = "TRUE",
            p_DEC_MCOMMA_DETECT          = "TRUE",
            p_DEC_PCOMMA_DETECT          = "TRUE",
            p_DEC_VALID_COMMA_ONLY       = "TRUE",

            # RX Clock Correction Attributes
            p_CBCC_DATA_SOURCE_SEL       = "DECODED",
            p_CLK_COR_SEQ_2_USE          = "FALSE",
            p_CLK_COR_KEEP_IDLE          = "FALSE",
            p_CLK_COR_MAX_LAT            = 10 if data_width == 20 else 19,
            p_CLK_COR_MIN_LAT            = 8 if data_width == 20 else 15,
            p_CLK_COR_PRECEDENCE         = "TRUE",
            p_CLK_COR_REPEAT_WAIT        = 0,
            p_CLK_COR_SEQ_LEN            = 1,
            p_CLK_COR_SEQ_1_ENABLE       = 0b1111,
            p_CLK_COR_SEQ_1_1            = 0b0100000000,
            p_CLK_COR_SEQ_1_2            = 0b0000000000,
            p_CLK_COR_SEQ_1_3            = 0b0000000000,
            p_CLK_COR_SEQ_1_4            = 0b0000000000,
            p_CLK_CORRECT_USE            = "FALSE",
            p_CLK_COR_SEQ_2_ENABLE       = 0b1111,
            p_CLK_COR_SEQ_2_1            = 0b0100000000,
            p_CLK_COR_SEQ_2_2            = 0b0000000000,
            p_CLK_COR_SEQ_2_3            = 0b0000000000,
            p_CLK_COR_SEQ_2_4            = 0b0000000000,

            # RX Channel Bonding Attributes
            p_CHAN_BOND_KEEP_ALIGN       = "FALSE",
            p_CHAN_BOND_MAX_SKEW         = 1,
            p_CHAN_BOND_SEQ_LEN          = 1,
            p_CHAN_BOND_SEQ_1_1          = 0b0000000000,
            p_CHAN_BOND_SEQ_1_2          = 0b0000000000,
            p_CHAN_BOND_SEQ_1_3          = 0b0000000000,
            p_CHAN_BOND_SEQ_1_4          = 0b0000000000,
            p_CHAN_BOND_SEQ_1_ENABLE     = 0b1111,
            p_CHAN_BOND_SEQ_2_1          = 0b0000000000,
            p_CHAN_BOND_SEQ_2_2          = 0b0000000000,
            p_CHAN_BOND_SEQ_2_3          = 0b0000000000,
            p_CHAN_BOND_SEQ_2_4          = 0b0000000000,
            p_CHAN_BOND_SEQ_2_ENABLE     = 0b1111,
            p_CHAN_BOND_SEQ_2_USE        = "FALSE",
            p_FTS_DESKEW_SEQ_ENABLE      = 0b1111,
            p_FTS_LANE_DESKEW_CFG        = 0b1111,
            p_FTS_LANE_DESKEW_EN         = "FALSE",

            # RX Margin Analysis Attributes
            p_ES_CONTROL                 = 0b000000,
            p_ES_ERRDET_EN               = "FALSE",
            p_ES_EYE_SCAN_EN             = "TRUE",
            p_ES_HORZ_OFFSET             = 0x000,
            p_ES_PMA_CFG                 = 0b0000000000,
            p_ES_PRESCALE                = 0b00000,
            p_ES_QUALIFIER               = 0x00000000000000000000,
            p_ES_QUAL_MASK               = 0x00000000000000000000,
            p_ES_SDATA_MASK              = 0x00000000000000000000,
            p_ES_VERT_OFFSET             = 0b000000000,

            # FPGA RX Interface Attributes
            p_RX_DATA_WIDTH              = data_width,

            # PMA Attributes
            p_OUTREFCLK_SEL_INV          = 0b11,
            p_PMA_RSV                    = 0x00000333,
            p_PMA_RSV2                   = 0x00002040,
            p_PMA_RSV3                   = 0b00,
            p_PMA_RSV4                   = 0b0000,
            p_RX_BIAS_CFG                = 0b0000111100110011,
            p_DMONITOR_CFG               = 0x000A00,
            p_RX_CM_SEL                  = 0b01,
            p_RX_CM_TRIM                 = 0b0000,
            p_RX_DEBUG_CFG               = 0b00000000000000,
            p_RX_OS_CFG                  = 0b0000010000000,
            p_TERM_RCAL_CFG              = 0b100001000010000,
            p_TERM_RCAL_OVRD             = 0b000,
            p_TST_RSV                    = 0x00000000,
            p_RX_CLK25_DIV               = 5,
            p_TX_CLK25_DIV               = 5,
            p_UCODEER_CLR                = 0b0,

            # PCI Express Attributes
            p_PCS_PCIE_EN                = "FALSE",

            # PCS Attributes
            p_PCS_RSVD_ATTR              = 0x000000000000,

            # RX Buffer Attributes
            p_RXBUF_ADDR_MODE            = "FAST",
            p_RXBUF_EIDLE_HI_CNT         = 0b1000,
            p_RXBUF_EIDLE_LO_CNT         = 0b0000,
            p_RXBUF_EN                   = "TRUE" if rx_buffer_enable else "FALSE",
            p_RX_BUFFER_CFG              = 0b000000,
            p_RXBUF_RESET_ON_CB_CHANGE   = "TRUE",
            p_RXBUF_RESET_ON_COMMAALIGN  = "FALSE",
            p_RXBUF_RESET_ON_EIDLE       = "FALSE",
            p_RXBUF_RESET_ON_RATE_CHANGE = "TRUE",
            p_RXBUFRESET_TIME            = 0b00001,
            p_RXBUF_THRESH_OVFLW         = 61,
            p_RXBUF_THRESH_OVRD          = "FALSE",
            p_RXBUF_THRESH_UNDFLW        = 4,
            p_RXDLY_CFG                  = 0x001F,
            p_RXDLY_LCFG                 = 0x030,
            p_RXDLY_TAP_CFG              = 0x0000,
            p_RXPH_CFG                   = 0xC00002,
            p_RXPHDLY_CFG                = 0x084020,
            p_RXPH_MONITOR_SEL           = 0b00000,
            p_RX_XCLK_SEL                = "RXREC" if rx_buffer_enable else "RXUSR",
            p_RX_DDI_SEL                 = 0b000000,
            p_RX_DEFER_RESET_BUF_EN      = "TRUE",

            # CDR Attributes
            p_RXCDR_CFG                  = rxcdr_cfgs[qpll.config["d"]],
            p_RXCDR_FR_RESET_ON_EIDLE    = 0b0,
            p_RXCDR_HOLD_DURING_EIDLE    = 0b0,
            p_RXCDR_PH_RESET_ON_EIDLE    = 0b0,
            p_RXCDR_LOCK_CFG             = 0b001001,

            # RX Initialization and Reset Attributes
            p_RXCDRFREQRESET_TIME        = 0b00001,
            p_RXCDRPHRESET_TIME          = 0b00001,
            p_RXISCANRESET_TIME          = 0b00001,
            p_RXPCSRESET_TIME            = 0b00001,
            p_RXPMARESET_TIME            = 0b00011,

            # RX OOB Signaling Attributes
            p_RXOOB_CFG                  = 0b0000110,

            # RX Gearbox Attributes
            p_RXGEARBOX_EN               = "FALSE",
            p_GEARBOX_MODE               = 0b000,

            # PRBS Detection Attribute
            p_RXPRBS_ERR_LOOPBACK        = 0b0,

            # Power-Down Attributes
            p_PD_TRANS_TIME_FROM_P2      = 0x03c,
            p_PD_TRANS_TIME_NONE_P2      = 0x3c,
            p_PD_TRANS_TIME_TO_P2        = 0x64,

            # RX OOB Signaling Attributes
            p_SAS_MAX_COM                = 64,
            p_SAS_MIN_COM                = 36,
            p_SATA_BURST_SEQ_LEN         = 0b0101,
            p_SATA_BURST_VAL             = 0b100,
            p_SATA_EIDLE_VAL             = 0b100,
            p_SATA_MAX_BURST             = 8,
            p_SATA_MAX_INIT              = 21,
            p_SATA_MAX_WAKE              = 7,
            p_SATA_MIN_BURST             = 4,
            p_SATA_MIN_INIT              = 12,
            p_SATA_MIN_WAKE              = 4,

            # RX Fabric Clock Output Control Attributes
            p_TRANS_TIME_RATE            = 0x0E,

            # TX Buffer Attributes
            p_TXBUF_EN                   = "TRUE" if tx_buffer_enable else "FALSE",
            p_TXBUF_RESET_ON_RATE_CHANGE = "TRUE",
            p_TXDLY_CFG                  = 0x001F,
            p_TXDLY_LCFG                 = 0x030,
            p_TXDLY_TAP_CFG              = 0x0000,
            p_TXPH_CFG                   = 0x0780,
            p_TXPHDLY_CFG                = 0x084020,
            p_TXPH_MONITOR_SEL           = 0b00000,
            p_TX_XCLK_SEL                = "TXOUT" if tx_buffer_enable else "TXUSR",

            # FPGA TX Interface Attributes
            p_TX_DATA_WIDTH              = data_width,

            # TX Configurable Driver Attributes
            p_TX_DEEMPH0                 = 0b000000,
            p_TX_DEEMPH1                 = 0b000000,
            p_TX_EIDLE_ASSERT_DELAY      = 0b110,
            p_TX_EIDLE_DEASSERT_DELAY    = 0b100,
            p_TX_LOOPBACK_DRIVE_HIZ      = "FALSE",
            p_TX_MAINCURSOR_SEL          = 0b0,
            p_TX_DRIVE_MODE              = "DIRECT",
            p_TX_MARGIN_FULL_0           = 0b1001110,
            p_TX_MARGIN_FULL_1           = 0b1001001,
            p_TX_MARGIN_FULL_2           = 0b1000101,
            p_TX_MARGIN_FULL_3           = 0b1000010,
            p_TX_MARGIN_FULL_4           = 0b1000000,
            p_TX_MARGIN_LOW_0            = 0b1000110,
            p_TX_MARGIN_LOW_1            = 0b1000100,
            p_TX_MARGIN_LOW_2            = 0b1000010,
            p_TX_MARGIN_LOW_3            = 0b1000000,
            p_TX_MARGIN_LOW_4            = 0b1000000,

            # TX Gearbox Attributes
            p_TXGEARBOX_EN               = "FALSE",

            # TX Initialization and Reset Attributes
            p_TXPCSRESET_TIME            = 0b00001,
            p_TXPMARESET_TIME            = 0b00001,

            # TX Receiver Detection Attributes
            p_TX_RXDETECT_CFG            = 0x1832,
            p_TX_RXDETECT_REF            = 0b100,

            # JTAG Attributes
            p_ACJTAG_DEBUG_MODE          = 0b0,
            p_ACJTAG_MODE                = 0b0,
            p_ACJTAG_RESET               = 0b0,

            # CDR Attributes
            p_CFOK_CFG                   = 0x49000040E80,
            p_CFOK_CFG2                  = 0b0100000,
            p_CFOK_CFG3                  = 0b0100000,
            p_CFOK_CFG4                  = 0b0,
            p_CFOK_CFG5                  = 0x0,
            p_CFOK_CFG6                  = 0b0000,
            p_RXOSCALRESET_TIME          = 0b00011,
            p_RXOSCALRESET_TIMEOUT       = 0b00000,

            # PMA Attributes
            p_CLK_COMMON_SWING           = 0b0,
            p_RX_CLKMUX_EN               = 0b1,
            p_TX_CLKMUX_EN               = 0b1,
            p_ES_CLK_PHASE_SEL           = 0b0,
            p_USE_PCS_CLK_PHASE_SEL      = 0b0,
            p_PMA_RSV6                   = 0b0,
            p_PMA_RSV7                   = 0b0,

            # TX Configuration Driver Attributes
            p_TX_PREDRIVER_MODE          = 0b0,
            p_PMA_RSV5                   = 0b0,
            p_SATA_PLL_CFG               = "VCO_3000MHZ",

            # RX Fabric Clock Output Control Attributes
            p_RXOUT_DIV                  = qpll.config["d"],

            # TX Fabric Clock Output Control Attributes
            p_TXOUT_DIV                  = qpll.config["d"],

            # RX Phase Interpolator Attributes
            p_RXPI_CFG0                  = 0b000,
            p_RXPI_CFG1                  = 0b1,
            p_RXPI_CFG2                  = 0b1,

            # RX Equalizer Attributes
            p_ADAPT_CFG0                 = 0x00000,
            p_RXLPMRESET_TIME            = 0b0001111,
            p_RXLPM_BIAS_STARTUP_DISABLE = 0b0,
            p_RXLPM_CFG                  = 0b0110,
            p_RXLPM_CFG1                 = 0b0,
            p_RXLPM_CM_CFG               = 0b0,
            p_RXLPM_GC_CFG               = 0b111100010,
            p_RXLPM_GC_CFG2              = 0b001,
            p_RXLPM_HF_CFG               = 0b00001111110000,
            p_RXLPM_HF_CFG2              = 0b01010,
            p_RXLPM_HF_CFG3              = 0b0000,
            p_RXLPM_HOLD_DURING_EIDLE    = 0b0,
            p_RXLPM_INCM_CFG             = 0b0,
            p_RXLPM_IPCM_CFG             = 0b1,
            p_RXLPM_LF_CFG               = 0b000000001111110000,
            p_RXLPM_LF_CFG2              = 0b01010,
            p_RXLPM_OSINT_CFG            = 0b100,

            # TX Phase Interpolator PPM Controller Attributes
            p_TXPI_CFG0                  = 0b00,
            p_TXPI_CFG1                  = 0b00,
            p_TXPI_CFG2                  = 0b00,
            p_TXPI_CFG3                  = 0b0,
            p_TXPI_CFG4                  = 0b0,
            p_TXPI_CFG5                  = 0b000,
            p_TXPI_GREY_SEL              = 0b0,
            p_TXPI_INVSTROBE_SEL         = 0b0,
            p_TXPI_PPMCLK_SEL            = "TXUSRCLK2",
            p_TXPI_PPM_CFG               = 0x00,
            p_TXPI_SYNFREQ_PPM           = 0b001,

            # LOOPBACK Attributes
            p_LOOPBACK_CFG               = 0b0,
            p_PMA_LOOPBACK_CFG           = 0b0,

            # RX OOB Signalling Attributes
            p_RXOOB_CLK_CFG              = "PMA",

            # TX OOB Signalling Attributes
            p_TXOOB_CFG                  = 0b0,

            # RX Buffer Attributes
            p_RXSYNC_MULTILANE           = 0b0,
            p_RXSYNC_OVRD                = 0b0,
            p_RXSYNC_SKIP_DA             = 0b0,

            # TX Buffer Attributes
            p_TXSYNC_MULTILANE           = 0b0,
            p_TXSYNC_OVRD                = 0b1 if tx_buffer_enable else 0b0,
            p_TXSYNC_SKIP_DA             = 0b0
        )
        self.gtp_params.update(
            # CPLL Ports
            i_GTRSVD               = 0b0000000000000000,
            i_PCSRSVDIN            = 0b0000000000000000,
            i_TSTIN                = 0b11111111111111111111,

            # Channel - DRP Ports
            i_DRPADDR              = drp_mux.addr,
            i_DRPCLK               = drp_mux.clk,
            i_DRPDI                = drp_mux.di,
            o_DRPDO                = drp_mux.do,
            i_DRPEN                = drp_mux.en,
            o_DRPRDY               = drp_mux.rdy,
            i_DRPWE                = drp_mux.we,

            # Clocking Ports
            i_RXSYSCLKSEL          = 0b00 if qpll.channel == 0 else 0b11,
            i_TXSYSCLKSEL          = 0b00 if qpll.channel == 0 else 0b11,

            # FPGA TX Interface Datapath Configuration
            i_TX8B10BEN            = 0,

            # GTPE2_CHANNEL Clocking Ports
            i_PLL0CLK              = qpll.clk if qpll.channel == 0 else 0,
            i_PLL0REFCLK           = qpll.refclk if qpll.channel == 0 else 0,
            i_PLL1CLK              = qpll.clk if qpll.channel == 1 else 0,
            i_PLL1REFCLK           = qpll.refclk if qpll.channel == 1 else 0,

            # Loopback Ports
            i_LOOPBACK             = self.loopback,

            # PCI Express Ports
            o_PHYSTATUS            = Open(),
            i_RXRATE               = 0,
            o_RXVALID              = Open(),

            # PMA Reserved Ports
            i_PMARSVDIN3           = 0b0,
            i_PMARSVDIN4           = 0b0,

            # Power-Down Ports
            i_RXPD                 = Cat(rx_init.gtrxpd, rx_init.gtrxpd),
            i_TXPD                 = 0b00,

            # RX 8B/10B Decoder Ports
            i_SETERRSTATUS         = 0,

            # RX Initialization and Reset Ports
            i_EYESCANRESET         = 0,
            i_RXUSERRDY            = rx_init.rxuserrdy,

            # RX Margin Analysis Ports
            o_EYESCANDATAERROR     = Open(),
            i_EYESCANMODE          = 0,
            i_EYESCANTRIGGER       = 0,

            # Receive Ports
            i_CLKRSVD0             = 0,
            i_CLKRSVD1             = 0,
            i_DMONFIFORESET        = 0,
            i_DMONITORCLK          = 0,
            o_RXPMARESETDONE       = rx_init.rxpmaresetdone,
            i_SIGVALIDCLK          = 0,

            # Receive Ports - CDR Ports
            i_RXCDRFREQRESET       = 0,
            i_RXCDRHOLD            = 0,
            o_RXCDRLOCK            = Open(),
            i_RXCDROVRDEN          = 0,
            i_RXCDRRESET           = 0,
            i_RXCDRRESETRSV        = 0,
            i_RXOSCALRESET         = 0,
            i_RXOSINTCFG           = 0b0010,
            o_RXOSINTDONE          = Open(),
            i_RXOSINTHOLD          = 0,
            i_RXOSINTOVRDEN        = 0,
            i_RXOSINTPD            = 0,
            o_RXOSINTSTARTED       = Open(),
            i_RXOSINTSTROBE        = 0,
            o_RXOSINTSTROBESTARTED = Open(),
            i_RXOSINTTESTOVRDEN    = 0,

            # Receive Ports - Clock Correction Ports
            o_RXCLKCORCNT          = Open(),

            # Receive Ports - FPGA RX Interface Datapath Configuration
            i_RX8B10BEN            = 0,

            # Receive Ports - FPGA RX Interface Ports
            o_RXDATA               = Cat(*[rxdata[10*i:10*i+8] for i in range(nwords)]),
            i_RXUSRCLK             = ClockSignal("rx"),
            i_RXUSRCLK2            = ClockSignal("rx"),

            # Receive Ports - Pattern Checker Ports
            o_RXPRBSERR            = Open(),
            i_RXPRBSSEL            = 0,

            # Receive Ports - Pattern Checker ports
            i_RXPRBSCNTRESET       = 0,

            # Receive Ports - RX 8B/10B Decoder Ports
            o_RXCHARISCOMMA        = Open(),
            o_RXCHARISK            = Cat(*[rxdata[10*i+8] for i in range(nwords)]),
            o_RXDISPERR            = Cat(*[rxdata[10*i+9] for i in range(nwords)]),
            o_RXNOTINTABLE         = Open(),

            # Receive Ports - RX AFE Ports
            i_GTPRXN               = rx_pads.n,
            i_GTPRXP               = rx_pads.p,
            i_PMARSVDIN2           = 0b0,
            o_PMARSVDOUT0          = Open(),
            o_PMARSVDOUT1          = Open(),

            # Receive Ports - RX Buffer Bypass Ports
            i_RXBUFRESET           = 0,
            o_RXBUFSTATUS          = Open(),
            i_RXDDIEN              = 0 if rx_buffer_enable else 1,
            i_RXDLYBYPASS          = 1 if rx_buffer_enable else 0,
            i_RXDLYEN              = 0,
            i_RXDLYOVRDEN          = 0,
            i_RXDLYSRESET          = rx_init.rxdlysreset,
            o_RXDLYSRESETDONE      = rx_init.rxdlysresetdone,
            i_RXPHALIGN            = 0,
            o_RXPHALIGNDONE        = rxphaligndone,
            i_RXPHALIGNEN          = 0,
            i_RXPHDLYPD            = 0,
            i_RXPHDLYRESET         = 0,
            o_RXPHMONITOR          = Open(),
            i_RXPHOVRDEN           = 0,
            o_RXPHSLIPMONITOR      = Open(),
            o_RXSTATUS             = Open(),
            i_RXSYNCALLIN          = rxphaligndone,
            o_RXSYNCDONE           = rx_init.rxsyncdone,
            i_RXSYNCIN             = 0,
            i_RXSYNCMODE           = 0 if rx_buffer_enable else 1,
            o_RXSYNCOUT            = Open(),

            # Receive Ports - RX Byte and Word Alignment Ports
            o_RXBYTEISALIGNED      = Open(),
            o_RXBYTEREALIGN        = Open(),
            o_RXCOMMADET           = Open(),
            i_RXCOMMADETEN         = 1,
            i_RXMCOMMAALIGNEN      = (~clock_aligner & self.rx_align & (rx_prbs_config == 0b00)) if rx_buffer_enable else 0,
            i_RXPCOMMAALIGNEN      = (~clock_aligner & self.rx_align & (rx_prbs_config == 0b00)) if rx_buffer_enable else 0,
            i_RXSLIDE              = 0,

            # Receive Ports - RX Channel Bonding Ports
            o_RXCHANBONDSEQ        = Open(),
            i_RXCHBONDEN           = 0,
            i_RXCHBONDI            = 0b0000,
            i_RXCHBONDLEVEL        = 0,
            i_RXCHBONDMASTER       = 0,
            o_RXCHBONDO            = Open(),
            i_RXCHBONDSLAVE        = 0,

            # Receive Ports - RX Channel Bonding Ports
            o_RXCHANISALIGNED      = Open(),
            o_RXCHANREALIGN        = Open(),

            # Receive Ports - RX Decision Feedback Equalizer
            o_DMONITOROUT          = Open(),
            i_RXADAPTSELTEST       = 0,
            i_RXDFEXYDEN           = 0,
            i_RXOSINTEN            = 0b1,
            i_RXOSINTID0           = 0,
            i_RXOSINTNTRLEN        = 0,
            o_RXOSINTSTROBEDONE    = Open(),

            # Receive Ports - RX Driver,OOB signalling,Coupling and Eq.,CDR
            i_RXLPMLFOVRDEN        = 0,
            i_RXLPMOSINTNTRLEN     = 0,

            # Receive Ports - RX Equalizer Ports
            i_RXLPMHFHOLD          = 0,
            i_RXLPMHFOVRDEN        = 0,
            i_RXLPMLFHOLD          = 0,
            i_RXOSHOLD             = 0,
            i_RXOSOVRDEN           = 0,

            # Receive Ports - RX Fabric ClocK Output Control Ports
            o_RXRATEDONE           = Open(),

            # Receive Ports - RX Fabric Clock Output Control Ports
            i_RXRATEMODE           = 0b0,

            # Receive Ports - RX Fabric Output Control Ports
            o_RXOUTCLK             = self.rxoutclk,
            o_RXOUTCLKFABRIC       = Open(),
            o_RXOUTCLKPCS          = Open(),
            i_RXOUTCLKSEL          = 0b010,

            # Receive Ports - RX Gearbox Ports
            o_RXDATAVALID          = Open(),
            o_RXHEADER             = Open(),
            o_RXHEADERVALID        = Open(),
            o_RXSTARTOFSEQ         = Open(),
            i_RXGEARBOXSLIP        = 0,

            # Receive Ports - RX Initialization and Reset Ports
            i_GTRXRESET            = rx_init.gtrxreset,
            i_RXLPMRESET           = 0,
            i_RXOOBRESET           = 0,
            i_RXPCSRESET           = 0,
            i_RXPMARESET           = 0,

            # Receive Ports - RX OOB Signaling ports
            o_RXCOMSASDET          = Open(),
            o_RXCOMWAKEDET         = Open(),
            o_RXCOMINITDET         = Open(),
            o_RXELECIDLE           = Open(),
            i_RXELECIDLEMODE       = 0b11,

            # Receive Ports - RX Polarity Control Ports
            i_RXPOLARITY           = rx_polarity,

            # Receive Ports -RX Initialization and Reset Ports
            o_RXRESETDONE          = rx_init.rxresetdone,

            # TX Buffer Bypass Ports
            i_TXPHDLYTSTCLK        = 0,

            # TX Configurable Driver Ports
            i_TXPOSTCURSOR         = 0b00000,
            i_TXPOSTCURSORINV      = 0,
            i_TXPRECURSOR          = 0b00000,
            i_TXPRECURSORINV       = 0,

            # TX Fabric Clock Output Control Ports
            i_TXRATEMODE           = 0,

            # TX Initialization and Reset Ports
            i_CFGRESET             = 0,
            i_GTTXRESET            = tx_init.gttxreset,
            o_PCSRSVDOUT           = Open(),
            i_TXUSERRDY            = tx_init.txuserrdy,

            # TX Phase Interpolator PPM Controller Ports
            i_TXPIPPMEN            = 0,
            i_TXPIPPMOVRDEN        = 0,
            i_TXPIPPMPD            = 0,
            i_TXPIPPMSEL           = 1,
            i_TXPIPPMSTEPSIZE      = 0,

            # Transceiver Reset Mode Operation
            i_GTRESETSEL           = 0,
            i_RESETOVRD            = 0,

            # Transmit Ports
            o_TXPMARESETDONE       = Open(),

            # Transmit Ports - Configurable Driver Ports
            i_PMARSVDIN0           = 0b0,
            i_PMARSVDIN1           = 0b0,

            # Transmit Ports - FPGA TX Interface Ports
            i_TXDATA               = Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
            i_TXUSRCLK             = ClockSignal("tx"),
            i_TXUSRCLK2            = ClockSignal("tx"),

            # Transmit Ports - PCI Express Ports
            i_TXELECIDLE           = 0,
            i_TXMARGIN             = 0,
            i_TXRATE               = 0,
            i_TXSWING              = 0,

            # Transmit Ports - Pattern Generator Ports
            i_TXPRBSFORCEERR       = 0,

            # Transmit Ports - TX 8B/10B Encoder Ports
            i_TX8B10BBYPASS        = 0,
            i_TXCHARDISPMODE       = Cat(*[txdata[10*i+9] for i in range(nwords)]),
            i_TXCHARDISPVAL        = Cat(*[txdata[10*i+8] for i in range(nwords)]),
            i_TXCHARISK            = 0,

            # Transmit Ports - TX Buffer Bypass Ports
            i_TXDLYBYPASS          = 1 if tx_buffer_enable else 0,
            i_TXDLYEN              = 0 if tx_buffer_enable else tx_init.txdlyen,
            i_TXDLYHOLD            = 0,
            i_TXDLYOVRDEN          = 0,
            i_TXDLYSRESET          = tx_init.txdlysreset,
            o_TXDLYSRESETDONE      = tx_init.txdlysresetdone,
            i_TXDLYUPDOWN          = 0,
            i_TXPHALIGN            = tx_init.txphalign,
            o_TXPHALIGNDONE        = tx_init.txphaligndone,
            i_TXPHALIGNEN          = 0 if tx_buffer_enable else 1,
            i_TXPHDLYPD            = 0,
            i_TXPHDLYRESET         = 0,
            i_TXPHINIT             = tx_init.txphinit,
            o_TXPHINITDONE         = tx_init.txphinitdone,
            i_TXPHOVRDEN           = 0,

            # Transmit Ports - TX Buffer Ports
            o_TXBUFSTATUS          = Open(),

            # Transmit Ports - TX Buffer and Phase Alignment Ports
            i_TXSYNCALLIN          = 0,
            o_TXSYNCDONE           = Open(),
            i_TXSYNCIN             = 0,
            i_TXSYNCMODE           = 0,
            o_TXSYNCOUT            = Open(),

            # Transmit Ports - TX Configurable Driver Ports
            o_GTPTXN               = tx_pads.n,
            o_GTPTXP               = tx_pads.p,
            i_TXBUFDIFFCTRL        = 0b100,
            i_TXDEEMPH             = 0,
            i_TXDIFFCTRL           = 0b1000,
            i_TXDIFFPD             = 0,
            i_TXINHIBIT            = self.tx_inhibit,
            i_TXMAINCURSOR         = 0b0000000,
            i_TXPISOPD             = 0,

            # Transmit Ports - TX Fabric Clock Output Control Ports
            o_TXOUTCLK             = self.txoutclk,
            o_TXOUTCLKFABRIC       = Open(),
            o_TXOUTCLKPCS          = Open(),
            i_TXOUTCLKSEL          = 0b010 if tx_buffer_enable else 0b011,
            o_TXRATEDONE           = Open(),

            # Transmit Ports - TX Gearbox Ports
            o_TXGEARBOXREADY       = Open(),
            i_TXHEADER             = 0,
            i_TXSEQUENCE           = 0,
            i_TXSTARTSEQ           = 0,

            # Transmit Ports - TX Initialization and Reset Ports
            i_TXPCSRESET           = 0,
            i_TXPMARESET           = 0,
            o_TXRESETDONE          = tx_init.txresetdone,

            # Transmit Ports - TX OOB signalling Ports
            o_TXCOMFINISH          = Open(),
            i_TXCOMINIT            = 0,
            i_TXCOMSAS             = 0,
            i_TXCOMWAKE            = 0,
            i_TXPDELECIDLEMODE     = 0,

            # Transmit Ports - TX Polarity Control Ports
            i_TXPOLARITY           = tx_polarity,

            # Transmit Ports - TX Receiver Detection Ports
            i_TXDETECTRX           = 0,

            # Transmit Ports - pattern Generator Ports
            i_TXPRBSSEL            = 0,
        )

        # TX clocking ------------------------------------------------------------------------------
        tx_reset_deglitched = Signal()
        tx_reset_deglitched.attr.add("no_retiming")
        self.sync += tx_reset_deglitched.eq(~tx_init.done)
        self.clock_domains.cd_tx = ClockDomain()

        txoutclk_bufg = Signal()
        self.specials += Instance("BUFG",
            i_I = self.txoutclk,
            o_O = txoutclk_bufg,
        )

        if not tx_buffer_enable:
            txoutclk_div = qpll.config["clkin"]/self.tx_clk_freq
        else:
            txoutclk_div = 1
        # Use txoutclk_bufg when divider is 1
        if txoutclk_div == 1:
            self.comb += self.cd_tx.clk.eq(txoutclk_bufg)
            self.specials += AsyncResetSynchronizer(self.cd_tx, tx_reset_deglitched)
        # Use a BUFR when integer divider (with BUFR_DIVIDE)
        elif txoutclk_div == int(txoutclk_div):
            txoutclk_bufr = Signal()
            self.specials += [
                Instance("BUFR",
                    p_BUFR_DIVIDE = str(int(txoutclk_div)),
                    i_CE = 1,
                    i_I  = txoutclk_bufg,
                    o_O  = txoutclk_bufr,
                ),
                Instance("BUFG",
                    i_I = txoutclk_bufr,
                    o_O = self.cd_tx.clk,
                ),
                AsyncResetSynchronizer(self.cd_tx, tx_reset_deglitched)
            ]
        # Use a PLL when non-integer divider
        else:
            txoutclk_pll = S7PLL()
            self.comb += txoutclk_pll.reset.eq(tx_reset_deglitched)
            self.submodules += txoutclk_pll
            txoutclk_pll.register_clkin(txoutclk_bufg, qpll.config["clkin"])
            txoutclk_pll.create_clkout(self.cd_tx, self.tx_clk_freq)

        # RX clocking ------------------------------------------------------------------------------
        rx_reset_deglitched = Signal()
        rx_reset_deglitched.attr.add("no_retiming")
        self.sync.tx += rx_reset_deglitched.eq(~rx_init.done)
        self.clock_domains.cd_rx = ClockDomain()
        self.specials += [
            Instance("BUFG",
                i_I = self.rxoutclk,
                o_O = self.cd_rx.clk,
            ),
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
            clock_aligner = BruteforceClockAligner(clock_aligner_comma, self.tx_clk_freq, check_period=10e-3)
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
        self.gtp_params.update(
            i_TXPOLARITY = self._tx_polarity.fields.swap,
            i_RXPOLARITY = self._rx_polarity.fields.swap,
        )

    def add_electrical_control(self):
        self._tx_diffctrl       = CSRStorage(4, reset=0b1000,  description="TX Driver Swing Control, see UG482.")
        self._tx_postcursor     = CSRStorage(5, reset=0b00000, description="TX Post Cursor Pre-emphasis Control, see UG482.")
        self._tx_postcursor_inv = CSRStorage(1, reset=0b0,     description="TX Post Cursor Polarity, see UG482.")
        self._tx_precursor      = CSRStorage(5, reset=0b00000, description="TX Pre Cursor Pre-emphasis Control, see UG482.")
        self._tx_precursor_inv  = CSRStorage(1, reset=0b0,     description="Invert polarity of TX Pre Cursor, see UG482.")
        self.gtp_params.update(
            i_TXDIFFCTRL      = self._tx_diffctrl.storage,
            i_TXPOSTCURSOR    = self._tx_postcursor.storage,
            i_TXPOSTCURSORINV = self._tx_postcursor_inv.storage,
            i_TXPRECURSOR     = self._tx_precursor.storage,
            i_TXPRECURSORINV  = self._tx_precursor_inv.storage,
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
        self.specials += Instance("GTPE2_CHANNEL", **self.gtp_params)
