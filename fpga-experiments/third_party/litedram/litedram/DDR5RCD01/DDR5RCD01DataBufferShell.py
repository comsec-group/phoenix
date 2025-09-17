#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

#python
from collections import defaultdict
# migen
from migen import *
# LiteDRAM : RCD
from litedram.DDR5RCD01.DDR5RCD01DataBufferSimulationPads import DDR5RCD01DataBufferSimulationPads


class DDR5RCD01DataBufferShell(Module):
    """
    DRAM Data bus pass-through
    """

    def __init__(self, pads_ingress, **kwargs):
        has_cb = hasattr(pads_ingress, 'cb')
        self.pads_egress = DDR5RCD01DataBufferSimulationPads(
            dq_w  = len(pads_ingress.dq),
            cb_w  = len(pads_ingress.cb) if has_cb else 0,
            dqs_w = len(pads_ingress.dqs_t),
        )
        direction = defaultdict(lambda: (pads_ingress, self.pads_egress))
        direction["_i"] = (self.pads_egress, pads_ingress)
        signal_names = [signal.name for signal in self.pads_egress.layout() if hasattr(pads_ingress, signal.name)]
        for signal in signal_names:
            for sufix in ["", "_o", "_oe", "_i"]:
                src, dst = direction[sufix]
                src_sig = getattr(src, signal+sufix)
                dst_sig = getattr(dst, signal+sufix)
                self.comb += dst_sig.eq(src_sig)


if __name__ == "__main__":
    pads_ingress = DDR5RCD01DataBufferSimulationPads()
    xShell = DDR5RCD01DataBufferShell(
        pads_ingress=pads_ingress
    )
