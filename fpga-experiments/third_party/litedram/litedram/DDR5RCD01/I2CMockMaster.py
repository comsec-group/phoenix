#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# Litex
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *
# LiteDRAM : RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.DDR5RCD01SidebandMockSimulationPads import DDR5RCD01SidebandMockSimulationPads


class I2CMockMasterWrapper(Module, AutoCSR):
    def __init__(self, pads_sideband: DDR5RCD01SidebandMockSimulationPads):
        if_mock = If_sideband_mock()

        self.submodules.internal = I2CMockMaster(if_mock)

        self.comb += [
            if_mock.we.eq(pads_sideband.we),
            if_mock.channel.eq(pads_sideband.channel),
            if_mock.page_num.eq(pads_sideband.page_num),
            if_mock.reg_num.eq(pads_sideband.reg_num),
            if_mock.data.eq(pads_sideband.data),
        ]

class I2CMockMaster(Module, AutoCSR):
    """
        I2C Mock Master
        ---------------

        TODO Documentation

        TODO Implementation: a parallel interface based on chapter 7 JEDEC spec
    """

    def __init__(self, if_mock: If_sideband_mock):
        self._channel  = CSRStorage(4)
        self._page_num = CSRStorage(8)
        self._reg_num  = CSRStorage(8)
        self._data     = CSRStorage(8)
        self._execute  = CSR()

        self.comb += If(self._execute.re,
            If(self._execute.r == 0,     # perform a write
                if_mock.we.eq(1),
                if_mock.channel.eq(self._channel.storage),
                if_mock.page_num.eq(self._page_num.storage),
                if_mock.reg_num.eq(self._reg_num.storage),
                if_mock.data.eq(self._data.storage),
            ).Elif(self._execute.r == 1, # perform a read
                # not implemented yet
            ),
        )

    def write(self, channel, page_num, reg_num, data):
        yield from self._channel.write(channel)
        yield from self._page_num.write(page_num)
        yield from self._reg_num.write(reg_num)
        yield from self._data.write(data)
        yield from self._execute.write(0)

    def rcd_read(self, dev, channel, page_num, reg_num):
        return [0, 0, 0, 0]

    def rcd_write(self, _dev, channel, page_num, reg_num, data, size):
        for i, byte in enumerate(data[:size]):
            yield from self.write(channel, page_num, reg_num + i, byte)

    def enter_dcstm(self, channel, rank):
        # taken from litex/soc/software/liblitedram/ddr5_helpers.c
        rw_data = self.rcd_read(0, channel, 0, 0)

        rw_data[1] &= ~(1 << 5)
        rw_data[2] &= ~(0b11 << (2 * channel))
        rw_data[2] |= (0b10 | (rank & 1)) << (2 * channel)

        yield from self.rcd_write(0, channel, 0, 0, rw_data, 4)

    def exit_dcstm(self, channel, rank):
        # taken from litex/soc/software/liblitedram/ddr5_helpers.c
        rw_data = self.rcd_read(0, channel, 0, 0)

        rw_data[2] &= ~(0b11 << (2 * channel))

        yield from self.rcd_write(0, channel, 0, 2, [rw_data[2]], 1)

    def rcd_set_dimm_operating_speed(self, channel, rank, target_speed):
        assert target_speed == -1, "We only simulate setting speed PLL bypass mode"

        coarse = 0x0f # PLL bypass mode
        fine   = 0x00 # any fine-grained speed bin will do
        yield from self.rcd_write(0, channel, 0, 5, [coarse], 1)
        yield from self.rcd_write(0, channel, 0, 6, [fine], 1)


if __name__ == "__main__":
    raise NotSupportedException
