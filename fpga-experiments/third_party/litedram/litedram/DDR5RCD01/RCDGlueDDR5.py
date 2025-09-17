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


class RCDGlueDDR5Channel(Module):
    """
    DRCGlueDDR5Common,
    -------------
    This module provides glue logic for channel A and B common signals
    between RCD Simulation Pads and DDR5 Simulation Pads.
    This is required only to translate names between blocks,
    which used different naming conventions(UDIMM from host, RDIMM in RCD).

    Module
    ------

    Parameters
    ----------
        - pads_RCD
        - pads_SDRAM
        - quarter (default = "A")
    """
    def __init__(self, pads_RCD, pads_SDRAM, quarter="A"):
        quarter_to_signals = {
            #     ck_t  cd_c   cs        ca    rst
            "A": ["qa", "qa", ("qa", 0), "qa", ""],
            "B": ["qb", "qb", ("qb", 0), "qb", ""],
            "C": ["qc", "qc", ("qa", 1), "qa", ""],
            "D": ["qd", "qd", ("qb", 1), "qb", ""],
        }
        # Connect simPHY to RCD
        connection_matrix_sc = [
            ('ck_t', "ck_t"),
            ('ck_c', "ck_c"),
            ('cs_n', "cs_n"),
            ('ca',   "ca"),
            ('qrst_n', "reset_n"),
        ]
        src, dst = pads_RCD, pads_SDRAM

        for prefix, (src_name, dst_name) in zip(quarter_to_signals[quarter], connection_matrix_sc):
            if isinstance(prefix, str):
                logging.info(f'Connect : {prefix+src_name} to {dst_name}')
                self.comb += getattr(dst, dst_name).eq(getattr(src, prefix+src_name))
            else:
                prefix, idx = prefix
                logging.info(f'Connect : {prefix+src_name}[{idx}] to {dst_name}')
                self.comb += getattr(dst, dst_name).eq(getattr(src, prefix+src_name)[idx])


class RCDGlueDDR5DataBuffer(Module):
    """
    RCDGlueDDR5DataBuffer
    -------------
    This module provides glue logic for channels data signals
    between DDR5 Simulation Pads and RCD Simulation Pads.
    This is required only to translate names between blocks,
    which used different naming conventions(UDIMM from host, RDIMM in RCD).

    Module
    ------
    Parameters
    ----------
        - pads_RCD
        - pads_SDRAM
    """
    def __init__(self, pads_RCD, pads_SDRAM, interleave=False, offset=0):
        # Connect simPHY to RCD
        connection_matrix_sc = [
            ('dq', 'dq'),
            # ECC not yet supported
            # ('cb', 'cb'),
            ('dqs_t', 'dqs_t'),
            ('dqs_c', 'dqs_c'),
        ]
        dq_dqs_ratio = len(pads_SDRAM.dq)//len(pads_SDRAM.dqs_t)
        dq_start  = 0
        dq_step   = dq_dqs_ratio
        dqs_start = 0
        dqs_step  = 1
        if interleave:
            dq_start  = offset * dq_dqs_ratio
            dq_step   = 2 * dq_dqs_ratio
            dqs_start = offset
            dqs_step  = 2

        src, dst = pads_RCD, pads_SDRAM
        for src_name, dst_name in connection_matrix_sc:
            start_idx = dq_start
            step      = dq_step
            width     = dq_dqs_ratio
            if "dqs" in dst_name:
                start_idx = dqs_start
                step      = dqs_step
                wodth     = 1

            for suffix in ["", "_o", "_oe", "_i"]:
                src_sig = getattr(src, src_name+suffix)
                dst_sig = getattr(dst, dst_name+suffix)
                for dst_cnt, src_offset in enumerate(range(start_idx, len(src_sig), step)):
                    logging.info(
                        f'Connect : {src_name+suffix}'
                        f'[{src_offset}:{src_offset+width}] to {dst_name+suffix}'
                        f'[{dst_cnt*width}:{(dst_cnt+1)*width}]'
                    )
                    if suffix != "_i":
                        self.comb += dst_sig[dst_cnt*width:(dst_cnt+1)*width].eq(
                            src_sig[src_offset:src_offset+width])
                    else:
                        self.comb += src_sig[src_offset:src_offset+width].eq(
                            dst_sig[dst_cnt*width:(dst_cnt+1)*width] |
                            src_sig[src_offset:src_offset+width]
                        )


if __name__ == "__main__":
    raise NotSupportedException
