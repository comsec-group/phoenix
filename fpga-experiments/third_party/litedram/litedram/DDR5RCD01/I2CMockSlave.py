#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# LiteDRAM : RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.DDR5RCD01RegistersPads import DDR5RCD01RegistersPads
from litedram.DDR5RCD01.DDR5RCD01SidebandMockSimulationPads import DDR5RCD01SidebandMockSimulationPads

# JESD82-511 Table 42
CHANNEL_A_ADDRESS = 0b0000
CHANNEL_B_ADDRESS = 0b0001


class I2CMockSlaveWrapper(Module):
    def __init__(self, pads_sideband: DDR5RCD01SidebandMockSimulationPads):
        if_mock = If_sideband_mock()
        if_regs_A = If_registers()
        if_regs_B = If_registers()

        self.pads_registers = DDR5RCD01RegistersPads()

        self.submodules += I2CMockSlave(if_mock, if_regs_A, if_regs_B)

        self.comb += [
            if_mock.we.eq(pads_sideband.we),
            if_mock.channel.eq(pads_sideband.channel),
            if_mock.page_num.eq(pads_sideband.page_num),
            if_mock.reg_num.eq(pads_sideband.reg_num),
            if_mock.data.eq(pads_sideband.data),

            self.pads_registers.we_A.eq(if_regs_A.we),
            self.pads_registers.d_A.eq(if_regs_A.d),
            self.pads_registers.addr_A.eq(if_regs_A.addr),
            if_regs_A.q.eq(self.pads_registers.q_A),

            self.pads_registers.we_B.eq(if_regs_B.we),
            self.pads_registers.d_B.eq(if_regs_B.d),
            self.pads_registers.addr_B.eq(if_regs_B.addr),
            if_regs_B.q.eq(self.pads_registers.q_B),
        ]

class I2CMockSlave(Module):
    """
        I2C Mock Slave
        --------------

        TODO Documentation

        TODO Implementation: a parallel interface based on chapter 7 JEDEC spec
    """
    def __init__(self, if_mock: If_sideband_mock, if_regs_A: If_registers, if_regs_B: If_registers):
        channel = Signal(4)
        page_num = Signal(8)
        reg_num = Signal(8)
        data = Signal(8)

        self.submodules.fsm = fsm = FSM()

        fsm.act("IDLE",
            If(if_mock.we,
                NextValue(data, if_mock.data),
                NextValue(page_num, if_mock.page_num),
                NextValue(reg_num, if_mock.reg_num),
                NextValue(channel, if_mock.channel),
                NextState("SET_PAGE"),
            ),
        )

        fsm.act("SET_PAGE",
            Case(channel, {
                CHANNEL_A_ADDRESS: [
                    if_regs_A.we.eq(1),
                    if_regs_A.d.eq(page_num),
                    if_regs_A.addr.eq(ADDR_CW_PAGE),
                ],
                CHANNEL_B_ADDRESS: [
                    if_regs_B.we.eq(1),
                    if_regs_B.d.eq(page_num),
                    if_regs_B.addr.eq(ADDR_CW_PAGE),
                ]
            }),
            NextState("WRITE"),
        )

        fsm.act("WRITE",
            Case(channel, {
                CHANNEL_A_ADDRESS: [
                    if_regs_A.we.eq(1),
                    if_regs_A.d.eq(data),
                    if_regs_A.addr.eq(reg_num),
                ],
                CHANNEL_B_ADDRESS: [
                    if_regs_B.we.eq(1),
                    if_regs_B.d.eq(data),
                    if_regs_B.addr.eq(reg_num),
                ]
            }),
            NextState("IDLE"),
        )


if __name__ == "__main__":
    raise NotSupportedException
