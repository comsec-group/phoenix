#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
import random
from collections import namedtuple
from operator import xor
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.BusCSCASequencer import BusCSCASequencer

# Payload = namedtuple('payload', ['mra', 'op', 'cw'])


class BusCSCAAgent(Module):
    """
        DDR5 RCD01 Module Template

        Module
        ------


        Parameters
        ------
    """

    def __init__(self, if_ibuf_o, dcs_n_w=2, dca_w=7):
        self.SEQ_INACTIVE = [~0, 0]

        self.payload_default = namedtuple('payload', ['mra', 'op', 'cw'])
        self.payload_default.mra = 0xFF
        self.payload_default.op = 0x5A
        self.payload_default.cw = 1

        self.sequence = []
        self.seq_item = []

        sequencer = BusCSCASequencer(
            if_ibuf_o=if_ibuf_o
        )
        self.submodules.sequencer = sequencer

    def __str__(self):
        s = "-"*20 + "AGENT" + "-"*20 + "\r\n"
        for id, item in enumerate(self.sequence):
            s = s + "Seq[CS,CA][" + str(id)+"] \t= "
            s = s + str(item)
            s = s + "\r\n"
        return s

    def run_agent(self, seq_collection):
        self.build_sequence(seq_collection)
        yield from self.sequencer.run_sequence(self.sequence)

    def build_sequence(self, seq_collection):
        for id, seq_collection_item in enumerate(seq_collection):
            self.seq_item = []
            self.seq_item_ca = []
            self.seq_item_cs = []
            self.setup_seq_item(seq_collection_item)
            self.seq_item = list(zip(self.seq_item_cs, self.seq_item_ca))
            self.sequence = self.sequence + self.seq_item
        logging.debug("Sequence TOTAL = " + str(self.sequence))

    def setup_seq_item(self, seq_collection_item):
        """
        datarate : DDR|SDR1|SDR2
        ui : 1|2
        """
        self.setup_seq_cs(
            cs_signalling=seq_collection_item["cs_signalling"],
            datarate=seq_collection_item["datarate"],
            ui=seq_collection_item["ui"],
            dest_rank=seq_collection_item["destination_rank"],
        )

        self.setup_seq_ca(
            datarate=seq_collection_item["datarate"],
            ui=seq_collection_item["ui"],
            dest_rank=seq_collection_item["destination_rank"],
            opcode=seq_collection_item["opcode"],
            payload=seq_collection_item["payload"],
            randomize_payload=seq_collection_item["randomize_payload"]
        )

        if seq_collection_item["is_padded"]:
            for i in range(seq_collection_item["padding_len"]):
                self.pad_seq_item()

    def pad_seq_item(self):
        self.seq_item_cs.insert(0, ~0)
        self.seq_item_ca.insert(0, ~0)
        self.seq_item_cs.append(~0)
        self.seq_item_ca.append(~0)

    def setup_seq_cs(self, cs_signalling="normal", datarate="DDR", ui=2, dest_rank="AB"):
        cs = []
        if cs_signalling == "normal":
            if datarate == "DDR":
                for id in range(2*ui):
                    if id in [0, 1]:
                        if dest_rank == "AB":
                            cs.append(0b00)
                        elif dest_rank == "A":
                            cs.append(0b01)
                        elif dest_rank == "B":
                            cs.append(0b10)
                    else:
                        cs.append(0b11)
            elif datarate == "SDR1":
                cs = []
            elif datarate == "SDR2":
                cs = []
        elif cs_signalling == "inactive":
            if datarate == "DDR":
                for id in range(2*ui):
                    cs.append(0b11)
            elif datarate == "SDR1":
                cs = []
            elif datarate == "SDR2":
                cs = []
        elif cs_signalling == "double_ui":
            if datarate == "DDR":
                for id in range(2*ui):
                    if id in [0, 1, 2, 3]:
                        if dest_rank == "AB":
                            cs.append(0b00)
                        elif dest_rank == "A":
                            cs.append(0b01)
                        elif dest_rank == "B":
                            cs.append(0b10)
                    else:
                        cs.append(0b11)
        elif cs_signalling == "active":
            if datarate == "DDR":
                for id in range(2*ui):
                    cs.append(0b00)
            elif datarate == "SDR1":
                cs = []
            elif datarate == "SDR2":
                cs = []
        self.seq_item_cs = cs

    def setup_seq_ca(self, datarate="DDR", ui=2, dest_rank="AB", opcode=0x00, payload=None, randomize_payload=False):
        if randomize_payload:
            mra = random.randint(0, 255)
            op = random.randint(0, 255)
            cw = random.randint(0, 1)
            payload = Payload(mra, op, cw)

        assert payload.mra <= 255
        assert payload.mra >= 0

        assert payload.op <= 255
        assert payload.op >= 0

        assert payload.cw <= 1
        assert payload.cw >= 0

        assert ui <= 2
        assert ui >= 1

        ca = []

        if ui == 1:
            """
            Non standard
            """
            mra_01 = payload.mra & 0b000_0011
            ui_0 = (opcode | (mra_01 << 5))
            ui_1 = (payload.mra >> 2)
            ca = [ui_0, ui_1]

        if ui == 2:
            """
            MRW
                 | CA0||  CA1||  CA2||  CA3||  CA4||  CA5||  CA6|
            UI_0 |   H||    L||    H||    L||    L|| MRA0|| MRA1|
            UI_1 |MRA2|| MRA3|| MRA4|| MRA5|| MRA6|| MRA7||    V|
            UI_2 | OP0||  OP1||  OP2||  OP3||  OP4||  OP5||  OP6|
            UI_3 | OP7||    V||    V||   CW||    V||    V||    V|
                 | CA0||  CA1||  CA2||  CA3||  CA4||  CA5||  CA6|
            """
            mra_01 = payload.mra & 0b000_0011
            ui_0 = (opcode | (mra_01 << 5))
            ui_1 = (payload.mra >> 2)
            ui_2 = payload.op & 0b0111_1111
            ui_3 = ((payload.op & 0b1000_0000) >> 7) | (payload.cw << 3)
            ca = [ui_0, ui_1, ui_2, ui_3]

        self.seq_item_ca = ca

    def run_sequencer(self):
        yield from self.sequencer.run_sequence(self.sequence)


class TestBed(Module):
    def __init__(self):
        if_ibuf_o = If_ibuf()
        xBusCSCAAgent = BusCSCAAgent(
            if_ibuf_o=if_ibuf_o,
        )
        self.submodules.dut = xBusCSCAAgent


def run_test(tb):
    command_queue = [
        {
            "cs_signalling": "normal",
            "opcode": 0b00101,
            "payload": Payload(0x10, 0x20, 0x1),
            "randomize_payload": False,
            "destination_rank": "AB",
            "datarate": "DDR",
            "ui": 2,
            "is_padded": True,
            "padding_len": 1
        },
        {
            "cs_signalling": "normal",
            "opcode": 0b00101,
            "payload": Payload(0x10, 0x20, 0x0),
            "randomize_payload": False,
            "destination_rank": "A",
            "datarate": "DDR",
            "ui": 2,
            "is_padded": True,
            "padding_len": 1
        },
        {
            "cs_signalling": "normal",
            "opcode": 0b11111,
            "payload": Payload(0x10, 0x20, 0x0),
            "randomize_payload": True,
            "destination_rank": "B",
            "datarate": "DDR",
            "ui": 1,
            "is_padded": False,
            "padding_len": 1
        },
    ]

    yield from tb.dut.run_agent(command_queue)
    logging.debug(str(tb.dut))
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
