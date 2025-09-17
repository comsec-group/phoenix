#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen.fhdl.structure import Signal

class BasePHYOutput:
    """
        Unserialized output of DDR5PHY.
        Has to be serialized by concrete implementation.
    """
    def __init__(self, nphases, databits, nranks, nibbles, with_sub_channels=False, name=None):
        self.reset_n = Signal(2*nphases, reset=~0)  # Serializer will work in ddr mode
        self.alert_n = Signal(2*nphases)            # Deserializer will work in ddr mode

        prefixes = [""] if not with_sub_channels else ["A_", "B_"]

        for prefix in prefixes:
            setattr(self, prefix+'cs_n', [Signal(2*nphases, reset=2**(2*nphases)-1, name=name and f"{name}_{i}_cs_n") for i in range(nranks)])
            setattr(self, prefix+'ca',   [Signal(2*nphases, name=name and f"{name}_{i}_ca") for i in range(14)])
            # 2*nphases, as phy will run in ddr mode

            setattr(self, prefix+'par',  Signal(2*nphases, name=name and name+"par_n"))

            setattr(self, prefix+'dq_o',  [Signal(2*nphases, name=name and f"{name}_{i}_dq_o") for i in range(databits)])
            setattr(self, prefix+'dq_oe', [Signal(2*nphases, name=name and f"{name}_{i}_dq_oe") for i in range(nibbles)])
            setattr(self, prefix+'dq_i',  [Signal(2*nphases, name=name and f"{name}_{i}_dq_i") for i in range(databits)])

            setattr(self, prefix+'dm_n_o',  [Signal(2*nphases, name=name and f"{name}_{i}_dm_n_o") for i in range(nibbles)])
            setattr(self, prefix+'dm_n_i',  [Signal(2*nphases, name=name and f"{name}_{i}_dm_i_o") for i in range(nibbles)])

            setattr(self, prefix+'dqs_t_o',  [Signal(2*nphases, name=name and f"{name}_{i}_dqs_t_o") for i in range(nibbles)])
            setattr(self, prefix+'dqs_t_i',  [Signal(2*nphases, name=name and f"{name}_{i}_dqs_t_i") for i in range(nibbles)])
            setattr(self, prefix+'dqs_oe',   [Signal(2*nphases, name=name and f"{name}_{i}_dqs_oe") for i in range(nibbles)])
            setattr(self, prefix+'dqs_c_o',  [Signal(2*nphases, name=name and f"{name}_{i}_dqs_c_o") for i in range(nibbles)])
            setattr(self, prefix+'dqs_c_i',  [Signal(2*nphases, name=name and f"{name}_{i}_dqs_c_i") for i in range(nibbles)])

