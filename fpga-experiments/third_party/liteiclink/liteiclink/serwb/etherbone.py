#
# This file is part of LiteICLink.
#
# Copyright (c) 2017-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Etherbone

CERN's Etherbone protocol is initially used to run a Wishbone bus over an
ethernet network. This re-implementation is meant to be run over serdes
and introduces some limitations:
- no probing (pf/pr)
- no address spaces (rca/bca/wca/wff)
- 32bits data and address
- 1 record per frame
"""

from migen import *

from litex.soc.interconnect import stream
from litex.soc.interconnect import wishbone

from liteiclink.serwb.packet import user_description

from litex.soc.interconnect.packet import *

# Etherbone Constants ------------------------------------------------------------------------------

etherbone_magic = 0x4e6f
etherbone_version = 1
etherbone_packet_header_length = 8
etherbone_packet_header_fields = {
    "magic":     HeaderField(0, 0, 16),

    "version":   HeaderField(2, 4,  4),
    "nr":        HeaderField(2, 2,  1),
    "pr":        HeaderField(2, 1,  1), # unused
    "pf":        HeaderField(2, 0,  1), # unused

    "addr_size": HeaderField(3, 4,  4), # static
    "port_size": HeaderField(3, 0,  4)  # static
}
etherbone_packet_header = Header(etherbone_packet_header_fields,
                                 etherbone_packet_header_length,
                                 swap_field_bytes=True)

etherbone_record_header_length = 4
etherbone_record_header_fields = {
    "bca":         HeaderField(0, 0, 1), # unused
    "rca":         HeaderField(0, 1, 1), # unused
    "rff":         HeaderField(0, 2, 1), # unused
    "cyc":         HeaderField(0, 4, 1), # unused
    "wca":         HeaderField(0, 5, 1), # unused
    "wff":         HeaderField(0, 6, 1), # unused

    "byte_enable": HeaderField(1, 0, 8),

    "wcount":      HeaderField(2, 0, 8),

    "rcount":      HeaderField(3, 0, 8)
}
etherbone_record_header = Header(etherbone_record_header_fields,
                                 etherbone_record_header_length,
                                 swap_field_bytes=True)

def _remove_from_layout(layout, *args):
    r = []
    for f in layout:
        remove = False
        for arg in args:
            if f[0] == arg:
                remove = True
        if not remove:
            r.append(f)
    return r

def etherbone_packet_description(dw):
    layout = etherbone_packet_header.get_layout()
    layout += [("data", dw)]
    return stream.EndpointDescription(layout)

def etherbone_packet_user_description(dw):
    layout = etherbone_packet_header.get_layout()
    layout = _remove_from_layout(layout,
                                 "magic",
                                 "portsize",
                                 "addrsize",
                                 "version")
    layout += user_description(dw).payload_layout
    return stream.EndpointDescription(layout)

def etherbone_record_description(dw):
    layout = etherbone_record_header.get_layout()
    layout += [("data", dw)]
    return stream.EndpointDescription(layout)

def etherbone_mmap_description(dw):
    layout = [
        ("we", 1),
        ("count", 8),
        ("base_addr", 32),
        ("be", dw//8),
        ("addr", 32),
        ("data", dw)
    ]
    return stream.EndpointDescription(layout)


# Etherbone Packet ---------------------------------------------------------------------------------

class _EtherbonePacketPacketizer(Packetizer):
    def __init__(self):
        Packetizer.__init__(self,
            etherbone_packet_description(32),
            user_description(32),
            etherbone_packet_header)


class _EtherbonePacketTX(Module):
    def __init__(self):
        self.sink = sink = stream.Endpoint(etherbone_packet_user_description(32))
        self.source = source = stream.Endpoint(user_description(32))

        # # #

        self.submodules.packetizer = packetizer = _EtherbonePacketPacketizer()
        self.comb += [
            packetizer.sink.valid.eq(sink.valid),
            packetizer.sink.last.eq(sink.last),
            sink.ready.eq(packetizer.sink.ready),

            packetizer.sink.magic.eq(etherbone_magic),
            packetizer.sink.port_size.eq(32//8),
            packetizer.sink.addr_size.eq(32//8),
            packetizer.sink.nr.eq(sink.nr),
            packetizer.sink.version.eq(etherbone_version),

            packetizer.sink.data.eq(sink.data)
        ]
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            packetizer.source.ready.eq(1),
            If(packetizer.source.valid,
                packetizer.source.ready.eq(0),
                NextState("SEND")
            )
        )
        fsm.act("SEND",
            packetizer.source.connect(source),
            source.length.eq(sink.length + etherbone_packet_header.length),
            If(source.valid & source.last & source.ready,
                NextState("IDLE")
            )
        )


class _EtherbonePacketDepacketizer(Depacketizer):
    def __init__(self):
        Depacketizer.__init__(self,
            user_description(32),
            etherbone_packet_description(32),
            etherbone_packet_header)


class _EtherbonePacketRX(Module):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint(user_description(32))
        self.source = source = stream.Endpoint(etherbone_packet_user_description(32))

        # # #

        self.submodules.depacketizer = depacketizer = _EtherbonePacketDepacketizer()
        self.comb += sink.connect(depacketizer.sink)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            depacketizer.source.ready.eq(1),
            If(depacketizer.source.valid,
                depacketizer.source.ready.eq(0),
                NextState("CHECK")
            )
        )
        valid = Signal(reset_less=True)
        self.sync += valid.eq(
            depacketizer.source.valid &
            (depacketizer.source.magic == etherbone_magic)
        )
        fsm.act("CHECK",
            If(valid,
                NextState("PRESENT")
            ).Else(
                NextState("DROP")
            )
        )
        self.comb += [
            source.last.eq(depacketizer.source.last),

            source.nr.eq(depacketizer.source.nr),

            source.data.eq(depacketizer.source.data),

            source.length.eq(sink.length - etherbone_packet_header.length)
        ]
        fsm.act("PRESENT",
            source.valid.eq(depacketizer.source.valid),
            depacketizer.source.ready.eq(source.ready),
            If(source.valid & source.last & source.ready,
                NextState("IDLE")
            )
        )
        fsm.act("DROP",
            depacketizer.source.ready.eq(1),
            If(depacketizer.source.valid &
               depacketizer.source.last &
               depacketizer.source.ready,
                NextState("IDLE")
            )
        )


class _EtherbonePacket(Module):
    def __init__(self, port_sink, port_source):
        self.submodules.tx = tx = _EtherbonePacketTX()
        self.submodules.rx = rx = _EtherbonePacketRX()
        self.comb += [
            tx.source.connect(port_sink),
            port_source.connect(rx.sink)
        ]
        self.sink, self.source = self.tx.sink, self.rx.source

# Etherbone Record ---------------------------------------------------------------------------------

class _EtherboneRecordPacketizer(Packetizer):
    def __init__(self):
        Packetizer.__init__(self,
            etherbone_record_description(32),
            etherbone_packet_user_description(32),
            etherbone_record_header)


class _EtherboneRecordDepacketizer(Depacketizer):
    def __init__(self):
        Depacketizer.__init__(self,
            etherbone_packet_user_description(32),
            etherbone_record_description(32),
            etherbone_record_header)


class _EtherboneRecordReceiver(Module):
    def __init__(self, buffer_depth=4):
        self.sink   = sink   = stream.Endpoint(etherbone_record_description(32))
        self.source = source = stream.Endpoint(etherbone_mmap_description(32))

        # # #

        # TODO: optimize ressources (no need to store parameters as datas)
        fifo = stream.SyncFIFO(etherbone_record_description(32), buffer_depth, buffered=True)
        self.submodules += fifo
        self.comb += sink.connect(fifo.sink)

        base_addr = Signal(32, reset_less=True)
        base_addr_update = Signal()
        self.sync += If(base_addr_update, base_addr.eq(fifo.source.data))

        count = Signal(max=512, reset_less=True)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            fifo.source.ready.eq(1),
            NextValue(count, 0),
            If(fifo.source.valid,
                base_addr_update.eq(1),
                If(fifo.source.wcount,
                    NextState("RECEIVE_WRITES")
                ).Elif(fifo.source.rcount,
                    NextState("RECEIVE_READS")
                )
            )
        )
        fsm.act("RECEIVE_WRITES",
            source.valid.eq(fifo.source.valid),
            source.last.eq(count == fifo.source.wcount-1),
            source.count.eq(fifo.source.wcount),
            source.be.eq(fifo.source.byte_enable),
            source.addr.eq(base_addr[2:] + count),
            source.we.eq(1),
            source.data.eq(fifo.source.data),
            fifo.source.ready.eq(source.ready),
            If(source.valid & source.ready,
                NextValue(count, count + 1),
                If(source.last,
                    If(fifo.source.rcount,
                        NextState("RECEIVE_BASE_RET_ADDR")
                    ).Else(
                        NextState("IDLE")
                    )
                )
            )
        )
        fsm.act("RECEIVE_BASE_RET_ADDR",
            NextValue(count, 0),
            If(fifo.source.valid,
                base_addr_update.eq(1),
                NextState("RECEIVE_READS")
            )
        )
        fsm.act("RECEIVE_READS",
            source.valid.eq(fifo.source.valid),
            source.last.eq(count == fifo.source.rcount-1),
            source.count.eq(fifo.source.rcount),
            source.base_addr.eq(base_addr),
            source.addr.eq(fifo.source.data[2:]),
            fifo.source.ready.eq(source.ready),
            If(source.valid & source.ready,
                NextValue(count, count + 1),
                If(source.last,
                    NextState("IDLE")
                )
            )
        )


class _EtherboneRecordSender(Module):
    def __init__(self, buffer_depth=4):
        self.sink   = sink   = stream.Endpoint(etherbone_mmap_description(32))
        self.source = source = stream.Endpoint(etherbone_record_description(32))

        # # #

        # TODO: optimize ressources (no need to store parameters as datas)
        fifo = PacketFIFO(etherbone_mmap_description(32), buffer_depth, buffered=True)
        self.submodules += fifo
        self.comb += sink.connect(fifo.sink)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            fifo.source.ready.eq(1),
            If(fifo.source.valid,
                fifo.source.ready.eq(0),
                NextState("SEND_BASE_ADDRESS")
            )
        )
        self.comb += [
            source.byte_enable.eq(fifo.source.be),
            If(fifo.source.we,
                source.wcount.eq(fifo.source.count)
            ).Else(
                source.rcount.eq(fifo.source.count)
            )
        ]
        fsm.act("SEND_BASE_ADDRESS",
            source.valid.eq(1),
            source.last.eq(0),
            source.data.eq(fifo.source.base_addr),
            If(source.ready,
                NextState("SEND_DATA")
            )
        )
        fsm.act("SEND_DATA",
            source.valid.eq(1),
            source.last.eq(fifo.source.last),
            source.data.eq(fifo.source.data),
            If(source.valid & source.ready,
                fifo.source.ready.eq(1),
                If(source.last,
                    NextState("IDLE")
                )
            )
        )


class _EtherboneRecord(Module):
    def __init__(self, endianness="big", buffer_depth=4):
        self.sink   = sink   = stream.Endpoint(etherbone_packet_user_description(32))
        self.source = source = stream.Endpoint(etherbone_packet_user_description(32))

        # # #

        # Receive record, decode it and generate mmap stream
        self.submodules.depacketizer = depacketizer = _EtherboneRecordDepacketizer()
        self.submodules.receiver = receiver = _EtherboneRecordReceiver(buffer_depth)
        self.comb += [
            sink.connect(depacketizer.sink),
            depacketizer.source.connect(receiver.sink)
        ]
        if endianness is "big":
            self.comb += receiver.sink.data.eq(reverse_bytes(depacketizer.source.data))

        # Receive MMAP stream, encode it and send records
        self.submodules.sender = sender = _EtherboneRecordSender(buffer_depth)
        self.submodules.packetizer = packetizer = _EtherboneRecordPacketizer()
        self.comb += [
            sender.source.connect(packetizer.sink),
            packetizer.source.connect(source),
            source.length.eq(etherbone_record_header.length +
            	             (sender.source.wcount != 0)*4 + sender.source.wcount*4 +
            	             (sender.source.rcount != 0)*4 + sender.source.rcount*4)
        ]
        if endianness is "big":
            self.comb += packetizer.sink.data.eq(reverse_bytes(sender.source.data))

# Etherbone Wishbone Master ------------------------------------------------------------------------

class _EtherboneWishboneMaster(Module):
    def __init__(self):
        self.sink   = sink   = stream.Endpoint(etherbone_mmap_description(32))
        self.source = source = stream.Endpoint(etherbone_mmap_description(32))
        self.bus    = bus    = wishbone.Interface()

        # # #

        data_update = Signal()

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            sink.ready.eq(1),
            If(sink.valid,
                sink.ready.eq(0),
                If(sink.we,
                    NextState("WRITE_DATA")
                ).Else(
                    NextState("READ_DATA")
                )
            )
        )
        fsm.act("WRITE_DATA",
            bus.adr.eq(sink.addr),
            bus.dat_w.eq(sink.data),
            bus.sel.eq(sink.be),
            bus.stb.eq(sink.valid),
            bus.we.eq(1),
            bus.cyc.eq(1),
            If(bus.stb & bus.ack,
                sink.ready.eq(1),
                If(sink.last,
                    NextState("IDLE")
                )
            )
        )
        fsm.act("READ_DATA",
            bus.adr.eq(sink.addr),
            bus.sel.eq(sink.be),
            bus.stb.eq(sink.valid),
            bus.cyc.eq(1),
            If(bus.stb & bus.ack,
                data_update.eq(1),
                NextState("SEND_DATA")
            )
        )
        self.sync += [
            source.base_addr.eq(sink.base_addr),
            source.addr.eq(sink.addr),
            source.count.eq(sink.count),
            source.be.eq(sink.be),
            source.we.eq(1),
            If(data_update,
                source.data.eq(bus.dat_r)
            )
        ]
        fsm.act("SEND_DATA",
            source.valid.eq(sink.valid),
            source.last.eq(sink.last),
            If(source.valid & source.ready,
                sink.ready.eq(1),
                If(source.last,
                    NextState("IDLE")
                ).Else(
                    NextState("READ_DATA")
                )
            )
        )

# Etherbone Wishbone Slave -------------------------------------------------------------------------

class _EtherboneWishboneSlave(Module):
    def __init__(self):
        self.bus    = bus    = wishbone.Interface()
        self.sink   = sink   = stream.Endpoint(etherbone_mmap_description(32))
        self.source = source = stream.Endpoint(etherbone_mmap_description(32))

        # # #

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            sink.ready.eq(1),
            If(bus.stb & bus.cyc,
                If(bus.we,
                    NextState("SEND_WRITE")
                ).Else(
                    NextState("SEND_READ")
                )
            )
        )
        fsm.act("SEND_WRITE",
            source.valid.eq(1),
            source.last.eq(1),
            source.base_addr[2:].eq(bus.adr),
            source.count.eq(1),
            source.be.eq(bus.sel),
            source.we.eq(1),
            source.data.eq(bus.dat_w),
            If(source.valid & source.ready,
                bus.ack.eq(1),
                NextState("IDLE")
            )
        )
        fsm.act("SEND_READ",
            source.valid.eq(1),
            source.last.eq(1),
            source.base_addr.eq(0),
            source.count.eq(1),
            source.be.eq(bus.sel),
            source.we.eq(0),
            source.data[2:].eq(bus.adr),
            If(source.valid & source.ready,
                NextState("WAIT_READ")
            )
        )
        fsm.act("WAIT_READ",
            sink.ready.eq(1),
            If(sink.valid & sink.we,
                bus.ack.eq(1),
                bus.dat_r.eq(sink.data),
                NextState("IDLE")
            )
        )


# Etherbone ----------------------------------------------------------------------------------------

class Etherbone(Module):
    def __init__(self, mode="master", buffer_depth=4):
        self.sink   = sink   = stream.Endpoint(user_description(32))
        self.source = source = stream.Endpoint(user_description(32))

        # # #

        # Encode/encode etherbone packets
        self.submodules.packet = packet = _EtherbonePacket(source, sink)

		# Packets are records with writes and reads
        self.submodules.record = record = _EtherboneRecord(buffer_depth)
        # Create MMAP wishbone
        self.submodules.wishbone = {
            "master": _EtherboneWishboneMaster(),
            "slave":  _EtherboneWishboneSlave(),
        }[mode]
        self.comb += [
            packet.source.connect(record.sink),
            record.source.connect(packet.sink),
            record.receiver.source.connect(self.wishbone.sink),
            self.wishbone.source.connect(record.sender.sink)
        ]
