#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# python
import argparse
import logging
# migen
from migen import *
# LiteDRAM : RCD
from litedram.DDR5RCD01.DDR5RCD01Chip import DDR5RCD01Chip
from litedram.DDR5RCD01.DDR5RCD01DataBuffer import DDR5RCD01DataBuffer
from litedram.DDR5RCD01.DDR5RCD01CommonIngressSimulationPads import DDR5RCD01CommonIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01ChannelIngressSimulationPads import DDR5RCD01ChannelIngressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01CoreEgressSimulationPads import DDR5RCD01CoreEgressSimulationPads
from litedram.DDR5RCD01.DDR5RCD01SidebandSimulationPads import DDR5RCD01SidebandSimulationPads
from litedram.DDR5RCD01.DDR5RCD01DataBufferSimulationPads import DDR5RCD01DataBufferSimulationPads
from litedram.DDR5RCD01.DDR5RCD01Shell import DDR5RCD01Shell

from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import EngTest, UnderConstruction, NotSupportedException

class DDR5RCD01System(Module):
    """
    DDR5 RCD01 System
    -----------------
        The system encapsulates:
        - the RCD chip
        - the Data Buffer chips
    The System may be configured for RDIMM or LRDIMM type.
    In the RDIMM mode BCOM is unused and Data Buffer signals
    are passed through. The LRDIMM is not yet implemented.

    The hierarchical structure is:
        System:
        - RCD Shell or RCD Chip
        - Data Buffer Shell or Data Buffer Chip

    The "shell" is a view, which only implements pass-through function. The "chip"
    is a view, which implements the physical function.

    TODO enable BCOM support

    TODO attach a data buffer model

    Dual-channel support
    --------------------
    According to the specification the RCD system is always dual-channel, however,
    to enable quicker simulations, a single-channel mode is implemented.
    The convention is to pass 'None' object to the ingress of the B channel.
    This causes the RCD Core not to build the B channel.

    Module
    ------
    Ingress pads:
        - dq
        - A
        - B
        - common
        - sideband

    Egress pads:
        - dq
        - A
        - B
        - common

    Parameters
    ----------
    rcd_passthrough
        This parameter controls selection between the RCD Shell (false)
        and RCD Chip (true).

        Expected values:
            {True, False};

    sideband_type
        This parameter control selection of the sideband slave
        implemented in the RCD Chip. The JEDEC specification allows
        either I2C or I3C to be used. Mock type is defined to allow
        for simple communication in the simulations.

        Expected values:
            object of type <class sideband_type(Enum)>
    """

    def __init__(self,
                 pads_ingress_dq_A,
                 pads_ingress_dq_B,
                 pads_ingress_A,
                 pads_ingress_B,
                 pads_ingress_common,
                 pads_sideband,
                 rcd_passthrough=True,
                 sideband_type=sideband_type.I2C,
                 dimm_type=dimm_type.RDIMM,
                 ):

        if rcd_passthrough == True:
            RCD_cls = DDR5RCD01Shell
        else:
            RCD_cls = DDR5RCD01Chip

        xRCD = RCD_cls(
            pads_ingress_A      = pads_ingress_A,
            pads_ingress_B      = pads_ingress_B,
            pads_ingress_common = pads_ingress_common,
            pads_sideband       = pads_sideband,
            dimm_type           = dimm_type,
        )
        self.submodules += xRCD

        self.pads_egress_A = xRCD.pads_egress_A

        if dimm_type == dimm_type.LRDIMM:
            self.pads_bcom_A   = xRCD.pads_bcom_A
            if pads_ingress_B is not None:
                self.pads_bcom_B   = xRCD.pads_bcom_B

        # Data Buffer
        xDB_A = DDR5RCD01DataBuffer(
            pads_ingress = pads_ingress_dq_A,
            dimm_type    = dimm_type,
        )
        self.submodules += xDB_A
        self.pads_egress_dq_A = xDB_A.pads_egress

        if pads_ingress_B is not None:
            self.pads_egress_B = xRCD.pads_egress_B
            # Data Buffer
            xDB_B = DDR5RCD01DataBuffer(
                pads_ingress = pads_ingress_dq_B,
                dimm_typei   = dimm_type,
            )
            self.submodules += xDB_B
            self.pads_egress_dq_B = xDB_B.pads_egress


    @classmethod
    def run_constructors(cls):
        # Nice to have something similar in all classes
        pads_ingress_dq_A = DDR5RCD01DataBufferSimulationPads()
        pads_ingress_dq_B = DDR5RCD01DataBufferSimulationPads()
        pads_ingress_A = DDR5RCD01ChannelIngressSimulationPads()
        pads_ingress_B = DDR5RCD01ChannelIngressSimulationPads()
        pads_ingress_common = DDR5RCD01CommonIngressSimulationPads()
        pads_sideband = DDR5RCD01SidebandSimulationPads()

        xSystem_dc = cls(
            pads_ingress_dq_A=pads_ingress_dq_A,
            pads_ingress_dq_B=pads_ingress_dq_B,
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=pads_ingress_B,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=pads_sideband,
            rcd_passthrough=True,
            sideband_type=sideband_type.I2C,
        )

        xSystem_sc = cls(
            pads_ingress_dq_A=pads_ingress_dq_A,
            pads_ingress_dq_B=None,
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=None,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=pads_sideband,
            rcd_passthrough=True,
            sideband_type=sideband_type.I2C,
        )

        xSystem_dc = cls(
            pads_ingress_dq_A=pads_ingress_dq_A,
            pads_ingress_dq_B=pads_ingress_dq_B,
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=pads_ingress_B,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=None,
            rcd_passthrough=True,
            sideband_type=None,
        )

        xSystem_sc = cls(
            pads_ingress_dq_A=pads_ingress_dq_A,
            pads_ingress_dq_B=None,
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=None,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=None,
            rcd_passthrough=True,
            sideband_type=None,
        )

        xSystem_Core_dc = cls(
            pads_ingress_dq_A=pads_ingress_dq_A,
            pads_ingress_dq_B=pads_ingress_dq_B,
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=pads_ingress_B,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=pads_sideband,
            rcd_passthrough=False,
            sideband_type=sideband_type.I2C,
        )

        xSystem_Core_sc = cls(
            pads_ingress_dq_A=pads_ingress_dq_A,
            pads_ingress_dq_B=None,
            pads_ingress_A=pads_ingress_A,
            pads_ingress_B=None,
            pads_ingress_common=pads_ingress_common,
            pads_sideband=pads_sideband,
            rcd_passthrough=False,
            sideband_type=sideband_type.I2C,
        )


class TestBed(Module):
    def __init__(self):
        self.pads_ingress_dq_A = DDR5RCD01DataBufferSimulationPads()
        self.pads_ingress_dq_B = DDR5RCD01DataBufferSimulationPads()
        self.pads_ingress_A = DDR5RCD01ChannelIngressSimulationPads()
        self.pads_ingress_B = DDR5RCD01ChannelIngressSimulationPads()
        self.pads_ingress_common = DDR5RCD01CommonIngressSimulationPads()
        self.pads_sideband = DDR5RCD01SidebandSimulationPads()

        xSystem_dc = DDR5RCD01System(
            pads_ingress_dq_A=self.pads_ingress_dq_A,
            pads_ingress_dq_B=self.pads_ingress_dq_B,
            pads_ingress_A=self.pads_ingress_A,
            pads_ingress_B=self.pads_ingress_B,
            pads_ingress_common=self.pads_ingress_common,
            pads_sideband=self.pads_sideband,
            rcd_passthrough=True,
            sideband_type=sideband_type.I2C,
        )
        self.submodules.dut = xSystem_dc


def seq_cmds(tb):
    # TODO all commands are passed as if they were 2UIs long. To be fixed.
    # Single UI command
    yield from n_ui_dram_command(tb, nums=[0x01, 0x02], sel_cs="rank_AB")
    # 2 UI commands
    yield from n_ui_dram_command(tb, nums=[0x01, 0x02, 0x03, 0x04], sel_cs="rank_A")
    yield from n_ui_dram_command(tb, nums=[0xC0, 0xDE, 0xF0, 0x0D], sel_cs="rank_B")
    yield from n_ui_dram_command(tb, nums=[0xC0, 0xDE, 0xF0, 0x0D], sel_cs="rank_AB")
    yield from n_ui_dram_command(tb, nums=[0x0A, 0x0B, 0x0C, 0x0D], non_target_termination=True)
    yield from n_ui_dram_command(tb, nums=[0xDE, 0xAD, 0xBA, 0xBE], non_target_termination=True)
    yield from n_ui_dram_command(tb, nums=[0xC0, 0xDE, 0xF0, 0x0D], sel_cs="rank_AB")


def n_ui_dram_command(tb, nums, sel_cs="rank_AB", non_target_termination=False):
    """
    This function drives the interface with as in:
        "JEDEC 82-511 Figure 7
        One UI DRAM Command Timing Diagram"

    Nums can be any length to incroporate two, or more, UI commands

    The non target termination parameter extends the DCS assertion to the 2nd UI
    """
    if sel_cs == "rank_A":
        cs = 0b10
    elif sel_cs == "rank_B":
        cs = 0b01
    elif sel_cs == "rank_AB":
        cs = 0b00
    else:
        cs = 0b11

    SEQ_INACTIVE = [~0, 0]
    yield from drive_init(tb)
    # yield from set_parity(tb)

    sequence = [SEQ_INACTIVE]
    for id, num in enumerate(nums):
        if non_target_termination:
            if id in [0, 1, 2, 3]:
                sequence.append([cs, num])
            else:
                sequence.append([0b11, num])
        else:
            if id in [0, 1]:
                sequence.append([cs, num])
            else:
                sequence.append([0b11, num])

    sequence.append(SEQ_INACTIVE)

    for seq_cs, seq_ca in sequence:
        logging.debug(str(seq_cs) + " " + str(seq_ca))
        yield from drive_cs_ca(seq_cs, seq_ca, tb)
    for i in range(3):
        yield


def drive_init(tb):
    yield tb.pads_ingress_common.drst_n.eq(1)
    yield from drive_cs_ca(~0, 0, tb)


def drive_cs_ca(cs, ca, tb):
    yield tb.pads_ingress_A.dcs_n.eq(cs)
    yield tb.pads_ingress_A.dca.eq(ca)
    yield tb.pads_ingress_A.dpar.eq(1)
    yield tb.pads_ingress_B.dcs_n.eq(cs)
    yield tb.pads_ingress_B.dca.eq(ca)
    yield tb.pads_ingress_B.dpar.eq(1)
    yield


def run_test(tb):
    logging.debug('Write test')
    # yield from one_ui_dram_command(tb)
    INIT_CYCLES = CW_DA_REGS_NUM + 5
    yield from drive_init(tb)
    for b in [0, 1]*5:
        yield tb.pads_ingress_common.dck_t.eq(b)
        yield tb.pads_ingress_common.dck_c.eq(~b)
        yield
    for i in range(INIT_CYCLES):
        yield
    yield from seq_cmds(tb)
    for i in range(5):
        yield
    logging.debug('Yield from write test.')


def eng_test():
    eT = EngTest(level=logging.INFO)
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready. Simulating with migen...")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DDR5RCD01System")
    parser.add_argument("--run-example", action="store_true", help="Run class constructors")
    args = parser.parse_args()
    if args.run_example:
        DDR5RCD01System.run_constructors()
    else:
        eng_test()
