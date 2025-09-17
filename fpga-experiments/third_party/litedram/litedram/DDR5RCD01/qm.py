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

def print_systems(a,ins=True):
    if ins:
        print("[Base10] = " + format(a,'#8d'), end=' ')
        print("[Base 2] = " + format(a,'#009b'), end=' ')
        print("[Base16] = " + format(a,'#6x'))
    else:
        print("[Base10] = " + format(a,'#8d'), end=' ')
        print("[Base 2] = " + format(a,'#016b'), end=' ')
        print("[Base16] = " + format(a,'#6x'))

def deserialize(a,b):
    return (a << 7) | b

parser = argparse.ArgumentParser(description="Math helper for RCD debugging")
parser.add_argument('ui0')
parser.add_argument('ui1')

args = parser.parse_args()

if args.ui0.startswith("0x"):
    ui0 = int(args.ui0,16)
else:
    ui0 = int(args.ui0)

if args.ui1.startswith("0x"):
    ui1 = int(args.ui1,16)
else:
    ui1 = int(args.ui1)

""" Make sure uis are 7 bit integers """
assert ui0 >= 0
assert ui0 < 128

assert ui1 >= 0
assert ui1 < 128

uid = deserialize(ui1,ui0)
nuid = (~uid) & 0x3FFF

print_systems(ui0)
print_systems(ui1)
print_systems(uid,False)
print_systems(nuid)

