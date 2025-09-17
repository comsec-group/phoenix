#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import argparse

"""
    Example usage:
        python qm.py 0x1F 0x2F
        python qm.py 124 0x2F
        python qm.py 124 54
"""


def print_systems(a, ins=True):
    if ins:
        print("[Base10] = " + format(a, '#8d'), end=' ')
        print("[Base 2] = " + format(a, '#009b'), end=' ')
        print("[Base16] = " + format(a, '#6x'))
    else:
        print("[Base10] = " + format(a, '#8d'), end=' ')
        print("[Base 2] = " + format(a, '#016b'), end=' ')
        print("[Base16] = " + format(a, '#6x'))


def extract(uis):
    ui0 = uis[0]
    ui1 = uis[1]
    ui2 = uis[2]
    ui3 = uis[3]

    opcode = ui0 & 0b001_1111
    mra = ((ui0 & 0b110_0000) >> 5) | ((ui1 & 0b011_1111) << 2)
    op = ui2 | ((ui3 & 0b000_0001) << 7)
    cw = (ui3 & 0b000_1000) >> 3
    return [opcode, mra, op, cw]


parser = argparse.ArgumentParser(description="Math helper for RCD debugging")
parser.add_argument('ui0')
parser.add_argument('ui1')
parser.add_argument('ui2')
parser.add_argument('ui3')

args = parser.parse_args()

uis = []
for arg in [args.ui0, args.ui1, args.ui2, args.ui3]:
    if arg.startswith("0x"):
        ui = int(arg, 16)
    elif arg.startswith("0b"):
        ui = int(arg, 2)
    else:
        ui = int(arg)
    uis.append(ui)


""" Make sure uis are 7 bit integers """
for ui in uis:
    assert ui >= 0
    assert ui < 128


[opcode, mra, op, cw] = extract(uis)
for item in uis:
    print_systems(item)

print("OPCODE, MRA, OP, CW")

for item in [opcode, mra, op, cw]:
    print_systems(item)


# ui0 = 0b1100000
# ui1 = 0b0111111
# ui2 = 0b1111111
# ui3 = 0b0001001

# 0b1100000 0b0111111 0b1111111 0b0001001
