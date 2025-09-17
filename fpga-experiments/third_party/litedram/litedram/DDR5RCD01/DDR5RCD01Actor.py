#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
from operator import xor
import enum
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.SimCSCADriver import SimCSCADriver
from litedram.DDR5RCD01.DDR5RCD01Decoder import DDR5RCD01Decoder
from litedram.DDR5RCD01.DDR5RCD01ActorMRW import DDR5RCD01ActorMRW


@enum.unique
class DDR5Opcodes(enum.IntEnum):
    """
    MRR
          | CA0||  CA1||  CA2||  CA3||  CA4||  CA5||  CA6|
    UI_0  |   H||    L||    H||    L||    H|| MRA0|| MRA1|
    UI_1  |MRA2|| MRA3|| MRA4|| MRA5|| MRA6|| MRA7||    V|
    UI_2  |   L||    L||    V||    V||    V||    V||    V|
    UI_3  |   V||    V||    V||   CW||    V||    V||    V|
          | CA0||  CA1||  CA2||  CA3||  CA4||  CA5||  CA6|
    MRW
          | CA0||  CA1||  CA2||  CA3||  CA4||  CA5||  CA6|
    UI_0  |   H||    L||    H||    L||    L|| MRA0|| MRA1|
    UI_1  |MRA2|| MRA3|| MRA4|| MRA5|| MRA6|| MRA7||    V|
    UI_2  | OP0||  OP1||  OP2||  OP3||  OP4||  OP5||  OP6|
    UI_3  | OP7||    V||    V||   CW||    V||    V||    V|
          | CA0||  CA1||  CA2||  CA3||  CA4||  CA5||  CA6|
    """
    MRR = 0b10101
    MRW = 0b00101


class DDR5Commands(enum.IntEnum):
    MRA_W = 8
    OP_W = 8


class DDR5RCD01Actor(Module):
    """
        DDR5 RCD01 Actor is the module, which:

            - ...


        Module
        ------


        Parameters
        ------
        max_ui_num

        cs_n_w

        ca_w

    """

    def __init__(self,
                 valid,
                 commands_cs_n,
                 commands_ca,
                 commands_par,
                 mrw_op_o,
                 reg_d,
                 reg_addr,
                 reg_we,
                 reg_q,
                 max_ui_num=4,
                 cs_n_w=2,
                 ca_w=7,
                 ):

        opcode = Signal(5)
        is_cmd_MRR = Signal()
        is_cmd_MRW = Signal()
        is_cmd_None = Signal()

        self.comb += If(
            valid,
            opcode.eq(commands_ca[0][0:5]),
        )
        self.comb += Case(
            opcode, {
                DDR5Opcodes.MRR: is_cmd_MRR.eq(1),
                DDR5Opcodes.MRW: is_cmd_MRW.eq(1),
                "default": is_cmd_None.eq(1),
            }
        )

        mrr_mra = Signal(DDR5Commands.MRA_W)
        mrr_cw = Signal()

        self.comb += If(
            is_cmd_MRR,
            mrr_mra.eq(Cat(commands_ca[0][5:8], commands_ca[1][0:6])),
            mrr_cw.eq(commands_ca[3][3]),
        )

        mrw_mra = Signal(DDR5Commands.MRA_W)
        mrw_cw = Signal()
        mrw_op = Signal(DDR5Commands.OP_W)
        mrw_op_o = Signal(DDR5Commands.OP_W)
        mrw_op_override = Signal()

        self.comb += If(
            is_cmd_MRW,
            mrw_mra.eq(Cat(commands_ca[0][5:8], commands_ca[1][0:6])),
            mrw_cw.eq(commands_ca[3][3]),
            mrw_op.eq(Cat(commands_ca[2], commands_ca[3][0])),
        )
        trigger_mrw = Signal()
        self.comb += trigger_mrw.eq(is_cmd_MRW & mrw_cw)

        xActorMRW = DDR5RCD01ActorMRW(
            trigger=trigger_mrw,
            mrw_mra=mrw_mra,
            mrw_op=mrw_op,
            mrw_cw=mrw_cw,
            RW5E_d=reg_d,
            RW5E_addr=reg_addr,
            RW5E_we=reg_we,
            RW5E_star_q=reg_q,
            mrw_op_o=mrw_op_o,
            mrw_op_override=mrw_op_override,
        )

        self.comb += If(
            mrw_op_override,
            mrw_op_o.eq(mrw_op_o),
        ).Else(
            mrw_op_o.eq(mrw_op),
        )


class TestBed(Module):
    def __init__(self):
        max_ui_num = 4
        cs_n_w = 2
        ca_w = 7
        if_ibuf = If_ibuf()
        self.tb_qvalid = Signal()
        self.tb_qcommands_cs_n = Array(Signal(cs_n_w)
                                       for y in range(max_ui_num))
        self.tb_qcommands_ca = Array(Signal(ca_w) for y in range(max_ui_num))
        self.tb_qcommands_par = Array(Signal() for y in range(max_ui_num))

        self.submodules.driver = SimCSCADriver(
            if_ibuf_o=if_ibuf,
        )

        self.submodules.decoder = DDR5RCD01Decoder(
            if_ibuf=if_ibuf,
            qvalid=self.tb_qvalid,
            qcommands_cs_n=self.tb_qcommands_cs_n,
            qcommands_ca=self.tb_qcommands_ca,
            qcommands_par=self.tb_qcommands_par,
            max_ui_num=max_ui_num,
            cs_n_w=cs_n_w,
            ca_w=ca_w,
        )

        self.mrw_op_o = Signal()
        self.reg_d = Signal(8)
        self.reg_addr = Signal(8)
        self.reg_we = Signal()
        self.reg_q = Signal(8)

        self.comb += self.reg_q.eq(0x5A)

        self.submodules.dut = DDR5RCD01Actor(
            valid=self.tb_qvalid,
            commands_cs_n=self.tb_qcommands_cs_n,
            commands_ca=self.tb_qcommands_ca,
            commands_par=self.tb_qcommands_par,
            mrw_op_o=self.mrw_op_o,
            reg_d=self.reg_d,
            reg_addr=self.reg_addr,
            reg_we=self.reg_we,
            reg_q=self.reg_q,
            max_ui_num=max_ui_num,
            cs_n_w=cs_n_w,
            ca_w=ca_w,
        )


def run_test(tb):
    logging.debug('Write test')
    yield from tb.driver.seq_cmds()
    for i in range(10):
        yield
    logging.debug('Yield from write test.')


if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
