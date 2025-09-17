#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

from litex.soc.interconnect import stream

from liteiclink.serwb.packet import Packetizer, Depacketizer
from liteiclink.serwb.etherbone import Etherbone


class SERWBCore(Module):
    def __init__(self, phy, clk_freq, mode,
        etherbone_buffer_depth = 4,
        tx_buffer_depth        = 8,
        rx_buffer_depth        = 8):

        # Etherbone --------------------------------------------------------------------------------
        self.submodules.etherbone = etherbone = Etherbone(mode, etherbone_buffer_depth)

        # Bus --------------------------------------------------------------------------------------
        self.bus = etherbone.wishbone.bus

        # Packetizer / Depacketizer ----------------------------------------------------------------
        self.submodules.depacketizer = depacketizer = Depacketizer(clk_freq)
        self.submodules.packetizer   = packetizer   = Packetizer()

        # Buffering --------------------------------------------------------------------------------
        tx_fifo = stream.SyncFIFO([("data", 32)], tx_buffer_depth, buffered=True)
        rx_fifo = stream.SyncFIFO([("data", 32)], rx_buffer_depth, buffered=True)
        self.submodules += tx_fifo, rx_fifo

        # Data flow --------------------------------------------------------------------------------
        self.comb += [
            # Phy <--> Core
            packetizer.source.connect(tx_fifo.sink),
            tx_fifo.source.connect(phy.sink),

            phy.source.connect(rx_fifo.sink),
            rx_fifo.source.connect(depacketizer.sink),

            # Etherbone <--> Core
            depacketizer.source.connect(etherbone.sink),
            etherbone.source.connect(packetizer.sink)
        ]
