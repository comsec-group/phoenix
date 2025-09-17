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


class I2CMockMasterPseudoCode(Module):
    """
        I2C Mock Master
        ---------------

    """

    def __init__(self):
        """
        Host/sideband must know from spec whether he wants to do a write to registers or pages

        void register_write_unit8(register_address, write_data){
            assert register_address >= 0
            assert register_address <= 127
            /* Driver-specific write here*/
            TODO
            /* */
        }

        void set_page(write_data){
            assert write_data >= 0
            assert write_data <= 255
            register_write_unit8(0x5F, write_data)
        }

        void write(page_address, register_address, write_data){
            if register_address > 0x5F
                currently_set_page = read(0x5F)
                if page_address != currently_set_page
                    set_page(page_address)
            register_write_uint8(register_address,write_data)
        }

        void set_register_pointer(write_data){
            assert write_data >= 0
            assert write_data <= 127
            register_write_unit8(0x5E, write_data)
        }

        uint8 read(page_address, register_address){
            if register_address > 0x5f
                set_page(page_address)
            set_register_pointer(register_address)
            /* Driver-specific read here*/
            TODO
            /* */
        }

        Example use-cases:
        Host/Sideband writes 0xAA to Directly Addressable Register 0x10
        register_write_unit8(0x10,0xAA)
        or equivalently
        write(0x00, 0x10, 0xAA)

        Host/Sideband writes the same data to Page[2] Register 0x10
        Host must consider that the 0x10-th register in the page is
        at the offset 0x5F+0x10
        register_address = 0x5F + 0x10
        write(0x02, register_address, 0xAA)

        """
        pass


if __name__ == "__main__":
    raise NotSupportedException
