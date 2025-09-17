#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from migen import *
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_interfaces_external import *
from litedram.DDR5RCD01.RCD_utils import *
# Submodules
from litedram.DDR5RCD01.DDR5RCD01LoopbackCommon import DDR5RCD01LoopbackCommon
from litedram.DDR5RCD01.DDR5RCD01Alert import DDR5RCD01Alert
from litedram.DDR5RCD01.DDR5RCD01PLL import DDR5RCD01PLL


class DDR5RCD01Common(Module):
    """
        DDR5 RCD Common
        ---------------
    This module encapsulates the following features:
        - PLL
        - Loopback
        - Alert_n
        - Reset distribution

        Module
        ------
    Connections to host:
        - alert_n
        - qlbd, qlbs
        - drst_n
        - dck_t,dck_c
    Connections to each channel:
        - error,
        - rst,
        - lbd, lbs
    Configuration signals:
        - config_a
        - config_b

    """

    def __init__(self,
                if_host_ck_rst,
                if_host_alert_n,
                if_host_lb,
                if_pll,
                if_channel_A,
                if_channel_B,
                if_ctrl_common,
                if_config_common,
                ):

        xloopback=DDR5RCD01LoopbackCommon(
            lbd_a=if_channel_A.dlbd,
            lbs_a=if_channel_A.dlbs,
            lbd_b=if_channel_B.dlbd,
            lbs_b=if_channel_B.dlbs,
            qlbd=if_host_lb.qlbd,
            qlbs=if_host_lb.qlbs,
            if_ctrl=if_ctrl_common,
            if_config=if_config_common,
        )
        self.submodules.xloopback = xloopback

        xalert = DDR5RCD01Alert(
            err_a=if_channel_A.derror_in_n,
            err_b=if_channel_B.derror_in_n,
            alert_n=if_host_alert_n.alert_n,
            if_ctrl=if_ctrl_common,
            if_config=if_config_common,
        )
        self.submodules.xalert = xalert

        xpll = DDR5RCD01PLL(
            if_ck_rst=if_host_ck_rst,
            if_pll=if_pll,
            if_ctrl=if_ctrl_common,
            if_config=if_config_common,
        )
        self.submodules.xpll = xpll

        """
            Reset distribution
        """
        self.comb += if_channel_A.qrst_n.eq(if_host_ck_rst.drst_n)
        self.comb += if_channel_B.qrst_n.eq(if_host_ck_rst.drst_n)


class TestBed(Module):
    def __init__(self):

        self.submodules.dut = DDR5RCD01Common()


def run_test(tb):
    logging.debug('Write test')
    for i in range(5):
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
