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
# RCD
from litedram.DDR5RCD01.RCD_definitions import *
from litedram.DDR5RCD01.RCD_interfaces import *
from litedram.DDR5RCD01.RCD_utils import *
# Submodules
# from litedram.DDR5RCD01.DDR5RCD01RegFile import DDR5RCD01RegFile
from litedram.DDR5RCD01.DDR5RCD01Registers import DDR5RCD01Registers
# from litedram.DDR5RCD01.DDR5RCD01Pages import DDR5RCD01Pages
from litedram.DDR5RCD01.DDR5RCD01CSLogic import DDR5RCD01CSLogic
from litedram.DDR5RCD01.DDR5RCD01Error import DDR5RCD01Error


@enum.unique
class HOST_IF_TM_ENCODING(enum.IntEnum):
    NORMAL_MODE = 0
    DCATM = 1
    DCSTM_0 = 2
    DCSTM_1 = 3


class DDR5RCD01ControlCenter(Module):
    """DDR5 RCD01 Control Center
    TODO Documentation

    -- 3.8 on hard reset
    POWERDOWN - meaning no power supplied, note, this is ambiguous*
    Device should start in the RESET state. DRST_n shall be asserted.
    Effects:
      - floating input receivers
      - non-sticky registers are restored to default (preferred 0)
      - QRST_n is asserted
      - other outputs are to flow, except QCS[x]_n which should be asserted
    This state is also called the low-power state.

    *Powerdown is widely used to describe a power-state, in which
    the bias circuitry is disabled, however, there is a stable power supply
    on the vdd pin.

    Next:
      - DRST_n is deasserted
      - DCS_n are deasserted
      - Host starts the dck clock
      - host writes to coarse and fine grain frequency registers
      - host writes to DCA input mode (DDR, SDR)
      - wait for PLL to re-lock
    Next, training:
      - DCS and DCA training
      - BCS and BCOM training (if applicable)

    Note, qrst_n remains asserted until a proper command register write.

    After initialization, a proper write sequence should occur to configure the application.
    -- 3.9 on soft reset (vdd remains on)
    TODO analyze

    TODO List of states:
    HARD_RESET
    SOFT_RESET
    INITIALIZATION
    NORMAL
    TRAINING (4 modes)
    POWER_SAVINGS (4 modes)

    Module
    ------
    d - Input : data
    q - Output: data
    ------
    """

    def __init__(self,
                 if_ibuf,
                 if_ctrl_ibuf,
                 if_ctrl_lbuf_row_A_rankA,
                 if_ctrl_lbuf_row_B_rankA,
                 if_ctrl_obuf_csca_row_A_rankA,
                 if_ctrl_obuf_csca_row_B_rankA,
                 if_ctrl_obuf_clks_row_A_rankA,
                 if_ctrl_obuf_clks_row_B_rankA,
                 if_ctrl_lbuf_row_A_rankB,
                 if_ctrl_lbuf_row_B_rankB,
                 if_ctrl_obuf_csca_row_A_rankB,
                 if_ctrl_obuf_csca_row_B_rankB,
                 if_ctrl_obuf_clks_row_A_rankB,
                 if_ctrl_obuf_clks_row_B_rankB,
                 if_register,
                 drst_rw04,
                 drst_pon,
                 if_ctrl_global,
                 if_config_global,
                 if_common,
                 if_ctrl_common,
                 if_config_common,
                 if_regs,
                 if_ctrl_rx_block,
                 if_ctrl_fwd_block_A,
                 if_ctrl_fwd_block_B,
                 if_ctrl_dcstm_agent,
                 if_ctrl_dcatm_agent,
                 if_ctrl_error_arbiter,
                 if_ctrl_cmd_logic,
                 is_channel_A=True,
                 ):
        """
            Registers hardware description
        """
        # TODO speed-up simulation, only 6 pages
        # cw_page_num = CW_PAGE_NUM
        cw_page_num = 6


        reg_we = Signal(1)
        reg_addr = Signal(CW_REG_BIT_SIZE)
        reg_d = Signal(CW_REG_BIT_SIZE)
        reg_q = Signal(CW_REG_BIT_SIZE)

        self.comb += reg_we.eq(if_register.we | if_regs.we)
        self.comb += reg_addr.eq(if_register.addr | if_regs.addr)
        self.comb += reg_d.eq(if_register.d | if_regs.d)
        self.comb += reg_q.eq(if_register.q | if_regs.q)

        xregisters = DDR5RCD01Registers(
            we=reg_we,
            addr=reg_addr,
            d=reg_d,
            q=reg_q,
            cw_page_num=cw_page_num
        )

        # xregisters = DDR5RCD01Registers(
        #     we=if_register.we,
        #     addr=if_register.addr,
        #     d=if_register.d,
        #     q=if_register.q,
        #     cw_page_num=cw_page_num
        # )
        self.submodules.xregisters = xregisters

        regs = self.xregisters.xreg_file.registers
        pages = self.xregisters.xpage_file.pages
        """
        CSR, RW, PAGE
        This section described the CSR of the device. Connects physical functions
        to its control words in Control Registers.

        """
        # Boot Image

        DEBUG_BOOT_ENABLE = False
        if DEBUG_BOOT_ENABLE:
            DEBUG_NUMBER = 0x39
            boot_image_rw00_rw5f = [DEBUG_NUMBER]*CW_DA_REGS_NUM
        else:
            CW_DEFAULT_RESET_STATE = 0x00
            boot_image_rw00_rw5f = [CW_DEFAULT_RESET_STATE]*CW_DA_REGS_NUM

        """ Custom Internal CSR
          Implementation dependent, not constrained by the JEDEC spec.

        """
        rw_custom_csr = Signal(8)  # Expand width as needed
        RW_CUSTOM_INBUF_EN = rw_custom_csr[0]

        if DEBUG_BOOT_ENABLE:
            # ------------------------0b76543210
            rw_custom_csr_boot_word = 0b00000001
        else:
            rw_custom_csr_boot_word = 0b00000000

        self.comb += if_ctrl_ibuf.en.eq(RW_CUSTOM_INBUF_EN)

        """ Table 98
            RW00
            Global Features Control Word
        """
        RW_GLOBAL_FEATURES = 0x00
        COMMAND_ADDRESS_RATE = regs[RW_GLOBAL_FEATURES][0]
        SDR_MODES = regs[RW_GLOBAL_FEATURES][1]
        CA_PASS_THROUGH_MODE_ENABLE = regs[RW_GLOBAL_FEATURES][2]
        CA_PASS_THROUGH_MODE_RANK_SELECTION = regs[RW_GLOBAL_FEATURES][3]
        BCOM_PASS_THROUGH_MODE_ENABLE = regs[RW_GLOBAL_FEATURES][4]
        OUTPUT_INVERSION_ENABLE = regs[RW_GLOBAL_FEATURES][5]
        POWER_DOWN_MODE_ENABLE = regs[RW_GLOBAL_FEATURES][6]
        TRANSPARENT_MODE_ENABLE = regs[RW_GLOBAL_FEATURES][7]
        # -----------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_GLOBAL_FEATURES] = 0b00100011

        self.comb += if_ctrl_cmd_logic.is_output_inversion_en.eq(
            OUTPUT_INVERSION_ENABLE)
        """ Table 99
            RW01
            Parity, CMD Blocking and Alert Global Control Word
            Note, for block_n signals the '0' means block
        """
        RW_SECONDARY_FEATURES = 0x01
        PARITY_CHECKING_ENABLE = regs[RW_SECONDARY_FEATURES][0]
        DRAM_FORWARD_CMDS_BLOCK_N = regs[RW_SECONDARY_FEATURES][1]
        # RESERVED = regs[RW_SECONDARY_FEATURES][2]
        DB_FORWARD_CMDS_BLOCK_N = regs[RW_SECONDARY_FEATURES][3]
        # RESERVED = regs[RW_SECONDARY_FEATURES][4]
        HOST_IF_TRAINING_FEEDBACK = regs[RW_SECONDARY_FEATURES][5]
        ALERT_ASSERTION_MODE = regs[RW_SECONDARY_FEATURES][6]
        ALERT_REENABLE = regs[RW_SECONDARY_FEATURES][7]
        # --------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_SECONDARY_FEATURES] = 0b10000000

        self.comb += if_ctrl_cmd_logic.is_parity_checking_en.eq(
            PARITY_CHECKING_ENABLE)

        """ Table 101
            RW02
            Host Interface Training Mode Global Control Word
        """
        RW_HOST_IF_TRAINING = 0x02
        HOST_IF_TM_CH_A = regs[RW_HOST_IF_TRAINING][0:2]
        HOST_IF_TM_CH_B = regs[RW_HOST_IF_TRAINING][2:4]
        DCATM_XOR_SAMPLING_EDGE = regs[RW_HOST_IF_TRAINING][4:6]
        VREF_CA_BROADCAST_EN = regs[RW_HOST_IF_TRAINING][6]
        # RESERVED = regs[RW_HOST_IF_TRAINING][7]
        # ------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_HOST_IF_TRAINING] = 0b00000000

        """ Table 103
            RW04
            Command Space Global Control Word
            After issuing a write to RW04, RCD has t_MRC time to execute the command
            Special case of write!
            regs[0x04]
        """
        RW_CMD_SPACE_GLOBAL_CONTROL = 0x04
        CMD_0_NOP = 0x00
        # Not supported: LRDIMM
        # CMD_1_CH_A_DB_RST = 0x01
        # CMD_2_CH_A_DB_RST_CLEAR = 0x02
        # CMD_3_CH_B_DB_RST = 0x03
        # CMD_4_CH_B_DB_RST_CLEAR = 0x04
        CMD_5_CH_A_DRAM_RST = 0x05
        CMD_6_CH_A_DRAM_RST_CLEAR = 0x06
        CMD_7_CH_B_DRAM_RST = 0x07
        CMD_8_CH_B_DRAM_RST_CLEAR = 0x08
        CMD_9_CH_A_PARITY_ERR_CLEAR = 0x09
        CMD_A_CH_B_PARITY_ERR_CLEAR = 0x0A
        # Not supported: DFE model
        # CMD_B_CH_A_DFE_ERR_COUNTER_RST = 0x0B
        # CMD_C_CH_B_DFE_ERR_COUNTER_RST = 0x0C
        CMD_D_ALERT_N_TOGGLE = 0x0D
        CMD_E_CH_A_QCS_HIGH = 0x0E
        CMD_F_CH_B_QCS_HIGH = 0x0F
        # --------------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_CMD_SPACE_GLOBAL_CONTROL] = 0b00000000

        """
            TODO add RW04 actor
            anytime RW04 changes, execute a command
            1.important
                dram resets (cmds 5-8)
            2.less important now
                parity err clear
            3.important
                alert toggle
            4.important
                keep qcs high (can be done by disabling cs outputs)
        """
        # Detect write to RW04
        execute_command = Signal()
        command = Signal(CW_REG_BIT_SIZE)

        # TODO placeholder signal
        b = Signal()

        self.comb += If(
            (if_register.we) &
            (if_register.addr == RW_CMD_SPACE_GLOBAL_CONTROL),
            execute_command.eq(1),
            command.eq(if_register.d),
        )

        self.sync += Case(
            command, {
                CMD_0_NOP: [],
                CMD_5_CH_A_DRAM_RST: [
                    drst_rw04.eq(1)
                ],
                CMD_6_CH_A_DRAM_RST_CLEAR: [
                    drst_rw04.eq(0)
                ],
                CMD_7_CH_B_DRAM_RST: [
                    # drst_rw04.eq(1)
                ],
                CMD_8_CH_B_DRAM_RST_CLEAR: [
                    # drst_rw04.eq(0)
                ],
                CMD_9_CH_A_PARITY_ERR_CLEAR: [
                    b.eq(1)
                ],
                CMD_A_CH_B_PARITY_ERR_CLEAR: [
                    b.eq(1)
                ],
                CMD_D_ALERT_N_TOGGLE: [
                    b.eq(1)
                ],
                CMD_E_CH_A_QCS_HIGH: [
                    b.eq(1)
                ],
                CMD_F_CH_B_QCS_HIGH: [
                    b.eq(1)
                ],
                "default": []
            }
        )

        """ Table 104
            RW05
            DIMM Operating Speed Global Control Word
        """
        RW_DIMM_SPEED_CONTROL = 0x05
        DIMM_OPERATING_SPEED = regs[RW_DIMM_SPEED_CONTROL][0:4]
        # RESERVED = regs[RW_DIMM_SPEED_CONTROL][4]
        REGISTER_VDD_VOLTAGE = regs[RW_DIMM_SPEED_CONTROL][5]
        FREQUENCY_CONTEXT = regs[RW_DIMM_SPEED_CONTROL][6]
        FREQUENCY_BAND = regs[RW_DIMM_SPEED_CONTROL][7]
        # --------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_DIMM_SPEED_CONTROL] = 0b10101111

        """ Table 105
            RW06
            Fine Granularity DIMM Operating Speed Global Control Word
        """
        RW_FINE_DIMM_SPEED_CONTROL = 0x06
        FINE_DIMM_OPERATING_SPEED = regs[RW_FINE_DIMM_SPEED_CONTROL][0:5]
        # RESERVED = regs[RW_FINE_DIMM_SPEED_CONTROL][5]
        # RESERVED = regs[RW_FINE_DIMM_SPEED_CONTROL][6]
        # RESERVED = regs[RW_FINE_DIMM_SPEED_CONTROL][7]
        # -------------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_FINE_DIMM_SPEED_CONTROL] = 0b00000000

        """ Table 107
            RW08
            Clock driver enable control word
            regs[0x08]
            """
        RW_CLOCK_OUTPUT_CONTROL = 0x08
        QACK_CLK_ENABLE_N = regs[RW_CLOCK_OUTPUT_CONTROL][0]
        QBCK_CLK_ENABLE_N = regs[RW_CLOCK_OUTPUT_CONTROL][1]
        QCCK_CLK_ENABLE_N = regs[RW_CLOCK_OUTPUT_CONTROL][2]
        QDCK_CLK_ENABLE_N = regs[RW_CLOCK_OUTPUT_CONTROL][3]
        # RESERVED = regs[RW_CLOCK_OUTPUT_CONTROL][4]
        BCK_CLK_ENABLE_N = regs[RW_CLOCK_OUTPUT_CONTROL][5]
        # RESERVED = regs[RW_CLOCK_OUTPUT_CONTROL][6]
        # RESERVED = regs[RW_CLOCK_OUTPUT_CONTROL][7]
        # ----------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_CLOCK_OUTPUT_CONTROL] = 0b00111010

        self.comb += if_ctrl_obuf_clks_row_A_rankA.oe_ck_t.eq(
            ~QACK_CLK_ENABLE_N)
        self.comb += if_ctrl_obuf_clks_row_A_rankA.oe_ck_c.eq(
            ~QACK_CLK_ENABLE_N)

        self.comb += if_ctrl_obuf_clks_row_B_rankA.oe_ck_t.eq(
            ~QBCK_CLK_ENABLE_N)
        self.comb += if_ctrl_obuf_clks_row_B_rankA.oe_ck_c.eq(
            ~QBCK_CLK_ENABLE_N)

        self.comb += if_ctrl_obuf_clks_row_A_rankB.oe_ck_t.eq(
            ~QCCK_CLK_ENABLE_N)
        self.comb += if_ctrl_obuf_clks_row_A_rankB.oe_ck_c.eq(
            ~QCCK_CLK_ENABLE_N)

        self.comb += if_ctrl_obuf_clks_row_B_rankB.oe_ck_t.eq(
            ~QDCK_CLK_ENABLE_N)
        self.comb += if_ctrl_obuf_clks_row_B_rankB.oe_ck_c.eq(
            ~QDCK_CLK_ENABLE_N)

        """ Table 108
            RW09
            Output address and Control Enable Control Word
            regs[0x09]
            """
        RW_OUTPUT_CONTROL = 0x09
        QACA_OUTPUT_ENABLE_N = regs[RW_OUTPUT_CONTROL][0]
        QBCA_OUTPUT_ENABLE_N = regs[RW_OUTPUT_CONTROL][1]
        DCS_N_AND_QCS_N_ENABLE_N = regs[RW_OUTPUT_CONTROL][2]
        BCS_BCOM_BRST_ENABLE_N = regs[RW_OUTPUT_CONTROL][3]
        QBACA13_OUTPUT_ENABLE_N = regs[RW_OUTPUT_CONTROL][4]
        QACS_N_ENABLE_N = regs[RW_OUTPUT_CONTROL][5]
        QBCS_N_ENABLE_N = regs[RW_OUTPUT_CONTROL][6]
        # RESERVED = regs[RW_OUTPUT_CONTROL][7]
        # ----------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_OUTPUT_CONTROL] = 0b10011000

        # Output enable
        self.comb += if_ctrl_obuf_csca_row_A_rankA.oe_qca.eq(
            ~QACA_OUTPUT_ENABLE_N)
        self.comb += if_ctrl_obuf_csca_row_B_rankA.oe_qca.eq(
            ~QACA_OUTPUT_ENABLE_N)
        self.comb += if_ctrl_obuf_csca_row_A_rankB.oe_qca.eq(
            ~QBCA_OUTPUT_ENABLE_N)
        self.comb += if_ctrl_obuf_csca_row_B_rankB.oe_qca.eq(
            ~QBCA_OUTPUT_ENABLE_N)

        """
            TODO priority encoder
            1. RW04_KEEP HIGH
            2. QCS_ENABLE
            3.
        """
        self.comb += if_ctrl_obuf_csca_row_A_rankA.oe_qcs_n.eq(
            ~QACS_N_ENABLE_N)
        self.comb += if_ctrl_obuf_csca_row_B_rankA.oe_qcs_n.eq(
            ~QACS_N_ENABLE_N)
        self.comb += if_ctrl_obuf_csca_row_A_rankB.oe_qcs_n.eq(
            ~QBCS_N_ENABLE_N)
        self.comb += if_ctrl_obuf_csca_row_B_rankB.oe_qcs_n.eq(
            ~QBCS_N_ENABLE_N)

        # DCS, DCA Output inversion
        self.comb += if_ctrl_obuf_csca_row_A_rankA.o_inv_en_qcs_n.eq(0)
        self.comb += if_ctrl_obuf_csca_row_B_rankA.o_inv_en_qcs_n.eq(0)
        self.comb += if_ctrl_obuf_csca_row_A_rankB.o_inv_en_qcs_n.eq(0)
        self.comb += if_ctrl_obuf_csca_row_B_rankB.o_inv_en_qcs_n.eq(0)

        self.comb += if_ctrl_obuf_csca_row_A_rankA.o_inv_en_qca.eq(0)
        self.comb += if_ctrl_obuf_csca_row_B_rankA.o_inv_en_qca.eq(0)
        self.comb += if_ctrl_obuf_csca_row_A_rankB.o_inv_en_qca.eq(
            OUTPUT_INVERSION_ENABLE)
        self.comb += if_ctrl_obuf_csca_row_B_rankB.o_inv_en_qca.eq(
            OUTPUT_INVERSION_ENABLE)

        # Clock output inversion

        self.comb += if_ctrl_obuf_clks_row_A_rankA.o_inv_en_ck_t.eq(0)
        self.comb += if_ctrl_obuf_clks_row_A_rankA.o_inv_en_ck_c.eq(0)
        self.comb += if_ctrl_obuf_clks_row_B_rankA.o_inv_en_ck_t.eq(0)
        self.comb += if_ctrl_obuf_clks_row_B_rankA.o_inv_en_ck_c.eq(0)
        self.comb += if_ctrl_obuf_clks_row_A_rankB.o_inv_en_ck_t.eq(
            OUTPUT_INVERSION_ENABLE)
        self.comb += if_ctrl_obuf_clks_row_A_rankB.o_inv_en_ck_c.eq(
            OUTPUT_INVERSION_ENABLE)
        self.comb += if_ctrl_obuf_clks_row_B_rankB.o_inv_en_ck_t.eq(
            OUTPUT_INVERSION_ENABLE)
        self.comb += if_ctrl_obuf_clks_row_B_rankB.o_inv_en_ck_c.eq(
            OUTPUT_INVERSION_ENABLE)

        """ Table 115
            RW11
            Command Latency Adder Configuration Control Word
            regs[0x11]
        """
        RW_LATENCY_ADDER = 0x11
        LATENCY_ADDER_OP_0 = regs[RW_LATENCY_ADDER][0]
        LATENCY_ADDER_OP_1 = regs[RW_LATENCY_ADDER][1]
        LATENCY_ADDER_OP_2 = regs[RW_LATENCY_ADDER][2]
        # RESERVED = regs[RW_LATENCY_ADDER][3]
        # RESERVED = regs[RW_LATENCY_ADDER][4]
        # RESERVED = regs[RW_LATENCY_ADDER][5]
        # RESERVED = regs[RW_LATENCY_ADDER][6]
        # RESERVED = regs[RW_LATENCY_ADDER][7]
        latency_cat = Cat(LATENCY_ADDER_OP_0,
                          LATENCY_ADDER_OP_1,
                          LATENCY_ADDER_OP_2)
        # ---------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_LATENCY_ADDER] = 0b00000001

        self.comb += if_ctrl_lbuf_row_A_rankA.sel_latency_add.eq(latency_cat)
        self.comb += if_ctrl_lbuf_row_B_rankA.sel_latency_add.eq(latency_cat)
        self.comb += if_ctrl_lbuf_row_A_rankB.sel_latency_add.eq(latency_cat)
        self.comb += if_ctrl_lbuf_row_B_rankB.sel_latency_add.eq(latency_cat)

        """
            Table 128
            RW[24:20]
            Error Log Register Encoding for DDR Mode
            These definitions could be reused for the SDR Mode or explicitly redefined.
            The only difference is that in DDR, there are UIs, in SDR cycles
        """
        RW_ERROR_LOG_CA_2UI = 0x20
        RW_ERROR_LOG_CA_1UI = 0x21
        RW_ERROR_LOG_CA_4UI = 0x22
        RW_ERROR_LOG_CA_3UI = 0x23
        # ------------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_ERROR_LOG_CA_1UI] = 0b00000000
        boot_image_rw00_rw5f[RW_ERROR_LOG_CA_2UI] = 0b00000000
        boot_image_rw00_rw5f[RW_ERROR_LOG_CA_3UI] = 0b00000000
        boot_image_rw00_rw5f[RW_ERROR_LOG_CA_4UI] = 0b00000000

        RW_ERROR_STATUS = 0x24
        # RESERVED = regs[RW_ERROR_STATUS][0]
        RW_ERROR_LOG_CS_2UI = regs[RW_ERROR_STATUS][2:1]
        RW_ERROR_LOG_CS_1UI = regs[RW_ERROR_STATUS][4:3]
        # RESERVED = regs[RW_ERROR_STATUS][5]
        CA_PARITY_ERROR_STATUS = regs[RW_ERROR_STATUS][6]
        MORE_THAN_1_ERROR = regs[RW_ERROR_STATUS][7]
        # --------------------------------------0b76543210
        boot_image_rw00_rw5f[RW_ERROR_STATUS] = 0b00000000

        """
            Main RCD FSM
            ------------
            POWERDOWN

            INITIALIZATION
                PON_DRST_EVENT
                    all inputs are disabled
                    qrst is asserted
                    qcs is asserted
                STABLE_POWER_RESET
                    host will keep dcs and drst low
                    host will start dck
                POST_PON_DRST_EVENT
                    host will deassert drst, wait some time
                    host will deassert dcs
                SIDEBAND_FREQUENCY_INIT
                    RW to set frequency registers and set input mode
                    (good time to also change termination if needed)
                HOST_IF_TRAINING
                    DCSTM HOST DCS TRAINING
                    DCATM HOST DCA TRAINING
                DRAM_IF_BLOCKED (waiting for command to unblock dram interface)
                QCS_BLOCKED (waiting for NOP command to RW04)

            NORMAL

            DRST_EVENT

        """

        """
            RESET_HARD state
            ----------------
            This state is achieved after a supply voltage ramp. At this time
            DRST_n must be kept low by the controller.
        """
        if not DEBUG_BOOT_ENABLE:
            xfsm = FSM(reset_state="PON_DRST_EVENT")
            self.submodules.xfsm = xfsm

            """
                All inputs are disabled
                qrst is asserted
                qcs is asserted
            """
            xfsm.act(
                "PON_DRST_EVENT",
                NextValue(drst_pon, 1),
                NextValue(drst_rw04, 1),
                NextValue(if_ctrl_rx_block.block, 1),
                NextValue(if_ctrl_obuf_csca_row_A_rankA.tie_low_cs, 1),
                NextValue(if_ctrl_obuf_csca_row_B_rankA.tie_low_cs, 1),
                NextValue(if_ctrl_obuf_csca_row_A_rankB.tie_low_cs, 1),
                NextValue(if_ctrl_obuf_csca_row_B_rankB.tie_low_cs, 1),
                NextValue(if_ctrl_obuf_csca_row_A_rankA.tie_low_ca, 1),
                NextValue(if_ctrl_obuf_csca_row_B_rankA.tie_low_ca, 1),
                NextValue(if_ctrl_obuf_csca_row_A_rankB.tie_low_ca, 1),
                NextValue(if_ctrl_obuf_csca_row_B_rankB.tie_low_ca, 1),

                NextValue(if_ctrl_obuf_clks_row_A_rankA.tie_low_ck_t, 1),
                NextValue(if_ctrl_obuf_clks_row_A_rankA.tie_low_ck_c, 1),
                NextValue(if_ctrl_obuf_clks_row_B_rankA.tie_low_ck_t, 1),
                NextValue(if_ctrl_obuf_clks_row_B_rankA.tie_low_ck_c, 1),
                NextValue(if_ctrl_obuf_clks_row_A_rankB.tie_low_ck_t, 1),
                NextValue(if_ctrl_obuf_clks_row_A_rankB.tie_low_ck_c, 1),
                NextValue(if_ctrl_obuf_clks_row_B_rankB.tie_low_ck_t, 1),
                NextValue(if_ctrl_obuf_clks_row_B_rankB.tie_low_ck_c, 1),

                NextValue(rw_custom_csr, 0x01),
                NextState("STABLE_POWER_RESET"),
            )

            """

            """
            xfsm.act(
                "STABLE_POWER_RESET",
                If(
                    if_ibuf.dcs_n == 0b00,
                    NextState("STABLE_POWER_RESET"),
                ).Else(
                    NextState("POST_PON_DRST_EVENT"),
                )
            )

            """
                host will deassert drst, wait some time
                host will deassert dcs
            """

            """
                Enable command receiving,
                block command forwarding
            """
            xfsm.act(
                "POST_PON_DRST_EVENT",
                NextValue(drst_pon, 0),
                NextValue(if_ctrl_rx_block.block, 0),
                NextValue(if_ctrl_fwd_block_A.block, 1),
                NextValue(if_ctrl_fwd_block_B.block, 1),
                NextState("INIT_IDLE")
            )

            """
                In this state:
                    - sideband update frequency settings
                Enter DCSTM:
                    - if rw02[3:0], go to dcstm
                Enter DCATM:
                    - if rw02[3:0], go to dcatm
                """
            if is_channel_A:
                xfsm.act(
                    "INIT_IDLE",
                    If(
                        (HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.DCSTM_0) |
                        (HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.DCSTM_1),
                        NextState("DCSTM"),
                    ).Elif(
                        HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.DCATM,
                        NextState("DCATM"),
                    ).Else(
                        NextState("INIT_IDLE"),
                    )
                )
            else:
                xfsm.act(
                    "INIT_IDLE",
                    If(
                        (HOST_IF_TM_CH_B == HOST_IF_TM_ENCODING.DCSTM_0) |
                        (HOST_IF_TM_CH_B == HOST_IF_TM_ENCODING.DCSTM_1),
                        NextState("DCSTM"),
                    ).Elif(
                        (HOST_IF_TM_CH_B == HOST_IF_TM_ENCODING.DCATM),
                        NextState("DCATM"),
                    ).Else(
                        NextState("INIT_IDLE"),
                    )
                )

            """
                if rw02[3:0], enter/exit
            """
            xfsm.act(
                "DCSTM",
                # TRAIN DCS
                if_ctrl_dcstm_agent.enable.eq(1),
                if_ctrl_error_arbiter.is_dcstm_en.eq(1),
                If(
                    (HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.DCSTM_0),
                    if_ctrl_dcstm_agent.select_dcs_n.eq(0)
                ),
                If(
                    (HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.DCSTM_1),
                    if_ctrl_dcstm_agent.select_dcs_n.eq(1)
                ),
                If(
                    (HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.NORMAL_MODE),
                    NextState("INIT_IDLE"),
                ).Elif(
                    (HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.DCATM),
                    NextState("DCATM"),
                ).Else(
                    NextState("DCSTM"),
                )
            )

            """
                if rw02[3:0], enter/exit
            """
            xfsm.act(
                "DCATM",
                if_ctrl_dcatm_agent.enable.eq(1),
                if_ctrl_error_arbiter.is_dcatm_en.eq(1),
                # TRAIN DCA
                If(
                    HOST_IF_TM_CH_A == HOST_IF_TM_ENCODING.NORMAL_MODE,
                    NextState("POST_TM_INIT_IDLE"),
                ).Else(
                    NextState("DCATM"),
                )
            )

            """
            unblock command forwarding
            """
            xfsm.act(
                "POST_TM_INIT_IDLE",
                If(
                    execute_command & (command == CMD_0_NOP),
                    NextValue(if_ctrl_fwd_block_A.block, 0),
                    NextValue(if_ctrl_fwd_block_B.block, 0),
                    NextValue(if_ctrl_rx_block.block, 0),
                    NextValue(if_ctrl_obuf_csca_row_A_rankA.tie_low_cs, 0),
                    NextValue(if_ctrl_obuf_csca_row_B_rankA.tie_low_cs, 0),
                    NextValue(if_ctrl_obuf_csca_row_A_rankB.tie_low_cs, 0),
                    NextValue(if_ctrl_obuf_csca_row_B_rankB.tie_low_cs, 0),
                    NextValue(if_ctrl_obuf_csca_row_A_rankA.tie_low_ca, 0),
                    NextValue(if_ctrl_obuf_csca_row_B_rankA.tie_low_ca, 0),
                    NextValue(if_ctrl_obuf_csca_row_A_rankB.tie_low_ca, 0),
                    NextValue(if_ctrl_obuf_csca_row_B_rankB.tie_low_ca, 0),

                    NextValue(if_ctrl_obuf_clks_row_A_rankA.tie_low_ck_t, 0),
                    NextValue(if_ctrl_obuf_clks_row_A_rankA.tie_low_ck_c, 0),
                    NextValue(if_ctrl_obuf_clks_row_B_rankA.tie_low_ck_t, 0),
                    NextValue(if_ctrl_obuf_clks_row_B_rankA.tie_low_ck_c, 0),
                    NextValue(if_ctrl_obuf_clks_row_A_rankB.tie_low_ck_t, 0),
                    NextValue(if_ctrl_obuf_clks_row_A_rankB.tie_low_ck_c, 0),
                    NextValue(if_ctrl_obuf_clks_row_B_rankB.tie_low_ck_t, 0),
                    NextValue(if_ctrl_obuf_clks_row_B_rankB.tie_low_ck_c, 0),
                    NextState("NORMAL"),
                ).Else(
                    NextState("POST_TM_INIT_IDLE")
                )
            )

            xfsm.act(
                "NORMAL",
                NextValue(if_ctrl_rx_block.block, 0),
                NextValue(if_ctrl_fwd_block_A.block, 0),
                NextValue(if_ctrl_fwd_block_B.block, 0),
                NextState("NORMAL"),
            )

        """
            DEBUG States
        """
        if DEBUG_BOOT_ENABLE:
            xfsm = FSM(reset_state="RESET_HARD")
            self.submodules.xfsm = xfsm
            xfsm.act(
                "RESET_HARD",
                drst_pon.eq(1),
                NextState("INIT_HARD"),
            )

            rw_boot_image_reader_start = Signal()
            rw_boot_image_reader_finish = Signal()

            xfsm.act(
                "INIT_HARD",
                NextValue(rw_custom_csr, rw_custom_csr_boot_word),
                rw_boot_image_reader_start.eq(1),
                drst_pon.eq(1),
                If(
                    rw_boot_image_reader_finish,
                    NextState("NORMAL")
                ),
            )
            xfsm.act(
                "NORMAL",
            )

        """
            DEBUG Boot image reader
        """
        if DEBUG_BOOT_ENABLE:
            rw_counter = Signal(int(CW_DA_REGS_NUM).bit_length())
            boot_word = Signal(int(CW_DA_REGS_NUM).bit_length())

            for i in range(CW_DA_REGS_NUM):
                self.comb += If(
                    rw_counter == i,
                    boot_word.eq(boot_image_rw00_rw5f[i])
                )

            self.sync += If(
                rw_counter == CW_DA_REGS_NUM,
                rw_counter.eq(rw_counter),
                rw_boot_image_reader_finish.eq(1)
            ).Else(
                If(
                    rw_boot_image_reader_start,
                    rw_counter.eq(rw_counter+1)
                )
            )

            self.comb += If(rw_boot_image_reader_start &
                            (rw_counter < CW_DA_REGS_NUM) &
                            (~rw_boot_image_reader_finish),
                            if_register.we.eq(1),
                            if_register.d.eq(boot_word),
                            if_register.addr.eq(rw_counter),
                            )


if __name__ == "__main__":
    raise NotSupportedException
