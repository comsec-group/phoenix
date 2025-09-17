#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from collections import namedtuple

from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *

Payload = namedtuple('payload', ['mra', 'op', 'cw'])


class BusCSCACommand():
    def __init__(self, **kwargs):
        self.cmd = {
            "cs_signalling": "normal",
            "opcode": 0b00000,
            "payload": Payload(0x00, 0x00, 0x0),
            "randomize_payload": False,
            "destination_rank": "AB",
            "datarate": "DDR",
            "ui": 1,
            "is_padded": False,
            "padding_len": 1
        }

        attr_list = ["cs_signalling", "opcode", "payload", "randomize_payload",
                     "destination_rank", "datarate", "ui", "is_padded", "padding_len"]

        if kwargs:
            for attr in attr_list:
                try:
                    self.cmd[attr] = kwargs.pop(attr)
                except KeyError:
                    pass
                except:
                    raise ValueError(
                        "Non supported parameter passed to the command")

    def __str__(self):
        s = "-"*20
        s += "\r\n"
        for key, value in self.cmd.items():
            s += f"{key}:{value}\r\n"
        s += "-"*20
        return s

class BusCSCAActive(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "active"
        self.cmd["opcode"] = 0b11111
        self.cmd["payload"] = Payload(0xFF, 0xFF, 0x0)
        self.cmd["randomize_payload"] = False
        self.cmd["destination_rank"] = "AB"
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 1
        self.cmd["is_padded"] = False
        self.cmd["padding_len"] = 0

"""
    Inactive == Deselect
"""
class BusCSCAInactive(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "inactive"
        self.cmd["opcode"] = 0b11111
        self.cmd["payload"] = Payload(0xFF, 0xFF, 0x1)
        self.cmd["randomize_payload"] = False
        self.cmd["destination_rank"] = "AB"
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 1
        self.cmd["is_padded"] = False
        self.cmd["padding_len"] = 1


class BusCSCAGeneric1Multi(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = 0b11111
        self.cmd["payload"] = Payload(0x00, 0x00, 0x0)
        self.cmd["randomize_payload"] = True
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 1
        self.cmd["is_padded"] = False


class BusCSCAGeneric1(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = 0b11111
        self.cmd["payload"] = Payload(0x00, 0x00, 0x0)
        self.cmd["randomize_payload"] = True
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 1
        self.cmd["is_padded"] = True


class BusCSCAGeneric1A(BusCSCAGeneric1):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["destination_rank"] = "A"


class BusCSCAGeneric1B(BusCSCAGeneric1):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["destination_rank"] = "B"


class BusCSCAGeneric1AB(BusCSCAGeneric1):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["destination_rank"] = "AB"


class BusCSCAGeneric2Multi(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = 0b11101
        self.cmd["payload"] = Payload(0x00, 0x00, 0x0)
        self.cmd["randomize_payload"] = True
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 2
        self.cmd["is_padded"] = False


class BusCSCAGeneric2(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = 0b11101
        self.cmd["payload"] = Payload(0x00, 0x00, 0x0)
        self.cmd["randomize_payload"] = True
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 2
        self.cmd["is_padded"] = True


class BusCSCAGeneric2A(BusCSCAGeneric2):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["destination_rank"] = "A"


class BusCSCAGeneric2B(BusCSCAGeneric2):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["destination_rank"] = "B"


class BusCSCAGeneric2AB(BusCSCAGeneric2):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["destination_rank"] = "AB"


class BusCSCAMRR(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = DDR5Opcodes.MRR
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 2


class BusCSCAMRW(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = DDR5Opcodes.MRW
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 2

class BusCSCANOP(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = 0b11111
        self.cmd["payload"] = Payload(0x00, 0x00, 0x0)
        self.cmd["randomize_payload"] = False
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 1
        self.cmd["is_padded"] = False

class BusCSCADCATM(BusCSCACommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cmd["cs_signalling"] = "normal"
        self.cmd["opcode"] = 0b11111
        self.cmd["payload"] = Payload(0x00, 0x00, 0x0)
        self.cmd["randomize_payload"] = True
        self.cmd["datarate"] = "DDR"
        self.cmd["ui"] = 1
        self.cmd["is_padded"] = False


if __name__ == "__main__":
    # Example : default command
    default_cmd = BusCSCACommand()
    print(str(default_cmd))

    # Example : modify fields
    cs_signalling = "inactive"
    opcode = 0b010101
    payload = Payload(0x11, 0x22, 0x1)
    randomize_payload = True
    destination_rank = "A"
    datarate = "SDR"
    ui = 1
    is_padded = True
    padding_len = 5
    modified_cmd = BusCSCACommand(
        cs_signalling=cs_signalling,
        opcode=opcode,
        payload=payload,
        randomize_payload=randomize_payload,
        destination_rank=destination_rank,
        datarate=datarate,
        ui=ui,
        is_padded=is_padded,
        padding_len=padding_len,
    )
    print(str(modified_cmd))

    # Example inactive
    inactive_cmd = BusCSCAInactive()
    print(str(inactive_cmd))

    # MRR
    mrr_cmd = BusCSCAMRR()
    print(str(mrr_cmd))

    # MRW
    mrw_cmd = BusCSCAMRW(payload=Payload(mra=0x12, op=0x34, cw=1))
    # mrw_cmd = BusCSCAMRW()
    print(str(mrw_cmd))
