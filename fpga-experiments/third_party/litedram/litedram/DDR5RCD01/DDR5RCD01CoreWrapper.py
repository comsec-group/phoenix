#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from operator import xor
from migen import *
from migen.fhdl import verilog
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
# Simulation Pads
from litedram.DDR5RCD01.DDR5RCD01CoreEgressSimulationPads import DDR5RCD01CoreEgressSimulationPads
# Submodules
from litedram.DDR5RCD01.DDR5RCD01Core import DDR5RCD01Core


class DDR5RCD01CoreWrapper(Module):
    """
    DDR5 RCD01 Core Wrapper
    -----------------------
    The Core Wrapper connects the Simulations Pads to the Core's interfaces.

    TODO BCOM is unconnected

    TODO Sideband is unconnected

    Module
    ------
        - A
        - B
        - Common

    Parameters
    ----------
    None

    """

    def __init__(self,
                 pads_ingress_A,
                 pads_ingress_B,
                 pads_ingress_common,
                 pads_registers,
                 **kwargs):

        self.pads_egress_A = DDR5RCD01CoreEgressSimulationPads()
        if pads_ingress_B is not None:
            self.pads_egress_B = DDR5RCD01CoreEgressSimulationPads()

        if_ck_rst = If_ck_rst()
        if_sdram_A = If_channel_sdram()
        if_sdram_B = If_channel_sdram()
        if_alert_n = If_alert_n()
        if_ibuf_A = If_ibuf()
        if_ibuf_B = If_ibuf()
        if_obuf_A = If_obuf()
        if_obuf_B = If_obuf()
        if_lb = If_lb()
        if_bcom_A = If_bcom()
        if_bcom_B = If_bcom()
        if_regs_A = If_registers()
        if_regs_B = If_registers()
        if pads_ingress_B is not None:
            is_dual_channel = True
        else:
            is_dual_channel = False

        self.submodules.xCore = DDR5RCD01Core(
            if_ck_rst=if_ck_rst,
            if_sdram_A=if_sdram_A,
            if_sdram_B=if_sdram_B,
            if_alert_n=if_alert_n,
            if_ibuf_A=if_ibuf_A,
            if_ibuf_B=if_ibuf_B,
            if_obuf_A=if_obuf_A,
            if_obuf_B=if_obuf_B,
            if_lb=if_lb,
            if_bcom_A=if_bcom_A,
            if_bcom_B=if_bcom_B,
            if_regs_A=if_regs_A,
            if_regs_B=if_regs_B,
            is_dual_channel=is_dual_channel,
        )

        self.comb += if_ck_rst.drst_n.eq(pads_ingress_common.drst_n)
        self.comb += if_ck_rst.dck_t.eq(pads_ingress_common.dck_t)
        self.comb += if_ck_rst.dck_c.eq(pads_ingress_common.dck_c)

        self.comb += pads_ingress_common.alert_n.eq(if_alert_n.alert_n)
        self.comb += pads_ingress_common.qlbd.eq(if_lb.qlbd)
        self.comb += pads_ingress_common.qlbs.eq(if_lb.qlbs)

        self.comb += if_ibuf_A.dcs_n.eq(pads_ingress_A.dcs_n)
        self.comb += if_ibuf_A.dca.eq(pads_ingress_A.dca)
        self.comb += if_ibuf_A.dpar.eq(pads_ingress_A.dpar)

        self.comb += self.pads_egress_A.dlbd.eq(if_sdram_A.dlbd)
        self.comb += self.pads_egress_A.dlbs.eq(if_sdram_A.dlbs)

        self.comb += self.pads_egress_A.qrst_n.eq(if_sdram_A.qrst_n)
        self.comb += self.pads_egress_A.derror_in_n.eq(if_sdram_A.derror_in_n)
        self.comb += self.pads_egress_A.qacs_n.eq(if_obuf_A.qacs_a_n)
        self.comb += self.pads_egress_A.qaca.eq(if_obuf_A.qaca_a)

        self.comb += self.pads_egress_A.qbcs_n.eq(if_obuf_A.qacs_b_n)
        self.comb += self.pads_egress_A.qbca.eq(if_obuf_A.qaca_b)

        self.comb += self.pads_egress_A.qack_t.eq(if_obuf_A.qack_t)
        self.comb += self.pads_egress_A.qack_c.eq(if_obuf_A.qack_c)
        self.comb += self.pads_egress_A.qbck_t.eq(if_obuf_A.qbck_t)
        self.comb += self.pads_egress_A.qbck_c.eq(if_obuf_A.qbck_c)
        self.comb += self.pads_egress_A.qcck_t.eq(if_obuf_A.qcck_t)
        self.comb += self.pads_egress_A.qcck_c.eq(if_obuf_A.qcck_c)
        self.comb += self.pads_egress_A.qdck_t.eq(if_obuf_A.qdck_t)
        self.comb += self.pads_egress_A.qdck_c.eq(if_obuf_A.qdck_c)

        self.comb += if_regs_A.we.eq(pads_registers.we_A)
        self.comb += if_regs_A.d.eq(pads_registers.we_A)
        self.comb += if_regs_A.addr.eq(pads_registers.we_A)
        self.comb += pads_registers.q_A.eq(if_regs_A.q)

        if pads_ingress_B is not None:
            self.comb += if_ibuf_B.dcs_n.eq(pads_ingress_B.dcs_n)
            self.comb += if_ibuf_B.dca.eq(pads_ingress_B.dca)
            self.comb += if_ibuf_B.dpar.eq(pads_ingress_B.dpar)
            self.comb += self.pads_egress_B.dlbd.eq(if_sdram_B.dlbd)
            self.comb += self.pads_egress_B.dlbs.eq(if_sdram_B.dlbs)
            self.comb += self.pads_egress_B.qrst_n.eq(if_sdram_B.qrst_n)
            self.comb += self.pads_egress_B.derror_in_n.eq(if_sdram_B.derror_in_n)
            self.comb += self.pads_egress_B.qacs_n.eq(if_obuf_B.qacs_a_n)
            self.comb += self.pads_egress_B.qaca.eq(if_obuf_B.qaca_a)
            self.comb += self.pads_egress_B.qbcs_n.eq(if_obuf_B.qacs_b_n)
            self.comb += self.pads_egress_B.qbca.eq(if_obuf_B.qaca_b)
            self.comb += self.pads_egress_B.qack_t.eq(if_obuf_B.qack_t)
            self.comb += self.pads_egress_B.qack_c.eq(if_obuf_B.qack_c)
            self.comb += self.pads_egress_B.qbck_t.eq(if_obuf_B.qbck_t)
            self.comb += self.pads_egress_B.qbck_c.eq(if_obuf_B.qbck_c)
            self.comb += self.pads_egress_B.qcck_t.eq(if_obuf_B.qcck_t)
            self.comb += self.pads_egress_B.qcck_c.eq(if_obuf_B.qcck_c)
            self.comb += self.pads_egress_B.qdck_t.eq(if_obuf_B.qdck_t)
            self.comb += self.pads_egress_B.qdck_c.eq(if_obuf_B.qdck_c)

            self.comb += if_regs_B.we.eq(pads_registers.we_B)
            self.comb += if_regs_B.d.eq(pads_registers.we_B)
            self.comb += if_regs_B.addr.eq(pads_registers.we_B)
            self.comb += pads_registers.q_B.eq(if_regs_B.q)



if __name__ == "__main__":
    raise NotSupportedException
