#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# LiteDRAM : MODULE PADS
from litedram.phy.ddr5.simphy import DDR5SimulationPads
# LiteDRAM : RCD
from litedram.DDR5RCD01.DDR5RCD01CommonIngressSimulationPads import DDR5RCD01CommonIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01ChannelIngressSimulationPads import DDR5RCD01ChannelIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01DataBufferSimulationPads import DDR5RCD01DataBufferSimulationPads

from litedram.DDR5RCD01.DDR5GlueRCD import DDR5GlueRCDCommon, DDR5GlueRCDChannel, DDR5GlueRCDDataBuffer
from litedram.DDR5RCD01.RCDGlueDDR5 import RCDGlueDDR5Channel, RCDGlueDDR5DataBuffer

from litedram.DDR5RCD01.DDR5RCD01System import DDR5RCD01System
from litedram.DDR5RCD01.DDR5RCD01SidebandSimulationPads import DDR5RCD01SidebandSimulationPads

from litedram.DDR5RCD01.RCD_definitions import sideband_type as sb_enum
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *

class DDR5RCD01SystemWrapper(Module):
    """
        DDR5RCD01SystemWrapper
        ----------------------
        Module
        ------
        Parameters
        ----------
    """
    def __init__(self, phy_pads, pads_sideband, rcd_passthrough, sideband_type):
        common_pads = DDR5RCD01CommonIngressSimulationPads()
        self.submodules += DDR5GlueRCDCommon(phy_pads, common_pads)

        pre_and_suff = [("A_", "A_", "_A"), ("B_", "B_", "_B")] if hasattr(phy_pads, "A_cs_n") else [("", "A_", "_A"),]
        pads = dict(
            pads_A=None,
            pads_B=None,
            data_pads_A=None,
            data_pads_B=None,
        )
        for prefix, _, suffix in pre_and_suff:
            pads["pads"+suffix] = DDR5RCD01ChannelIngressSimulationPads(
                dcs_n_w = len(getattr(phy_pads, prefix+"cs_n")),
                dca_w   = len(getattr(phy_pads, prefix+"ca")),
            )
            self.submodules += DDR5GlueRCDChannel(phy_pads, pads["pads"+suffix], prefix)

            len_dq  = len(getattr(phy_pads, prefix+'dq'))
            len_cb  = len(getattr(phy_pads, prefix+'cb')) if hasattr(phy_pads, prefix+'cb') else 0
            len_dqs = len(getattr(phy_pads, prefix+'dqs_t'))
            pads['data_pads'+suffix] = DDR5RCD01DataBufferSimulationPads(
                dq_w  = len_dq,
                cb_w  = len_cb,
                dqs_w = len_dqs,
            )
            self.submodules += DDR5GlueRCDDataBuffer(phy_pads, pads['data_pads'+suffix], prefix)

        xRCDSystem = DDR5RCD01System(
            pads_ingress_dq_A   = pads['data_pads_A'],
            pads_ingress_dq_B   = pads['data_pads_B'],
            pads_ingress_A      = pads['pads_A'],
            pads_ingress_B      = pads['pads_B'],
            pads_ingress_common = common_pads,
            pads_sideband   = pads_sideband,
            sideband_type   = sideband_type,
            rcd_passthrough = rcd_passthrough,
        )
        self.submodules.xRCDSystem = xRCDSystem

        quarters = {
            "A": "front_top",
            "B": "front_bottom",
            "C": "back_top",
            "D": "back_bottom",
        }
        quarter_to_offset = {
            "A": 1,
            "B": 0,
            "C": 1,
            "D": 0,
        }

        for prefix, rcd_pre, suffix in pre_and_suff:
            len_dq  = len(getattr(phy_pads, prefix+'dq'))
            len_cb  = len(getattr(phy_pads, prefix+'cb')) if hasattr(phy_pads, prefix+'cb') else 0
            len_dqs = len(getattr(phy_pads, prefix+'dqs_t'))
            dq_dqs_ratio = (len_dq + len_cb)//len_dqs
            egress    = getattr(xRCDSystem, 'pads_egress'+suffix)
            egress_dq = getattr(xRCDSystem, 'pads_egress_dq'+suffix)

            top = False
            if (len_dq//dq_dqs_ratio) % 2 == 0:
                len_dq //= 2
                top = True
            pads = []
            for quarter, val in quarters.items():
                if "top" in val and top:
                    setattr(self, rcd_pre+val,
                        DDR5SimulationPads(
                            databits=len_dq,
                            dq_dqs_ratio=dq_dqs_ratio,
                        )
                    )
                    pads.append((quarter, getattr(self, rcd_pre+val)))
                else:
                    setattr(self, rcd_pre+val,
                        DDR5SimulationPads(
                            databits=len_dq,
                            dq_dqs_ratio=dq_dqs_ratio,
                        )
                    )
                    pads.append((quarter, getattr(self, rcd_pre+val)))
            for quarter, pad in pads:
                self.submodules += RCDGlueDDR5Channel(egress, pad, quarter)
                self.submodules += RCDGlueDDR5DataBuffer(
                    egress_dq,
                    pad,
                    interleave=top,
                    offset=quarter_to_offset[quarter]
                )
            self.comb += egress.derror_in_n.eq(reduce(or_, [pad[1].alert_n for pad in pads]))
