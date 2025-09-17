#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

# Python
import logging
# migen
from migen import *
from migen.fhdl import verilog
# Litex
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_utils import *
from litedram.DDR5RCD01.RCD_interfaces import *
#
from litedram.DDR5RCD01.DDR5RCD01OutBuf import DDR5RCD01OutBuf


class DDR5RCD01OutputBuffer_CSCA(Module):
    """DDR5 RCD01 Output Buffer
    TODO Documentation
    d         - Input : data
    oe        - Input : output enable
    o_inv_en  - Input : output inversion enable
    frac_p    - Input : Fractional (n/64) phase delay select; frac_p==0 -> no delay
    q         - Output: data
    # Driver strength is not on implementation list, also: slew rate control
    """

    def __init__(self, if_i_csca, if_o_csca, if_ctrl, sig_disable_level=~0):
        # Single Row CS Bus
        xoutbuf_qcs_n = DDR5RCD01OutBuf(
            d=if_i_csca.qcs_n,
            q=if_o_csca.qcs_n,
            oe=if_ctrl.oe_qcs_n,
            o_inv_en=if_ctrl.o_inv_en_qcs_n,
            tie_high = if_ctrl.tie_high_cs,
            tie_low = if_ctrl.tie_low_cs,
            sig_disable_level=sig_disable_level
        )
        self.submodules += xoutbuf_qcs_n
        # Single Row CA Bus
        xoutbuf_qca = DDR5RCD01OutBuf(
            d=if_i_csca.qca,
            q=if_o_csca.qca,
            oe=if_ctrl.oe_qca,
            o_inv_en=if_ctrl.o_inv_en_qca,
            tie_high = if_ctrl.tie_high_ca,
            tie_low = if_ctrl.tie_low_ca,
            sig_disable_level=sig_disable_level
        )
        self.submodules += xoutbuf_qca

        # TODO Implement fractional delay here, if applicable


class TestBed(Module):
    def __init__(self):

        self.ctrl_if = If_ctrl_obuf_CSCA()
        self.iif_csca = If_bus_csca()
        self.iif_clks = If_()
        self.oif_csca = If_channel_obuf_csca()
        self.oif_clks = If_channel_obuf_clks()

        self.submodules.dut = DDR5RCD01OutputBuffer_CSCA(
            self.iif_csca, self.iif_clks, self.oif_csca, self.oif_clks, self.ctrl_if)
        # print(verilog.convert(self.dut))


def run_test(dut):
    logging.debug('Write test')
    yield
    yield

if __name__ == "__main__":
    eT = EngTest()
    logging.info("<- Module called")
    tb = TestBed()
    logging.info("<- Module ready")
    run_simulation(tb, run_test(tb), vcd_name=eT.wave_file_name)
    logging.info("<- Simulation done")
    logging.info(str(eT))
