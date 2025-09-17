#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# migen
from migen import *
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01CommonIngressSimulationPads import DDR5RCD01CommonIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01ChannelIngressSimulationPads import DDR5RCD01ChannelIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01SidebandSimulationPads import DDR5RCD01SidebandSimulationPads
from litedram.DDR5RCD01.DDR5RCD01CoreWrapper import DDR5RCD01CoreWrapper
from litedram.DDR5RCD01.I2CSlave import I2CSlave
from litedram.DDR5RCD01.I3CSlave import I3CSlave
from litedram.DDR5RCD01.I2CMockSlave import I2CMockSlaveWrapper


class DDR5RCD01Chip(Module):
    """
    DDR5 RCD01 Chip
    ---------------

    The Chip is a module, which integrates the sideband slave with the RCD Core. The
    RCD Core is encapsulated in a wrapper to connect the Simulation Pads to the Core
    interfaces.

    Module
    ------
    Simulation pads:
        - A,
        - B,
        - common,
        - sideband

    Parameters
    ----------
    c.f. DDR5RCD01System

    """

    def __init__(self,
                 pads_ingress_A,
                 pads_ingress_B,
                 pads_ingress_common,
                 pads_sideband,
                 sideband_type=sideband_type.MOCK,
                 dimm_type=dimm_type.RDIMM,
                 **kwargs):
        """
            Sideband
        """
        if sideband_type == sideband_type.I2C:
            iXC_slave = I2CSlave(pads_sideband)
        elif sideband_type == sideband_type.I3C:
            iXC_slave = I3CSlave(pads_sideband)
        elif sideband_type == sideband_type.MOCK:
            iXC_slave = I2CMockSlaveWrapper(pads_sideband)
        else:
            raise NotImplementedError("Only i2c and i3c are supported options")
        self.submodules.iXC_slave = iXC_slave

        """
            Core Wrapper
        """
        if dimm_type == dimm_type.RDIMM:
            xCore = DDR5RCD01CoreWrapper(
                pads_ingress_A=pads_ingress_A,
                pads_ingress_B=pads_ingress_B,
                pads_ingress_common=pads_ingress_common,
                pads_registers=iXC_slave.pads_registers,
            )
            self.submodules.xCore = xCore
        elif dimm_type == dimm_type.LRDIMM:
            raise NotImplementedError("LRDIMM is not supported")

        self.pads_egress_A = xCore.pads_egress_A
        if pads_ingress_B is not None:
            self.pads_egress_B = xCore.pads_egress_B


if __name__ == "__main__":

    pads_ingress_A = DDR5RCD01ChannelIngressSimulationPads()
    pads_ingress_B = DDR5RCD01ChannelIngressSimulationPads()
    pads_ingress_common = DDR5RCD01CommonIngressSimulationPads()
    pads_sideband = DDR5RCD01SidebandSimulationPads()

    xChip = DDR5RCD01Chip(
        pads_ingress_A=pads_ingress_A,
        pads_ingress_B=pads_ingress_B,
        pads_ingress_common=pads_ingress_common,
        pads_sideband=pads_sideband,
        sideband_type=sideband_type.MOCK,
        dimm_type=dimm_type.RDIMM,
    )

    xChip = DDR5RCD01Chip(
        pads_ingress_A=pads_ingress_A,
        pads_ingress_B=None,
        pads_ingress_common=pads_ingress_common,
        pads_sideband=pads_sideband,
        sideband_type=sideband_type.MOCK,
        dimm_type=dimm_type.RDIMM,
    )
    try:
        xChip = DDR5RCD01Chip(
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=None,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=pads_sideband,
            sideband_type=sideband_type.MOCK,
            dimm_type=dimm_type.LRDIMM,
        )
    except:
        pass

    try:
        xChip = DDR5RCD01Chip(
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=None,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=pads_sideband,
            sideband_type=sideband_type.I2C,
            dimm_type=dimm_type.LRDIMM,
        )
    except:
        pass
