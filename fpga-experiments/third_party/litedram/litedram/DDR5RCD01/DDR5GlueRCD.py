#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# python
import logging
# migen
from migen import *
# RCD
from litedram.DDR5RCD01.DDR5RCD01ChannelIngressSimulationPads import DDR5RCD01ChannelIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01CommonIngressSimulationPads import DDR5RCD01CommonIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01DataBufferSimulationPads import DDR5RCD01DataBufferSimulationPads
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *


class DDR5GlueRCDCommon(Module):
    """
    DDR5GlueRCDCommon
    -------------
    This module provides glue logic for channel A and B common signals
    between DDR5 Simulation Pads and RCD Simulation Pads.
    This is required only to translate names between blocks,
    which used different naming conventions(UDIMM from host, RDIMM in RCD).

    Module
    ------

    Parameters
    ----------
        - pads_ddr5
        - pads_RCD
    """
    def __init__(self, pads_ddr5, pads_RCD):
        # Connect simPHY to RCD
        connection_matrix_sc = [
            ('ck_t', "dck_t", 'Forward'),
            ('ck_c', "dck_c", 'Forward'),
            ('reset_n', "drst_n", 'Forward'),
            ('alert_n', "alert_n", 'Reverse'),
        ]
        direction_to_buses = {
            'Forward': (pads_ddr5, pads_RCD),
            'Reverse': (pads_RCD, pads_ddr5),
        }

        for src_name, dst_name, direction in connection_matrix_sc:
            src, dst = direction_to_buses[direction]
            logging.info(f'Connect : {src_name} to {dst_name}')
            self.comb += getattr(dst, dst_name).eq(getattr(src, src_name))


class DDR5GlueRCDChannel(Module):
    """
    DDR5GlueRCDChannel
    -------------
    This module provides glue logic for channels CA signals
    between DDR5 Simulation Pads and RCD Simulation Pads.
    This is required only to translate names between blocks,
    which used different naming conventions(UDIMM from host, RDIMM in RCD).

    Module
    ------

    Parameters
    ----------
        - pads_ddr5
        - pads_RCD
        - prefix (default "")
    """
    def __init__(self, pads_ddr5, pads_RCD, prefix=""):
        # Connect simPHY to RCD
        connection_matrix_sc = [
            (f'{prefix}cs_n', 'dcs_n', 'Forward'),
            (f'{prefix}ca',   'dca',   'Forward'),
            (f'{prefix}par',  'dpar',  'Forward'),
        ]
        direction_to_buses = {
            'Forward': (pads_ddr5, pads_RCD),
            'Reverse': (pads_RCD, pads_ddr5),
        }

        for src_name, dst_name, direction in connection_matrix_sc:
            src, dst = direction_to_buses[direction]
            logging.info(f'Connect : {src_name} to {dst_name}')
            self.comb += getattr(dst, dst_name).eq(getattr(src, src_name))


class DDR5GlueRCDDataBuffer(Module):
    """
    DDR5GlueRCDDataBuffer
    -------------
    This module provides glue logic for channels data signals
    between DDR5 Simulation Pads and RCD Simulation Pads.
    This is required only to translate names between blocks,
    which used different naming conventions(UDIMM from host, RDIMM in RCD).

    Module
    ------
    Parameters
    ----------
        - pads_ddr5
        - pads_RCD
        - prefix (default "")
    """
    def __init__(self, pads_ddr5, pads_RCD, prefix=""):
        # Connect simPHY to RCD
        connection_matrix_sc = [
            (f'{prefix}dq', 'dq'),
            # ECC not yet supported
            # ('cb', 'cb', 'Forward'),
            (f'{prefix}dqs_t', 'dqs_t'),
            (f'{prefix}dqs_c', 'dqs_c'),
        ]

        src, dst = pads_ddr5, pads_RCD

        for src_name, dst_name in connection_matrix_sc:
            logging.info(f'Connect : {src_name} to {dst_name}')
            for suffix in ["", "_o", "_oe", "_i"]:
                if suffix != "_i":
                    self.comb += getattr(dst, dst_name+suffix).eq(getattr(src, src_name+suffix))
                else:
                    self.comb += getattr(src, src_name+suffix).eq(getattr(dst, dst_name+suffix))


if __name__ == "__main__":
    raise NotSupportedException
