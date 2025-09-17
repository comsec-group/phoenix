#include <liblitedram/ddr5_helpers.h>

#if defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_DDR5)

#include <stdio.h>

#include <liblitedram/accessors.h>

#include <liblitedram/sdram_rcd.h>

//#define DEBUG_DDR5

static int N2_mode = 1;
extern int enumerated;
extern int single_cycle_MPC;

void prep_payload(int channel, int cs, int command, int wrdata_en,
                  uint64_t wrdata_mask, int rddata_en) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_command_storage_write(
            command << CSR_SDRAM_DFII_B_CMDINJECTOR_COMMAND_STORAGE_CA_OFFSET |
            cs << CSR_SDRAM_DFII_B_CMDINJECTOR_COMMAND_STORAGE_CS_OFFSET |
            wrdata_en << CSR_SDRAM_DFII_B_CMDINJECTOR_COMMAND_STORAGE_WRDATA_EN_OFFSET |
            rddata_en << CSR_SDRAM_DFII_B_CMDINJECTOR_COMMAND_STORAGE_RDDATA_EN_OFFSET
        );
        sdram_dfii_b_cmdinjector_command_storage_wr_mask_write(wrdata_mask);
    } else {
        sdram_dfii_a_cmdinjector_command_storage_write(
            command << CSR_SDRAM_DFII_A_CMDINJECTOR_COMMAND_STORAGE_CA_OFFSET |
            cs << CSR_SDRAM_DFII_A_CMDINJECTOR_COMMAND_STORAGE_CS_OFFSET |
            wrdata_en << CSR_SDRAM_DFII_A_CMDINJECTOR_COMMAND_STORAGE_WRDATA_EN_OFFSET |
            rddata_en << CSR_SDRAM_DFII_A_CMDINJECTOR_COMMAND_STORAGE_RDDATA_EN_OFFSET
        );
        sdram_dfii_a_cmdinjector_command_storage_wr_mask_write(wrdata_mask);
    }
#else
    sdram_dfii_cmdinjector_command_storage_write(
        command | cs << CSR_SDRAM_DFII_CMDINJECTOR_COMMAND_STORAGE_CS_OFFSET |
        wrdata_en << CSR_SDRAM_DFII_CMDINJECTOR_COMMAND_STORAGE_WRDATA_EN_OFFSET |
        rddata_en << CSR_SDRAM_DFII_CMDINJECTOR_COMMAND_STORAGE_RDDATA_EN_OFFSET
    );
    sdram_dfii_cmdinjector_command_storage_wr_mask_write(wrdata_mask);
#endif
}

void upload_payload(int channel, int phases) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_phase_addr_write(phases);
    } else {
        sdram_dfii_a_cmdinjector_phase_addr_write(phases);
    }
#else
    sdram_dfii_cmdinjector_phase_addr_write(phases);
#endif
}

void store_payload(int channel, int single) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        if (single == 0)
            sdram_dfii_b_cmdinjector_store_continuous_cmd_write(1);
        else
            sdram_dfii_b_cmdinjector_store_singleshot_cmd_write(1);
    } else {
        if (single == 0)
            sdram_dfii_a_cmdinjector_store_continuous_cmd_write(1);
        else
            sdram_dfii_a_cmdinjector_store_singleshot_cmd_write(1);
    }
#else
    if (single == 0)
        sdram_dfii_cmdinjector_store_continuous_cmd_write(1);
    else
        sdram_dfii_cmdinjector_store_singleshot_cmd_write(1);
#endif
}

void cmd_injector(int channel, int phases, int cs, int command,
                  int wrdata_en, uint64_t wrdata_mask, int rddata_en, int single) {
    prep_payload(channel, cs, command, wrdata_en, wrdata_mask, rddata_en);
    upload_payload(channel, phases);
    store_payload(channel, single);
}

void store_continuous(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_single_shot_write(0);
        sdram_dfii_b_cmdinjector_issue_command_write(1);
    } else {
        sdram_dfii_a_cmdinjector_single_shot_write(0);
        sdram_dfii_a_cmdinjector_issue_command_write(1);
    }
#else
    sdram_dfii_cmdinjector_single_shot_write(0);
    sdram_dfii_cmdinjector_issue_command_write(1);
#endif
}

void issue_single(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_single_shot_write(1);
        sdram_dfii_b_cmdinjector_issue_command_write(1);
        sdram_dfii_b_cmdinjector_single_shot_write(0);
    } else {
        sdram_dfii_a_cmdinjector_single_shot_write(1);
        sdram_dfii_a_cmdinjector_issue_command_write(1);
        sdram_dfii_a_cmdinjector_single_shot_write(0);
    }
#else
    sdram_dfii_cmdinjector_single_shot_write(1);
    sdram_dfii_cmdinjector_issue_command_write(1);
    sdram_dfii_cmdinjector_single_shot_write(0);
#endif
}

void setup_rddata_cnt(int channel, int value) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_rddata_capture_cnt_write(value);
    } else {
        sdram_dfii_a_cmdinjector_rddata_capture_cnt_write(value);
    }
#else
    sdram_dfii_cmdinjector_rddata_capture_cnt_write(value);
#endif
}

#ifndef SDRAM_PHY_SUBCHANNELS
#define DFII_CMDINJECTOR_DATA_BYTES (SDRAM_PHY_DFI_DATABITS/8)
#define SUBCHANNEL_WIDTH (SDRAM_PHY_DFI_DATABITS/2)
#else
#define DFII_CMDINJECTOR_DATA_BYTES (SDRAM_PHY_DFI_DATABITS/16)
#define SUBCHANNEL_WIDTH (SDRAM_PHY_DFI_DATABITS/4)
#endif

uint16_t get_data_module_phase(int channel, int module, int width, int phase) {
    uint16_t ret_value;
    int pebo;   // module's positive_edge_byte_offset
    int nebo;   // module's negative_edge_byte_offset, could be undefined if SDR DRAM is used
    int ibo;    // module's in byte offset (x4 ICs)
    uint8_t data[DFII_CMDINJECTOR_DATA_BYTES];
    uint16_t die_mask = (1<<width)-1;
    ret_value = 0;
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        sdram_dfii_b_cmdinjector_rddata_select_write(phase);
        csr_rd_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_RDDATA_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    } else {
        sdram_dfii_a_cmdinjector_rddata_select_write(phase);
        csr_rd_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_RDDATA_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    }
#else
    sdram_dfii_cmdinjector_rddata_select_write(phase);
    csr_rd_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_RDDATA_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
#endif
    // CSR are read as BIG Endian
    nebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4);
    pebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4) + (width/8);

    ibo = 0; // Non zero only if x4 ICs are used
    ret_value |= (data[pebo] >> ibo) & die_mask;
    ibo = (0x4*(width/4)) % 8;
    ret_value |= ((data[nebo] >> ibo) & die_mask) << width;
    return ret_value;
}

uint16_t get_wdata_module_phase(int channel, int module, int width, int phase) {
    uint16_t ret_value;
    int pebo;   // module's positive_edge_byte_offset
    int nebo;   // module's negative_edge_byte_offset, could be undefined if SDR DRAM is used
    int ibo;    // module's in byte offset (x4 ICs)
    uint8_t data[DFII_CMDINJECTOR_DATA_BYTES];
    uint16_t die_mask = (1<<width)-1;
    ret_value = 0;
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        sdram_dfii_b_cmdinjector_wrdata_select_write(phase);
        csr_rd_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_WRDATA_S_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    } else {
        sdram_dfii_a_cmdinjector_wrdata_select_write(phase);
        csr_rd_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_WRDATA_S_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    }
#else
    sdram_dfii_cmdinjector_wrdata_select_write(phase);
    csr_rd_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_WRDATA_S_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
#endif
    // CSR are read as BIG Endian
    nebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4);
    pebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4) + (width/8);

    ibo = 0; // Non zero only if x4 ICs are used
    ret_value |= (data[pebo] >> ibo) & die_mask;
    ibo = (0x4*(width/4)) % 8;
    ret_value |= ((data[nebo] >> ibo) & die_mask) << width;
    return ret_value;
}

void set_data_module_phase(int channel, int module, int width, int phase, uint16_t wrdata) {
    int pebo;   // module's positive_edge_byte_offset
    int nebo;   // module's negative_edge_byte_offset, could be undefined if SDR DRAM is used
    int ibo;    // module's in byte offset (x4 ICs)
    uint8_t data[DFII_CMDINJECTOR_DATA_BYTES];
    uint8_t die_mask = ( 1 << width) - 1;
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        sdram_dfii_b_cmdinjector_wrdata_select_write(phase);
        csr_rd_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_WRDATA_S_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    } else {
        sdram_dfii_a_cmdinjector_wrdata_select_write(phase);
        csr_rd_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_WRDATA_S_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    }
#else
    sdram_dfii_cmdinjector_wrdata_select_write(phase);
    csr_rd_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_WRDATA_S_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
#endif

    // CSR are read as BIG Endian
    nebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4);
    pebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4) + (width/8);
    ibo = 0; // Non zero only if x4 ICs are used
    data[pebo] = (data[pebo]&(~die_mask)) | (wrdata & die_mask);
    ibo = (0x4*(width/4)) % 8;
    data[nebo] = (data[nebo]&(~(die_mask << ibo))) | ((wrdata >> 8*(width/8)) & (die_mask << ibo));

#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        sdram_dfii_b_cmdinjector_wrdata_select_write(phase);
        csr_wr_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_WRDATA_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
        sdram_dfii_b_cmdinjector_wrdata_store_write(1);
    } else {
        sdram_dfii_a_cmdinjector_wrdata_select_write(phase);
        csr_wr_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_WRDATA_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
        sdram_dfii_a_cmdinjector_wrdata_store_write(1);
    }
#else
    sdram_dfii_cmdinjector_wrdata_select_write(phase);
    csr_wr_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_WRDATA_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    sdram_dfii_cmdinjector_wrdata_store_write(1);
#endif
    return;
}

static void reset_CA_phy_regs(int channels, int ranks, int addresses) {
    for (int channel = 0; channel < channels; ++channel) {
        ck_rst(channel, 0, 0);
        for (int rank = 0; rank < ranks; ++rank) {
            cs_rst(channel, rank, 0);
            par_rst(channel, rank, 0);
            for (int address = 0; address < addresses; ++address) {
                ca_rst(channel, rank, address);
            }
        }
    }
}

static void reset_RD_phy_regs(int channels, int modules, int width) {
    for (int channel = 0; channel < channels; ++channel) {
        for (int module = 0; module < modules; ++module) {
            rd_rst(channel, module, width);
            idly_rst(channel, module, width);
        }
    }
}

static void reset_WR_phy_regs(int channels, int modules, int width) {
    for (int channel = 0; channel < channels; ++channel) {
        for (int module = 0; module < modules; ++module) {
            wr_dqs_rst(channel, module, width);
            odly_dqs_rst(channel, module, width);
            wr_dq_rst(channel, module, width);
            odly_dq_rst(channel, module, width);
            odly_dm_rst(channel, module, width);
        }
    }
}

void reset_all_phy_regs(int channels, int ranks, int addresses, int modules, int width) {
    reset_CA_phy_regs(channels, ranks, addresses);
    reset_RD_phy_regs(channels, modules, width);
    reset_WR_phy_regs(channels, modules, width);
}

void enable_phy(void) {
    ddrphy_CSRModule_enable_fifos_write(0);
    busy_wait_us(50);
    clear_phy_fifos(0);
    clear_phy_fifos(1);
    busy_wait_us(50);
    ddrphy_CSRModule_rst_write(1);
    busy_wait_us(50);
    ddrphy_CSRModule_rst_write(0);
    busy_wait_us(50);
    ddrphy_CSRModule_enable_fifos_write(1);
    busy_wait_us(50);
}

void setup_capture(int channel, int setup) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_sample_write(0);
        sdram_dfii_b_cmdinjector_setup_write(setup);
        sdram_dfii_b_cmdinjector_reset_write(1);
    } else {
        sdram_dfii_a_cmdinjector_sample_write(0);
        sdram_dfii_a_cmdinjector_setup_write(setup);
        sdram_dfii_a_cmdinjector_reset_write(1);
    }
#else
    sdram_dfii_cmdinjector_sample_write(0);
    sdram_dfii_cmdinjector_setup_write(setup);
    sdram_dfii_cmdinjector_reset_write(1);
#endif
}

void start_capture(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_sample_write(1);
    } else {
        sdram_dfii_a_cmdinjector_sample_write(1);
    }
#else
    sdram_dfii_cmdinjector_sample_write(1);
#endif
}

void stop_capture(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        sdram_dfii_b_cmdinjector_sample_write(0);
    } else {
        sdram_dfii_a_cmdinjector_sample_write(0);
    }
#else
    sdram_dfii_cmdinjector_sample_write(0);
#endif
}

// operation: 0->OR, 1-> AND
uint32_t capture_and_reduce_result(int channel, int operation) {
    uint8_t data[DFII_CMDINJECTOR_DATA_BYTES];
    int i;
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        csr_rd_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    } else {
        csr_rd_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    }
#else
    csr_rd_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
#endif

    for (i = 1; i < DFII_CMDINJECTOR_DATA_BYTES; ++i) {
        data[0] = operation ? (data[0] & data[i]) : (data[0] | data[i]);
    }
    if (operation) {
        data[0] &= data[0]>>4;
        data[0] &= data[0]>>2;
        data[0] &= data[0]>>1;
    } else {
        data[0] |= data[0]>>4;
        data[0] |= data[0]>>2;
        data[0] |= data[0]>>1;
    }
    return data[0]&1;
}

uint32_t capture_and_reduce_module(int channel, int module, int width, int operation) {
    uint16_t ret_value;
    int pebo;   // module's positive_edge_byte_offset
    int nebo;   // module's negative_edge_byte_offset, could be undefined if SDR DRAM is used
    int ibo;    // module's in byte offset (x4 ICs)
    uint8_t data[DFII_CMDINJECTOR_DATA_BYTES];
    uint16_t die_mask = (1<<width)-1;
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        csr_rd_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    } else {
        csr_rd_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
    }
#else
    csr_rd_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
#endif
    ret_value = 0;
    // CSR are read as BIG Endian
    nebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4);
    pebo = ((DFII_CMDINJECTOR_DATA_BYTES / (width/4)) - 1 - module) * (width/4) + (width/8);

    ibo = 0; // Non zero only if x4 ICs are used
    ret_value |= (data[pebo] >> ibo) & die_mask;
    ibo = (0x4*(width/4)) % 8;
    ret_value |= ((data[nebo] >> ibo) & die_mask) << width;
    if(operation) {
        ret_value &= ret_value >> (8 * (width/8));
        ret_value &= ret_value >> 4;
        ret_value &= ret_value >> 2;
        ret_value &= ret_value >> 1;
    } else {
        ret_value |= ret_value >> (8 * (width/8));
        ret_value |= ret_value >> 4;
        ret_value |= ret_value >> 2;
        ret_value |= ret_value >> 1;
    }
    return ret_value&1;
}

int or_sample(int channel) {
    setup_capture(channel, 0);
    busy_wait_us(1);
    start_capture(channel);
    busy_wait_us(5);
    stop_capture(channel);
    return !!capture_and_reduce_result(channel, 0);
}

int and_sample(int channel) {
    setup_capture(channel, 3);
    busy_wait_us(1);
    start_capture(channel);
    busy_wait_us(5);
    stop_capture(channel);
    return !!capture_and_reduce_result(channel, 1);
}

int or_sample_module(int channel, int module, int width) {
    setup_capture(channel, 0);
    busy_wait_us(1);
    start_capture(channel);
    busy_wait_us(5);
    stop_capture(channel);
    return !capture_and_reduce_module(channel, module, width, 0);
}

int and_sample_module(int channel, int module, int width) {
    setup_capture(channel, 3);
    busy_wait_us(1);
    start_capture(channel);
    busy_wait_us(5);
    stop_capture(channel);
    return !!capture_and_reduce_module(channel, module, width, 1);
}

void read_registers(int channel, int rank, int module, int width) {
    int i;
    for (i = 0; i < 256; ++i) {
        send_mrr(channel, rank, i);
        printf("\tMR:%3d %02"PRIX8"\n", i, recover_mrr_value(channel, module, width));
    }
}

/**
 * ca_check_if_has_line13
 *
 * Detect if CA13 is present.
 * Requires to already be in the CATM.
 */
int check_ca_13th_line(int32_t channel, int32_t rank) {
    cmd_injector(channel, 0xf, 0, 1<<13, 0, 0, 1, 0);
    cmd_injector(channel, 0x1, 1<<rank, 1<<13, 0, 0, 1, 0);
    store_continuous(channel);

    return and_sample(channel);
}

void disable_dfi_2n_mode(void) {
    int value = sdram_dfii_control_read();
    value &= ~DFII_CONTROL_2N_MODE;
    sdram_dfii_control_write(value);
    printf("Switching DFI to 1N mode\n");
    N2_mode = 0;
}

void enable_dfi_2n_mode(void) {
    int value = sdram_dfii_control_read();
    value |= DFII_CONTROL_2N_MODE;
    sdram_dfii_control_write(value);
    printf("Switching DFI to 2N mode\n");
    N2_mode = 1;
}

int in_2n_mode(void) {
    return N2_mode;
}

void disable_dram_2n_mode(int channel, int rank) {
    send_mpc(channel, rank, 0b1001, 0);
    printf("Switching DRAM on channel:%c rank:%d to 1N mode\n", 'A'+channel, rank);
}

static void phy_select(int channel, int select, int width) {
    int mask = 1;
    if (width == 8) {
        mask = 3;
        select *= 2;
    }
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_dly_sel_write(mask<<select);
    } else {
        ddrphy_CSRModule_A_dly_sel_write(mask<<select);
    }
#else
    ddrphy_CSRModule_dly_sel_write(mask<<select);
#endif
    busy_wait_us(1);
}

static void phy_deselect(int channel, int select, int width) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_dly_sel_write(0);
    } else {
        ddrphy_CSRModule_A_dly_sel_write(0);
    }
#else
    ddrphy_CSRModule_dly_sel_write(0);
#endif
    busy_wait_us(1);
}

static void phy_dq_select(int channel, int select, int width) {
#ifdef SDRAM_DELAY_PER_DQ
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_dq_dly_sel_write(1<<select);
    } else {
        ddrphy_CSRModule_A_dq_dly_sel_write(1<<select);
    }
#else
    ddrphy_CSRModule_dq_dly_sel_write(1<<select);
#endif
    busy_wait_us(1);
#endif // SDRAM_DELAY_PER_DQ
}

static void phy_dq_deselect(int channel, int select, int width) {
#ifdef SDRAM_DELAY_PER_DQ
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_dq_dly_sel_write(0);
    } else {
        ddrphy_CSRModule_A_dq_dly_sel_write(0);
    }
#else
    ddrphy_CSRModule_dq_dly_sel_write(0);
#endif
    busy_wait_us(1);
#endif // SDRAM_DELAY_PER_DQ
}

static void idly_rst_internal(int channel) {
#ifdef SDRAM_INPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_rdly_dqs_rst_write(1);
    } else {
        ddrphy_CSRModule_A_rdly_dqs_rst_write(1);
    }
#else
    ddrphy_CSRModule_rdly_dqs_rst_write(1);
#endif
#endif // SDRAM_INPUT_DELAY_CAPABLE
}

static void idly_inc_internal(int channel) {
#ifdef SDRAM_INPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_rdly_dqs_inc_write(1);
    } else {
        ddrphy_CSRModule_A_rdly_dqs_inc_write(1);
    }
#else
    ddrphy_CSRModule_rdly_dqs_inc_write(1);
#endif
#endif // SDRAM_INPUT_DELAY_CAPABLE
}

static void idly_dq_rst_internal(int channel) {
#ifdef SDRAM_INPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_rdly_dq_rst_write(1);
    } else {
        ddrphy_CSRModule_A_rdly_dq_rst_write(1);
    }
#else
    ddrphy_CSRModule_rdly_dq_rst_write(1);
#endif
#endif // SDRAM_INPUT_DELAY_CAPABLE
}

static void idly_dq_inc_internal(int channel) {
#ifdef SDRAM_INPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_rdly_dq_inc_write(1);
    } else {
        ddrphy_CSRModule_A_rdly_dq_inc_write(1);
    }
#else
    ddrphy_CSRModule_rdly_dq_inc_write(1);
#endif
#endif // SDRAM_INPUT_DELAY_CAPABLE
}

static void rd_rst_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_ck_rdly_rst_write(1);
    } else {
        ddrphy_CSRModule_A_ck_rdly_rst_write(1);
    }
#else
    ddrphy_CSRModule_ck_rdly_rst_write(1);
#endif
}

static void rd_inc_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_ck_rdly_inc_write(1);
    } else {
        ddrphy_CSRModule_A_ck_rdly_inc_write(1);
    }
#else
    ddrphy_CSRModule_ck_rdly_inc_write(1);
#endif
}

static void odly_dqs_rst_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wdly_dqs_rst_write(1);
    } else {
        ddrphy_CSRModule_A_wdly_dqs_rst_write(1);
    }
#else
    ddrphy_CSRModule_wdly_dqs_rst_write(1);
#endif
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static void odly_dqs_inc_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wdly_dqs_inc_write(1);
    } else {
        ddrphy_CSRModule_A_wdly_dqs_inc_write(1);
    }
#else
    ddrphy_CSRModule_wdly_dqs_inc_write(1);
#endif
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static void odly_dm_rst_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wdly_dm_rst_write(1);
    } else {
        ddrphy_CSRModule_A_wdly_dm_rst_write(1);
    }
#else
    ddrphy_CSRModule_wdly_dm_rst_write(1);
#endif
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static void odly_dm_inc_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wdly_dm_inc_write(1);
    } else {
        ddrphy_CSRModule_A_wdly_dm_inc_write(1);
    }
#else
    ddrphy_CSRModule_wdly_dm_inc_write(1);
#endif
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static void odly_dq_rst_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wdly_dq_rst_write(1);
    } else {
        ddrphy_CSRModule_A_wdly_dq_rst_write(1);
    }
#else
    ddrphy_CSRModule_wdly_dq_rst_write(1);
#endif
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static void odly_dq_inc_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wdly_dq_inc_write(1);
    } else {
        ddrphy_CSRModule_A_wdly_dq_inc_write(1);
    }
#else
    ddrphy_CSRModule_wdly_dq_inc_write(1);
#endif
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static uint16_t get_cs_dly_internal(int channel) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_csdly_read();
    } else {
        return ddrphy_CSRModule_A_csdly_read();
    }
#else
    return ddrphy_CSRModule_csdly_read();
#endif
#else
    return 0;
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

static uint16_t get_ca_dly_internal(int channel) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_cadly_read();
    } else {
        return ddrphy_CSRModule_A_cadly_read();
    }
#else
    return ddrphy_CSRModule_cadly_read();
#endif
#else
    return 0;
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

static uint16_t get_rd_dq_dly_internal(int channel) {
#ifdef SDRAM_INPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_rdly_dq_read();
    } else {
        return ddrphy_CSRModule_A_rdly_dq_read();
    }
#else
    return ddrphy_CSRModule_rdly_dq_read();
#endif
#else
    return 0;
#endif // SDRAM_INPUT_DELAY_CAPABLE
}

static uint16_t get_rd_dqs_dly_internal(int channel) {
#ifdef SDRAM_INPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_rdly_dqs_read();
    } else {
        return ddrphy_CSRModule_A_rdly_dqs_read();
    }
#else
    return ddrphy_CSRModule_rdly_dqs_read();
#endif
#else
    return 0;
#endif // SDRAM_INPUT_DELAY_CAPABLE
}

static uint16_t get_rd_dq_ck_dly_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_ck_rddly_read();
    } else {
        return ddrphy_CSRModule_A_ck_rddly_read();
    }
#else
    return ddrphy_CSRModule_ck_rddly_read();
#endif
}

static uint16_t get_rd_preamble_ck_dly_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_ck_rddly_preamble_read();
    } else {
        return ddrphy_CSRModule_A_ck_rddly_preamble_read();
    }
#else
    return ddrphy_CSRModule_ck_rddly_preamble_read();
#endif
}

static uint16_t get_wr_dm_dly_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_wdly_dm_read();
    } else {
        return ddrphy_CSRModule_A_wdly_dm_read();
    }
#else
    return ddrphy_CSRModule_wdly_dm_read();
#endif
#else
    return 0;
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static uint16_t get_wr_dq_dly_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_wdly_dq_read();
    } else {
        return ddrphy_CSRModule_A_wdly_dq_read();
    }
#else
    return ddrphy_CSRModule_wdly_dq_read();
#endif
#else
    return 0;
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static uint16_t get_wr_dqs_dly_internal(int channel) {
#ifdef SDRAM_OUTPUT_DELAY_CAPABLE
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_wdly_dqs_read();
    } else {
        return ddrphy_CSRModule_A_wdly_dqs_read();
    }
#else
    return ddrphy_CSRModule_wdly_dqs_read();
#endif
#else
    return 0;
#endif // SDRAM_OUTPUT_DELAY_CAPABLE
}

static void wr_rst_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_ck_wdly_rst_write(1);
    } else {
        ddrphy_CSRModule_A_ck_wdly_rst_write(1);
    }
#else
    ddrphy_CSRModule_ck_wdly_rst_write(1);
#endif
}

static void wr_inc_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_ck_wdly_inc_write(1);
    } else {
        ddrphy_CSRModule_A_ck_wdly_inc_write(1);
    }
#else
    ddrphy_CSRModule_ck_wdly_inc_write(1);
#endif
}

static void wr_dq_rst_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_ck_wddly_rst_write(1);
    } else {
        ddrphy_CSRModule_A_ck_wddly_rst_write(1);
    }
#else
    ddrphy_CSRModule_ck_wddly_rst_write(1);
#endif
}

static void wr_dq_inc_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_ck_wddly_inc_write(1);
    } else {
        ddrphy_CSRModule_A_ck_wddly_inc_write(1);
    }
#else
    ddrphy_CSRModule_ck_wddly_inc_write(1);
#endif
}

static int read_captured_preamble_internal(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_preamble_read();
    } else {
        return ddrphy_CSRModule_A_preamble_read();
    }
#else
    return ddrphy_CSRModule_preamble_read();
#endif
}

#ifdef SDRAM_PHY_SUBCHANNELS
#define DQ_REMAP_DATA_BYTES (SDRAM_PHY_DFI_DATABITS/4)
#else
#define DQ_REMAP_DATA_BYTES (SDRAM_PHY_DFI_DATABITS/2)
#endif

static int get_dq_remapping(int channel, int line) {
    uint8_t data[DQ_REMAP_DATA_BYTES];
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        csr_rd_buf_uint8(CSR_MAIN_B_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
    } else {
        csr_rd_buf_uint8(CSR_MAIN_A_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
    }
#else
    csr_rd_buf_uint8(CSR_MAIN_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
#endif
    return data[line];
}

static void set_dq_remapping(int channel, int line, int mapping) {
    uint8_t data[DQ_REMAP_DATA_BYTES];
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        csr_rd_buf_uint8(CSR_MAIN_B_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
    } else {
        csr_rd_buf_uint8(CSR_MAIN_A_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
    }
#else
    csr_rd_buf_uint8(CSR_MAIN_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
#endif
    data[line] = mapping;
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel) {
        csr_wr_buf_uint8(CSR_MAIN_B_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
    } else {
        csr_wr_buf_uint8(CSR_MAIN_A_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
    }
#else
    csr_wr_buf_uint8(CSR_MAIN_DQ_REMAPPING_ADDR, data, DQ_REMAP_DATA_BYTES);
#endif
}

void get_dimm_dq_remapping(int channel, int modules, int width) {
    int it, module, line;
    uint16_t temp;
    for (it = 0; it < width; ++it) {
        send_mrw(channel, 0, MODULE_BROADCAST, 26, 0xFF);
        send_mrw(channel, 0, MODULE_BROADCAST, 27, 0xFF);
        send_mrw(channel, 0, MODULE_BROADCAST, 28, 1 << it);
        send_mrw(channel, 0, MODULE_BROADCAST, 29, (it&8) << (it&7));
        send_mrw(channel, 0, MODULE_BROADCAST, 25, 0x08);

        cmd_injector(channel, 0xf, 0, 0, 0, 0, 1, 0);
        store_continuous(channel);
        busy_wait_us(1);
        send_mrr(channel, 0, 31);
        busy_wait_us(1);
        setup_capture(channel, 3);
        busy_wait_us(1);
        start_capture(channel);
        busy_wait_us(1);
        stop_capture(channel);

        send_mrw(channel, 0, MODULE_BROADCAST, 25, 0x00);
        busy_wait_us(1);
        send_mrw(channel, 0, MODULE_BROADCAST, 25, 0x00);
        for (module = 0; module < modules; ++module) {
            temp = get_data_module_phase(channel, module, width, 0);
            for (line = 0; line < width; ++line) {
                if (!(temp & (1<<line)))
                    set_dq_remapping(channel, module*width+it, line);
            }
        }
    }
}

static uint16_t permute(int channel, int rank, int module, int width, const uint16_t old_value) {
    int it, mapping;
    uint16_t ret_val = 0;
    for (it = 0; it < width; ++it) {
        mapping = get_dq_remapping(channel, (module*width+it)^(rank&1));
        ret_val |= ((old_value >> it) & 1) << mapping;
        ret_val |= ((old_value >> (width + it)) & 1) << (mapping + width);
    }
    return ret_val;
}

uint8_t lfsr_next(uint8_t input) {
    uint8_t temp = 0;
    temp |= ((input)    &1) << 7;
    temp |= ((input>>7) &1) << 6;
    temp |= (((input>>6)&1) ^ (input&1)) << 5;
    temp |= (((input>>5)&1) ^ (input&1)) << 4;
    temp |= (((input>>4)&1) ^ (input&1)) << 3;
    temp |= ((input>>3) &1) << 2;
    temp |= ((input>>2) &1) << 1;
    temp |= ((input>>1) &1) << 0;
    return temp;
}

int compare_serial(int channel, int rank, int module, int width, uint16_t data, int inv, int print) {
    uint16_t module_data;
    uint16_t expected_data[8];
    uint16_t phase, _temp, _mask, _error;
    int _it;

    _mask = (1<<width) - 1;
    if (print)
        printf("expected:");
    for (phase = 0; phase < 8; ++phase) {
        _temp = 0;
        _temp |=   (((data & 1) << width) - (data & 1)) ^ (inv & _mask);
        data >>= 1;
        _temp |= (((((data & 1) << width) - (data & 1)) ^ (inv & _mask)) << width);
        data >>= 1;
        expected_data[phase] = permute(channel, rank, module, width, _temp);
        if (print)
            printf("%04"PRIx16"|", expected_data[phase]);
    }
    if (print)
        printf("\nrddata:");
    for (phase = 0; phase < 8; ++phase) {
        module_data = get_data_module_phase(channel, module, width, phase);
        if (print)
            printf("%04"PRIx16"|", module_data);
        _error = module_data ^ expected_data[phase];
        if (_error) {
            if (print)
                for (_it = 0; _it < 2*width; ++_it)
                    if ((_error >> _it) & 1)
                        printf("\nFailed for line:%d bit:%d, expected %d got %d",
                            _it % width, phase*2 + _it / width,
                            (expected_data[phase] >> _it) & 1, (module_data >> _it) & 1);
            if (print)
                printf("\n");
            return 0;
        }
    }
    if (print)
        printf("\n");
    return 1;
}

int compare(int channel, int rank, int module, int width, int data0, int data1, int inv, int select, int print) {
    uint16_t expected_data[8];
    uint16_t module_data;
    uint16_t phase, _temp, _mask,_error;
    uint8_t  lfsr0, lfsr1;
    int      _it;

    _mask = (1<<width) - 1;
    lfsr0 = data0;
    lfsr1 = data1;
    if (print)
        printf("\nexpected:");
    for (phase = 0; phase < 8; ++phase) {
        _temp = 0;
        for (_it = 0; _it < width; ++_it) {
            _temp |= (((select & (1 << _it)) ? (lfsr1 & 1) : (lfsr0 & 1)) & 1) << _it;
        }

        lfsr0 = lfsr_next(lfsr0);
        lfsr1 = lfsr_next(lfsr1);
        _temp ^= (inv & _mask);

        for (_it = 0; _it < width; ++_it) {
            _temp |= (((select & (1 << _it)) ? (lfsr1 & 1) : (lfsr0 & 1)) & 1 ) << (_it + width);
        }

        lfsr0 = lfsr_next(lfsr0);
        lfsr1 = lfsr_next(lfsr1);
        _temp ^= ((inv & _mask) << width);

        expected_data[phase] = permute(channel, rank, module, width, _temp);
        if (print)
            printf("%04"PRIx16"|", expected_data[phase]);
    }
    if (print)
        printf("\nrddata:");
    for (phase = 0; phase < 8; ++phase) {
        module_data = get_data_module_phase(channel, module, width, phase);
        if (print)
            printf("%04"PRIx16"|", module_data);
        _error = module_data ^ expected_data[phase];
        if (_error) {
            if (print)
                for (_it = 0; _it < 2*width; ++_it)
                    if ((_error >> _it) & 1)
                        printf("\nFailed for line:%d bit:%d, expected %d got %d",
                            _it % width, phase*2 + _it / width,
                            (expected_data[phase] >> _it) & 1, (module_data >> _it) & 1);
            if (print)
                printf("\n");
            return 0;
        }
    }
    if (print)
        printf("\n");
    return 1;
}

void cs_rst(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, rank, 0);
    /* Reset CS delay */
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel)
        ddrphy_CSRModule_B_csdly_rst_write(1);
    else
        ddrphy_CSRModule_A_csdly_rst_write(1);
#else
        ddrphy_CSRModule_csdly_rst_write(1);
#endif //SDRAM_PHY_SUBCHANNELS
    phy_deselect(channel, rank, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

void cs_inc(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, rank, 0);
    /* Increment CS delay */
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel)
        ddrphy_CSRModule_B_csdly_inc_write(1);
    else
        ddrphy_CSRModule_A_csdly_inc_write(1);
#else
    ddrphy_CSRModule_csdly_inc_write(1);
#endif //SDRAM_PHY_SUBCHANNELS
    phy_deselect(channel, rank, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

uint16_t get_cs_dly(int channel, int rank, int address) {
    uint16_t temp;
    phy_select(channel,rank, 0);
    temp = get_cs_dly_internal(channel);
    phy_deselect(channel, rank, 0);
    return temp;
}

void ca_rst(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, address, 0);
    /* Reset CA delay */
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel)
        ddrphy_CSRModule_B_cadly_rst_write(1);
    else
        ddrphy_CSRModule_A_cadly_rst_write(1);
#else
    ddrphy_CSRModule_cadly_rst_write(1);
#endif //SDRAM_PHY_SUBCHANNELS
    phy_deselect(channel, address, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

void ca_inc(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, address, 0);
    /* Increment CA delay */
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel)
        ddrphy_CSRModule_B_cadly_inc_write(1);
    else
        ddrphy_CSRModule_A_cadly_inc_write(1);
#else
    ddrphy_CSRModule_cadly_inc_write(1);
#endif //SDRAM_PHY_SUBCHANNELS
    phy_deselect(channel, address, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

uint16_t get_ca_dly(int channel, int rank, int address) {
    uint16_t temp;
    phy_select(channel, address, 0);
    temp = get_ca_dly_internal(channel);
    phy_deselect(channel, address, 0);
    return temp;
}

void par_rst(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, rank, 0);
    /* Reset PAR delay */
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel)
        ddrphy_CSRModule_B_pardly_rst_write(1);
    else
        ddrphy_CSRModule_A_pardly_rst_write(1);
#endif //SDRAM_PHY_SUBCHANNELS
    phy_deselect(channel, rank, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

void par_inc(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, rank, 0);
    /* Reset PAR delay */
#ifdef SDRAM_PHY_SUBCHANNELS
    if (channel)
        ddrphy_CSRModule_B_pardly_inc_write(1);
    else
        ddrphy_CSRModule_A_pardly_inc_write(1);
#endif //SDRAM_PHY_SUBCHANNELS
    phy_deselect(channel, rank, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

void ck_rst(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, rank, 0);
    /* Reset CK delay */
    ddrphy_CSRModule_ckdly_rst_write(1);
    phy_deselect(channel, rank, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

void ck_inc(int channel, int rank, int address) {
#ifdef SDRAM_PHY_ADDRESS_DELAY_CAPABLE
    phy_select(channel, rank, 0);
    /* Increment CK delay */
    ddrphy_CSRModule_ckdly_inc_write(1);
    phy_deselect(channel, rank, 0);
#endif // SDRAM_PHY_ADDRESS_DELAY_CAPABLE
}

void rd_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
    rd_rst_internal(channel);
    phy_deselect(channel, module, width);
}

void rd_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
    rd_inc_internal(channel);
    phy_deselect(channel, module, width);
}

void idly_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
    idly_rst_internal(channel);
#ifdef SDRAM_DELAY_PER_DQ
    for(int i=0; i < width; ++i) {
        phy_dq_select(channel, i, width);
        idly_dq_rst_internal(channel);
        phy_dq_deselect(channel, i, width);
    }
#else
    idly_dq_rst_internal(channel);
#endif // SDRAM_DELAY_PER_DQ
    phy_deselect(channel, module, width);
}

void idly_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
    idly_inc_internal(channel);
#ifdef SDRAM_DELAY_PER_DQ
    for(int i=0; i < width; ++i) {
        phy_dq_select(channel, i, width);
        idly_dq_inc_internal(channel);
        phy_dq_deselect(channel, i, width);
    }
#else
    idly_dq_inc_internal(channel);
#endif // SDRAM_DELAY_PER_DQ
    phy_deselect(channel, module, width);
}

void idly_dq_rst(int channel, int module, int width, int dq_line) {
    phy_dq_select(channel, dq_line, width);
    phy_select(channel, module, width);
    idly_dq_rst_internal(channel);
    phy_deselect(channel, module, width);
    phy_dq_deselect(channel, dq_line, width);
}

void idly_dq_inc(int channel, int module, int width, int dq_line) {
    phy_dq_select(channel, dq_line, width);
    phy_select(channel, module, width);
    idly_dq_inc_internal(channel);
    phy_deselect(channel, module, width);
    phy_dq_deselect(channel, dq_line, width);
}

uint16_t get_rd_dq_dly(int channel, int module, int width) {
    uint16_t temp;
    phy_select(channel, module, width);
    temp = get_rd_dq_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

uint16_t get_rd_dqs_dly(int channel, int module, int width) {
    uint16_t temp;
    if (width == 8) {
        module *= 2;
    }
    phy_select(channel, module, 4);
    temp = get_rd_dqs_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

uint16_t get_rd_dq_ck_dly(int channel, int module, int width) {
    uint16_t temp;
    phy_select(channel, module, width);
    temp = get_rd_dq_ck_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

uint16_t get_rd_preamble_ck_dly(int channel, int module, int width) {
    uint16_t temp;
    if (width == 8) {
        module *= 2;
    }
    phy_select(channel, module, 4);
    temp = get_rd_preamble_ck_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

void wr_dqs_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
    wr_rst_internal(channel);
    phy_deselect(channel, module, width);
}

void wr_dqs_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
    wr_inc_internal(channel);
    phy_deselect(channel, module, width);
}

void odly_dqs_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
    odly_dqs_rst_internal(channel);
    phy_deselect(channel, module, width);
}

void odly_dqs_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
    odly_dqs_inc_internal(channel);
    phy_deselect(channel, module, width);
}

uint16_t get_wr_dqs_dly(int channel, int module, int width) {
    uint16_t temp;
    if (width == 8) {
        module *= 2;
    }
    phy_select(channel, module, 4);
    temp = get_wr_dqs_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

void wr_dq_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
    wr_dq_rst_internal(channel);
    phy_deselect(channel, module, width);
}

void wr_dq_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
    wr_dq_inc_internal(channel);
    phy_deselect(channel, module, width);
}

void odly_dm_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
    odly_dm_rst_internal(channel);
    phy_deselect(channel, module, width);
}

void odly_dm_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
    odly_dm_inc_internal(channel);
    phy_deselect(channel, module, width);
}

void odly_dq_rst(int channel, int module, int width) {
    phy_select(channel, module, width);
#ifdef SDRAM_DELAY_PER_DQ
    for(int i=0; i < width; ++i) {
        phy_dq_select(channel, i, width);
        odly_dq_rst_internal(channel);
        phy_dq_deselect(channel, i, width);
    }
#else
    odly_dq_rst_internal(channel);
#endif
    phy_deselect(channel, module, width);
}

void odly_dq_inc(int channel, int module, int width) {
    phy_select(channel, module, width);
#ifdef SDRAM_DELAY_PER_DQ
    for(int i=0; i < width; ++i) {
        phy_dq_select(channel, i, width);
        odly_dq_inc_internal(channel);
        phy_dq_deselect(channel, i, width);
    }
#else
    odly_dq_inc_internal(channel);
#endif
    phy_deselect(channel, module, width);
}

void odly_per_dq_rst(int channel, int module, int width, int dq) {
    phy_select(channel, module, width);
    phy_dq_select(channel, dq, width);
    odly_dq_rst_internal(channel);
    phy_dq_deselect(channel, dq, width);
    phy_deselect(channel, module, width);
}

void odly_per_dq_inc(int channel, int module, int width, int dq) {
    phy_select(channel, module, width);
    phy_dq_select(channel, dq, width);
    odly_dq_inc_internal(channel);
    phy_dq_deselect(channel, dq, width);
    phy_deselect(channel, module, width);
}

uint16_t get_wr_dq_dly(int channel, int module, int width) {
    uint16_t temp;
    if (width == 8) {
        module *= 2;
    }
    phy_select(channel, module, 4);
    temp = get_wr_dq_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

uint16_t get_wr_dm_dly(int channel, int module, int width) {
    uint16_t temp;
    if (width == 8) {
        module *= 2;
    }
    phy_select(channel, module, 4);
    temp = get_wr_dm_dly_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

int captured_preamble(int channel, int module, int width) {
    int temp;
    if (width == 8) {
        module *= 2;
    }
    phy_select(channel, module, 4);
    temp = read_captured_preamble_internal(channel);
    phy_deselect(channel, module, width);
    return temp;
}

uint8_t recover_mrr_value(int channel, int module, int width) {
    uint16_t temp, dq_0;
    uint8_t ret, i;
    ret = 0;
    dq_0 = get_dq_remapping(channel, module*width);
    for (i = 4; i < 8; ++i){
        temp = get_data_module_phase(channel, module, width, i);
        ret |= (((temp >> dq_0) & 1) << ((i-4)*2));
        ret |= ((((temp >> dq_0) >> width) & 1) << ((i-4)*2 + 1));
    }
    return ret;
}

bool check_enumerate(int channel, int rank, int module, int width, int verbose) {
    int module_;
    int good = 1;
    send_mrw(channel, rank, MODULE_BROADCAST, 26, 0xFF);
    send_mrw(channel, rank, MODULE_BROADCAST, 27, 0xFF);
    send_mrw(channel, rank, MODULE_BROADCAST, 28, 0x00);
    send_mrw(channel, rank, MODULE_BROADCAST, 29, 0x00);
    if (module != -1) {
        send_mrw(channel, rank, module, 26, 0x00);
        send_mrw(channel, rank, module, 27, 0x00);
    }

    send_mrw(channel, rank, MODULE_BROADCAST, 25, 0x08);

    cmd_injector(channel, 0xf, 0, 0, 0, 0, 1, 0);
    store_continuous(channel);
    busy_wait_us(1);
    send_mrr(channel, rank, 31);
    busy_wait_us(1);
    if (module != -1)
        setup_capture(channel, 0);
    else
        setup_capture(channel, 3);
    busy_wait_us(1);
    start_capture(channel);
    busy_wait_us(1);
    stop_capture(channel);

    send_mrw(channel, rank, MODULE_BROADCAST, 25, 0x00);
    busy_wait_us(1);
    send_mrw(channel, rank, MODULE_BROADCAST, 25, 0x00);

    printf("\t");
    if (!verbose) {
        if (module != -1) {
            for (module_ = 0; module_ < SDRAM_PHY_MODULES/CHANNELS; module_++)
                good &= !capture_and_reduce_module(channel, module, width, module_ != module);
            printf("%s\n", good ? "pass" : "fail");
        }
        else
            printf("%s\n", !!capture_and_reduce_result(channel, 1) ? "pass" : "fail");
    } else {
        uint8_t data[DFII_CMDINJECTOR_DATA_BYTES];
        int i;
#ifdef SDRAM_PHY_SUBCHANNELS
        if (channel) {
            csr_rd_buf_uint8(CSR_SDRAM_DFII_B_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
        } else {
            csr_rd_buf_uint8(CSR_SDRAM_DFII_A_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
        }
#else
        csr_rd_buf_uint8(CSR_SDRAM_DFII_CMDINJECTOR_RESULT_ARRAY_ADDR, data, DFII_CMDINJECTOR_DATA_BYTES);
#endif
        for (i = 0; i < DFII_CMDINJECTOR_DATA_BYTES; ++i)
            printf("%02"PRIx8, data[i]);
        printf("\n");
    }
    return good;
}

void setup_enumerate(int channel, int rank, int module, int width, int verbose) {
    int module_, i;
    char *pattern = width == 8 ? "%04"PRIx16 : "%02"PRIx16;
    for (module_ = 0; module_ < SDRAM_PHY_MODULES/CHANNELS; module_++) {
        for (i = 0; i < 8; ++i)
            set_data_module_phase(channel, module_, width, i, 0xffff);
    }
    for (i = 0; i < 8; ++i)
        set_data_module_phase(channel, module, width, i, 0);
    if(verbose) {
        printf("Channel: %d, rank: %d\n", channel, rank);
        for(i = 0; i < 8; ++i) {
            printf("Phase:%d|", i);
            for (module_ = 0; module_ < SDRAM_PHY_MODULES/CHANNELS; module_++) {
                printf(pattern, get_wdata_module_phase(channel, module_, width, i));
            }
            printf("\n");
        }
    }
    // Start DQS toggling before Enter PDA Enum MPC
    cmd_injector(channel, 0xf, 0, 0xf, 1, 0, 0, 0);
    store_continuous(channel);
    // Enter PDA Enumerate Programming Mode
    send_mpc(channel, rank, 0xB, 1);
    busy_wait_us(1);
    send_mpc(channel, rank, (0x60 | (module & 0xf)), 1);
    busy_wait_us(1);
    // Exit PDA Enumerate Programming Mode
    send_mpc(channel, rank, 0xA, 1);
    busy_wait_us(1);
    // Stop DQS toggling after Exit PDA Enum MPC
    cmd_injector(channel, 0xf,  0, 0, 0, 0, 0, 0);
    store_continuous(channel);

    for (module_ = 0; module_ < SDRAM_PHY_MODULES/CHANNELS; module_++) {
        for (i = 0; i < 8; ++i)
            set_data_module_phase(channel, module_, width, i, 0xffff);
    }
}

static void long_mpc(int channel, int rank, int cmd, int wrdata_active) {
    cmd_injector(channel, 0xf,  0,       0xf | (cmd<<5), wrdata_active, 0, 0, 0);
    store_continuous(channel);
    busy_wait_us(1);
    cmd_injector(channel, 0xff, 0,       0xf | (cmd<<5), wrdata_active, 0, 0, 1);
    cmd_injector(channel, 0x3f, 1<<rank, 0xf | (cmd<<5), wrdata_active, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
    cmd_injector(channel, 0xff, 0,       0,              wrdata_active, 0, 0, 1);
    cmd_injector(channel, 0xf,  0,       0,              wrdata_active, 0, 0, 0);
    store_continuous(channel);
    busy_wait_us(1);
}

static void short_mpc(int channel, int rank, int cmd, int wrdata_active) {
    cmd_injector(channel, 0xf,  0,       0,              wrdata_active, 0, 0, 0);
    store_continuous(channel);
    busy_wait_us(1);
    cmd_injector(channel, 0xff, 0,       0,              wrdata_active, 0, 0, 1);
    cmd_injector(channel, 0x1,  1<<rank, 0xf | (cmd<<5), wrdata_active, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
    cmd_injector(channel, 0xff, 0,       0,              wrdata_active, 0, 0, 1);
    cmd_injector(channel, 0xf,  0,       0,              wrdata_active, 0, 0, 0);
    store_continuous(channel);
    busy_wait_us(1);
}

void send_mpc(int channel, int rank, int cmd, int wrdata_active) {
    if (single_cycle_MPC)
        short_mpc(channel, rank, cmd, wrdata_active);
    else
        long_mpc(channel, rank, cmd, wrdata_active);
}

void send_mrw_rcd(int channel, int rank, int reg, int value) {
    cmd_injector(channel, 1<<0, 1<<rank, 0x5 | (reg<<5), 0, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, 0x5 | (reg<<5), 0, 0, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, value | 1<<10, 0, 0, 0, 1);
    cmd_injector(channel, 1<<2, 0, value | 1<<10, 0, 0, 0, 1);
    cmd_injector(channel, 1<<3, 0, value | 1<<10, 0, 0, 0, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
    cmd_injector(channel, 0xff, 0, 0, 0, 0, 0, 1);
}

void send_mrw_no_mpc(int channel, int rank, int reg, int value) {
    cmd_injector(channel, 1<<0, 1<<rank, 0x5 | (reg<<5), 0, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, 0x5 | (reg<<5), 0, 0, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, value, 0, 0, 0, 1);
    cmd_injector(channel, 1<<2, 0, value, 0, 0, 0, 1);
    cmd_injector(channel, 1<<3, 0, value, 0, 0, 0, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(5);
    cmd_injector(channel, 0xff, 0, 0, 0, 0, 0, 1);
}

void send_mrw(int channel, int rank, int module, int reg, int value) {
    send_mpc(channel, rank, 0x70 | (module&0xF), 0);
    cmd_injector(channel, 1<<0, 1<<rank, 0x5 | (reg<<5), 0, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, 0x5 | (reg<<5), 0, 0, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, value, 0, 0, 0, 1);
    cmd_injector(channel, 1<<2, 0, value, 0, 0, 0, 1);
    cmd_injector(channel, 1<<3, 0, value, 0, 0, 0, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(5);
    cmd_injector(channel, 0xff, 0, 0, 0, 0, 0, 1);
    send_mpc(channel, rank, 0x7f, 0);
}

void send_mrr(int channel, int rank, int reg) {
    setup_rddata_cnt(channel, 0);
    setup_rddata_cnt(channel, 8);
    cmd_injector(channel, 1<<0, 1<<rank, 0x15 | (reg<<5), 0, 0, 1, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, 0x15 | (reg<<5), 0, 0, 1, 1);
    else
        cmd_injector(channel, 1<<1, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<2, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<3, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 1, 1);
    issue_single(channel);
    busy_wait_us(5);
    cmd_injector(channel, 0xff, 0, 0, 0, 0, 0, 1);
    setup_rddata_cnt(channel, 0);
}

void send_wleveling_write(int channel, int rank) {
    int wr_2 = 0 | (1<<10) | (1<<11); // Second beat of write, no auto precharge, no wr_partial
    cmd_injector(channel, 1<<0, 1<<rank, 0x0D | (1<<5), 1, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, 0x0D | (1<<5), 0, 0, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, wr_2, 0, 0, 0, 1);
    cmd_injector(channel, 1<<2, 0, wr_2, 0, 0, 0, 1);
    cmd_injector(channel, 1<<3, 0, wr_2, 0, 0, 0, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 0, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(5);
}

void send_precharge(int channel, int rank) {
    int pre = 0xB; // Precharge all

    cmd_injector(channel, 1<<0, 1<<rank, pre, 0, 0, 0, 1);
    cmd_injector(channel, 0xfe, 0, 0, 0, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, pre, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
}

void send_activate(int channel, int rank) {
    int bg  = 0 << 8;
    int ba  = 0 << 6;

    int act_1 = 0x0 | ba | bg;              // Activate bank group 0, bank 0, row 0
    int act_2 = 0;

    cmd_injector(channel, 1<<0, 1<<rank, act_1, 0, 0, 0, 1);
    cmd_injector(channel, 0xfe, 0, 0, 0, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, act_1, 0, 0, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, act_2, 0, 0, 0, 1);
    cmd_injector(channel, 1<<2, 0, act_2, 0, 0, 0, 1);
    cmd_injector(channel, 1<<3, 0, act_2, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
}

void send_write(int channel, int rank) {
    int bg  = 0 << 8;
    int ba  = 0 << 6;
    int col = 0;

    int wr_1 = 0xD | (1 << 5) | ba | bg;    // Write to bank group 0, bank 0
    int wr_2 = col | (1 << 11);             // Second beat of write, with auto precharge, no wr_partial

    send_activate(channel, rank);
    cmd_injector(channel, 1<<0, 1<<rank, wr_1, 1, 0, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, wr_1, 1, 0, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, wr_2, 1, 0, 0, 1);
    cmd_injector(channel, 1<<2, 0, wr_2, 1, 0, 0, 1);
    cmd_injector(channel, 1<<3, 0, wr_2, 1, 0, 0, 1);
    cmd_injector(channel, 1<<4, 0, 0, 1, 0, 0, 1);
    cmd_injector(channel, 1<<5, 0, 0, 1, 0, 0, 1);
    cmd_injector(channel, 1<<6, 0, 0, 1, 0, 0, 1);
    cmd_injector(channel, 1<<7, 0, 0, 1, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
}

void send_write_byte(int channel, int rank, int module, int byte) {
    int bg  = 0 << 8;
    int ba  = 0 << 6;
    int col = 0;

    int wr_1 = 0xD | (1 << 5) | ba | bg;    // Write to bank group 0, bank 0
    int wr_2 = col;                         // Second beat of write, with auto precharge, with wr_partial

    uint32_t mask     = ~((1 << (byte&1)) << (2*module));
    uint8_t  transfer = byte >> 1;
    uint8_t  cmd_r = 0;
    int      cmd = 0;

    send_activate(channel, rank);
    cmd_injector(channel, 1<<0, 1<<rank, wr_1, 1, WRDATA_BITMASK, 0, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, wr_1, 1, WRDATA_BITMASK, 0, 1);
    else
        cmd_injector(channel, 1<<1, 0, wr_2, 1, WRDATA_BITMASK, 0, 1);
    cmd_injector(channel, 1<<2, 0, wr_2, 1, WRDATA_BITMASK, 0, 1);
    cmd_injector(channel, 1<<3, 0, wr_2, 1, WRDATA_BITMASK, 0, 1);
    cmd_injector(channel, 1<<4, 0, 0, 1, WRDATA_BITMASK, 0, 1);
    cmd_injector(channel, 1<<5, 0, 0, 1, WRDATA_BITMASK, 0, 1);
    cmd_injector(channel, 1<<6, 0, 0, 1, WRDATA_BITMASK, 0, 1);
    cmd_injector(channel, 1<<7, 0, 0, 1, WRDATA_BITMASK, 0, 1);
    switch(transfer) {
    case 0:
        cmd = wr_1;
        cmd_r = 1<<rank;
        break;
    case 1:
        if (N2_mode) {
            cmd = wr_1;
            break;
        }
    case 2:
    case 3:
        cmd = wr_2;
        break;
    default:
        break;
    }
    cmd_injector(channel, 1<<transfer, cmd_r, cmd, 1, mask, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
}

void send_read(int channel, int rank) {
    int bg  = 0 << 8;
    int ba  = 0 << 6;
    int col = 0;

    int rd_1 = 0x1D | (1 << 5) | ba |bg;    // Read from bank group 0, bank 0
    int rd_2 = col;                         // Second beat of read, with auto precharge

    setup_rddata_cnt(channel, 0);
    setup_rddata_cnt(channel, 8);

    send_activate(channel, rank);
    cmd_injector(channel, 1<<0, 1<<rank, rd_1, 0, 0, 1, 1);
    if (N2_mode)
        cmd_injector(channel, 1<<1, 0, rd_1, 0, 0, 1, 1);
    else
        cmd_injector(channel, 1<<1, 0, rd_2, 0, 0, 1, 1);
    cmd_injector(channel, 1<<2, 0, rd_2, 0, 0, 1, 1);
    cmd_injector(channel, 1<<3, 0, rd_2, 0, 0, 1, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 1, 1);
    issue_single(channel);
    busy_wait_us(5);
    setup_rddata_cnt(channel, 0);
}

void prep_nop(int channel, int rank) {
    cmd_injector(channel, 1<<0, 0, 0x3FFF, 0, 0, 1, 1);
    cmd_injector(channel, 1<<1, 3, 0x3FFF, 0, 0, 1, 1);
    cmd_injector(channel, 1<<2, 0, 0x3FFF, 0, 0, 1, 1);
    cmd_injector(channel, 1<<3, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<4, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<5, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<6, 0, 0, 0, 0, 1, 1);
    cmd_injector(channel, 1<<7, 0, 0, 0, 0, 1, 1);
}

void force_issue_single(void) {
#ifdef SDRAM_PHY_SUBCHANNELS
    sdram_dfii_b_cmdinjector_single_shot_write(1);
    sdram_dfii_a_cmdinjector_single_shot_write(1);
#else
    sdram_dfii_cmdinjector_single_shot_write(1);
#endif
    sdram_dfii_force_issue_write(1);
#ifdef SDRAM_PHY_SUBCHANNELS
    sdram_dfii_b_cmdinjector_single_shot_write(0);
    sdram_dfii_a_cmdinjector_single_shot_write(0);
#else
    sdram_dfii_cmdinjector_single_shot_write(0);
#endif
    busy_wait_us(1);
}

/**
 * enter_cstm
 *
 * Enters CS training when doing Host->DRAM training.
 * Sends "Enter CS Training Mode" MPC over multiple cycles.
 * JESD79-5A 4.20.2
 */
void enter_cstm(int channel, int rank) {
    send_mpc(channel, rank, 1, 0);
}

/**
 * exit_cstm
 *
 * Exits CS training when doing Host->DRAM training.
 * Sends "Exit CS Training Mode" MPC over multiple cycles.
 * JESD79-5A 4.20.2
 */
void exit_cstm(int channel, int rank) {
    send_mpc(channel, rank, 0, 0);
}

static void cs_sample_prep(int channel, int rank, int address, int shift_0101) {
    cmd_injector(channel, 0xf, 0, 0x1f, 0, 0, 1, 0);
    cmd_injector(channel, 0x5<<(!!shift_0101), 1<<rank, 0x1f, 0, 0, 1, 0);
    store_continuous(channel);
    busy_wait_us(1);
}

/**
 * cs_check_if_works
 *
 * Checks if during CSTM, CS and CK signals are aligned.
 * When they are aligned, then DRAM will send 0s on all DQ's.
 * We sample DQ's over multiple cycles, reduce them with
 * the OR operation and check if all were 0s.
 * JESD79-5A 4.20
 */
uint32_t cs_check_if_works(int channel, int rank, int address, int shift_0101, int modules, int width) {
    uint32_t works = 0;
    cs_sample_prep(channel, rank, address, shift_0101);
    for (int module = 0; module < modules; ++module)
        works |= or_sample_module(channel, module, width) << module;
    return works;
}

/**
 * enter_catm
 *
 * Enters CA training when doing Host->DRAM training.
 * Sends "Enter CA Training Mode" MPC.
 *
 * As no commands are being processed by the DRAM other
 * than NOPs it is safe to send this MPC over multiple
 * cycles.
 * JESD79-5A 4.19.2
 */
void enter_catm(int channel, int rank) {
    send_mpc(channel, rank, 3, 0);
}

/**
 * exit_catm
 *
 * Exits CA training when doing Host->DRAM training.
 * Sends multiple NOPs is consecutive cycles (at least 2 needed).
 * JESD79-5A 4.19.2
 */
void exit_catm(int channel, int rank) {
    cmd_injector(channel, 0xf, 0, 0x1f, 0, 0, 0, 0);
    store_continuous(channel);
    cmd_injector(channel, 0xff, 1<<rank, 0x1f, 0, 0, 0, 1);
    issue_single(channel);
    busy_wait_us(1);
    cmd_injector(channel, 0xf, 0, 0, 0, 0, 0, 0);
    store_continuous(channel);
    cmd_injector(channel, 0xff, 0, 0, 0, 0, 0, 1);
}


static void ca_sample_prep(int channel, int rank, int address, int l2h, int phase_shift) {
    cmd_injector(channel, 0xf,              0,       (!l2h)<<address, 0, 0, 1, 0);

    if (phase_shift == 0) {
        cmd_injector(channel, 0x1,              1<<rank,    l2h<<address, 0, 0, 1, 0);
    } else {
        cmd_injector(channel, 0x1,              0,          l2h<<address, 0, 0, 1, 0);
        cmd_injector(channel, 0x1<<phase_shift, 1<<rank, (!l2h)<<address, 0, 0, 1, 0);
    }
    store_continuous(channel);
    busy_wait_us(1);
}

/**
 * ca_check_if_works
 *
 * Checks if during CATM, CA and CS signals are aligned.
 * The DRAM will reduce sampled CA values with the XOR
 * operation.
 *
 * To check if a specific CA line is correctly aligned, we
 * change only the CA line we want to test. If it is aligned,
 * the DRAM will respond with only 1s on DQ lines.
 *
 * First we test scenario, where selected line is set low
 * and for one phase when CS_n is low, we set it high.
 * We sample DQ's over multiple cycles, reduce them with
 * the AND operation and check if all were 1s.
 *
 * We also perform a second test where the selected line is
 * inverted. So for all phases it is high and when CS_n goes
 * low, selected CA also goes low.
 * This time, we reduce sampled DQ's with the OR operation as
 * we expect the response to be 0s.
 *
 * Performing both tests, ensures that selected delay works
 * just as good when going low->high and high->low.
 * JESD79-5A 4.19
 */
int ca_check_if_works(int channel, int rank, int address, int shift_back) {
    int ok;

    // Test change from low to high
    ca_sample_prep(channel, rank, address, 1, shift_back);
    ok = and_sample(channel);

    // Test change from high to low
    ca_sample_prep(channel, rank, address, 0, shift_back);
    ok &= !or_sample(channel);

    return ok;
}

void enter_write_leveling(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_wlevel_en_write(1);
    } else {
        ddrphy_CSRModule_A_wlevel_en_write(1);
    }
#else
    ddrphy_CSRModule_wlevel_en_write(1);
#endif
    busy_wait_us(1);
}

int wr_dqs_check_if_works(int channel, int rank, int module, int width) {
    send_wleveling_write(channel, rank);
    return and_sample_module(channel, module, width);
}

void wleveling_scan(int channel, int rank, int module, int width, int max_delay, eye_t *eye) {
    int works, delay;

    odly_dqs_rst(channel, module, width);
    for(delay = 0; delay < max_delay; ++delay) {
        works = 1;

        // Check multiple times, as we can be on the edge of transition
        // Make sure we aren't in meta stable delay
        for (int i = 0; i < 16; i++) {
            works &= wr_dqs_check_if_works(channel, rank, module, width);
        }

        printf("%d", works);
        if (works && eye->state == BEFORE) {
            eye->start = delay;
            eye->state = INSIDE;
        }

        odly_dqs_inc(channel, module, width);
    }
}

void exit_write_leveling(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        return ddrphy_CSRModule_B_wlevel_en_write(0);
    } else {
        return ddrphy_CSRModule_A_wlevel_en_write(0);
    }
#else
    return ddrphy_CSRModule_wlevel_en_write(0);
#endif
}

void clear_phy_fifos(int channel) {
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_discard_rd_fifo_write(1);
    } else {
        ddrphy_CSRModule_A_discard_rd_fifo_write(1);
    }
#else
    ddrphy_CSRModule_discard_rd_fifo_write(1);
#endif
    busy_wait_us(5);
#ifdef SDRAM_PHY_SUBCHANNELS
    if(channel) {
        ddrphy_CSRModule_B_discard_rd_fifo_write(0);
    } else {
        ddrphy_CSRModule_A_discard_rd_fifo_write(0);
    }
#else
    ddrphy_CSRModule_discard_rd_fifo_write(0);
#endif
}

/*-----------------------------------------------------------------------*/
/* RCD Training Helpers                                                  */
/*-----------------------------------------------------------------------*/

/**
 * get_rcd_id
 *
 * Calculates RCDs slave id based on the rank number.
 */
uint8_t get_rcd_id(int rank) {
    return rank / 2;
}

/**
 * rcd_set_dca_rate
 *
 * Sets selected DCA mode in the RCD.
 * It's a part of RCD initialization sequence (JESD82-511 3.4.3).
 * JESD82-511 3.4
 */
void rcd_set_dca_rate(int channel, int rank, enum dca_rate rate) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    uint8_t rw_data[5];

    // we need to modify RW00[1:0]
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    rw_data[0] &= ~(0b11 << 0);         // clear last setting
    rw_data[0] |= ((0b11 & rate) << 0); // and set a new one

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, &rw_data[0], 1, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with setting DCA rate in the RCD\n");
}

/**
 * rcd_set_dimm_operating_speed
 *
 * As part of RCD initialization sequence, the host must set DIMMs
 * operating speed in the RCD.
 * This setting is stored in RW05 and RW06.
 * Additionally PLL bypass mode is supported.
 *
 * `target_speed` is operating speed in MT/s, so target_speed=3200
 * for 3200 MT/s.
 * Pass target_speed=-1 to enable PLL bypass mode.
 */
void rcd_set_dimm_operating_speed(int channel, int rank, int target_speed) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    uint8_t coarse, fine;
    int offset_speed, bin_size;

    // Special case, -1 means: enable PLL bypass mode
    if (target_speed == -1) {
        coarse = 0x0f;

        ok &= sdram_rcd_write(rcd, 0, 0, 0, 5, &coarse, 1, false);
        busy_wait_us(10);

        if (!ok)
            printf("There was a problem with enabling PLL bypass mode in the RCD\n");

        return;
    }

    // Speed bins are of form:
    //     bin_size * coarse - 20 * fine < target_speed <= bin_size * coarse

    if (2000 <= target_speed && target_speed <= 2100) {
        // Down-bin data rate speed bin is 100 MT/s wide
        bin_size = 100;

        // Down-bin data rate starts at 2000 MT/s, so we subtract that offset
        offset_speed = target_speed - 2000;

        // Special value for down-bin data rate speed bin (JESD82-511 8.7.1)
        coarse = 0x0e;
    } else {
        if (!(2800 <= target_speed && target_speed <= 6400)) {
            printf("Unsupported speed bin %d MT/s. Defaulting to 2800 MT/s.\n", target_speed);
            target_speed = 2800;
        }

        // Normal speed bin if 400 MT/s wide
        bin_size = 400;

        // Speed bins start at 2800 MT/s, so we subtract that offset
        offset_speed = target_speed - 2800;

        // We calculate the coarse speed bin. As the range is left
        // side exclusive, we subtract one from the offset_speed.
        coarse = (offset_speed - 1) / 400;
    }

    // Catch a special case when target_speed is either
    // 2000 MT/s or 2800 MT/s. Technically they are not
    // allowed by the spec, but we treat them as if they
    // are 2001 MT/s or 2801 MT/s.
    if (offset_speed == 0)
        offset_speed = 1;

    int in_bin_offset = offset_speed % bin_size;
    fine = (bin_size - in_bin_offset) / 20;

    // Catch special case, when target_speed is at the end of the speed bin
    if (in_bin_offset == 0)
        fine = 0;

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 5, &coarse, 1, false);
    busy_wait_us(10);
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 6, &fine, 1, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with setting DIMM speed in the RCD\n");
}

void rcd_set_dimm_operating_speed_band(int channel, int rank, int target_speed) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    ok &= sdram_rcd_read(rcd, 0, 0, 0, 4, rw_data, false);
    if (target_speed <= 2800)
        rw_data[1] |= 1<<7;

    ok &= sdram_rcd_write(rcd, 0, 0, 0, 4, rw_data, 4, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with setting DIMM band in the RCD\n");
}

void rcd_set_termination_and_vref(int rank) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    // we need to modify RW10
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0x10, rw_data, false);
    rw_data[0] = 0;
    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0x10, rw_data, 4, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with setting IBT in the RCD\n");

    for (int i=0; i<2; ++i) {
        ok = true;
        // we need to modify from RW40 to RW47
        ok &= sdram_rcd_read(rcd, 0, i, 0, 0x40, rw_data, false);
        rw_data[0] = 0x2d;
        rw_data[1] = 0x2d;
        rw_data[2] = 0x2d;
        rw_data[3] = 0x2d;
        // write the settings back
        ok &= sdram_rcd_write(rcd, 0, i, 0, 0x40, rw_data, 4, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with setting channel's:%c Vref 40-43 in the RCD\n", 'A'+i);

        ok = true;
        ok &= sdram_rcd_read(rcd, 0, i, 0, 0x44, rw_data, false);
        rw_data[0] = 0x2d;
        rw_data[1] = 0x2d;
        rw_data[2] = 0x2d;
        rw_data[3] = 0x2d;
        // write the settings back
        ok &= sdram_rcd_write(rcd, 0, i, 0, 0x44, rw_data, 4, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with setting channel's:%c Vref 44-47 in the RCD\n", 'A'+i);

        ok = true;
        ok &= sdram_rcd_read(rcd, 0, i, 0, 0x48, rw_data, false);
        rw_data[0] = 0x2d;
        rw_data[1] = 0x2d;
        // write the settings back
        ok &= sdram_rcd_write(rcd, 0, i, 0, 0x48, rw_data, 4, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with setting channel's:%c Vref 48-49 in the RCD\n", 'A'+i);
    }
}

void rcd_set_enables_and_slew_rates(
    int rank, int qcke, int qcae, int qckh, int qcah, int slew) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];
    for (int i=0; i<2; ++i) {
        ok = true;
        // we need to modify from RW08 to RW0F
        // 0D and 0F are only for LRDIMMs
        ok &= sdram_rcd_read(rcd, 0, i, 0, 0x08, rw_data, false);
        rw_data[0] = qcke;
        rw_data[1] = qcae;
        rw_data[2] = qckh;
        // write the settings back
        ok &= sdram_rcd_write(rcd, 0, i, 0, 0x08, rw_data, 4, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with setting channel's:%c "
                   "Clock Driver enable, QCA/CS enable or "
                   "Clock Driver characteristics in the RCD\n", 'A'+i);

        ok = true;
        ok &= sdram_rcd_read(rcd, 0, i, 0, 0x0C, rw_data, false);
        rw_data[0] = qcah;
        rw_data[2] = slew;
        // write the settings back
        ok &= sdram_rcd_write(rcd, 0, i, 0, 0x0C, rw_data, 4, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with setting channel's:%c "
                   "QCK/QCA/QCS drivers slew rate or "
                   "QCA/QCS driver characteristics in the RCD\n", 'A'+i);
    }
}


/**
 * rcd_set_qrst
 *
 * Sets DRAMs QRST signal.
 */
void rcd_set_qrst(int channel, int rank) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    // we send Set CH_[AB]_DRAM Reset commands (CMD5 or CMD7)
    // to the RW04 register (JESD82-511 8.6.5)
    uint8_t cmd = 5 + (2 * channel);

    ok &= sdram_rcd_write(rcd, 0, 0, 0, 4, &cmd, 1, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with setting DRAM reset for channel %c\n", 'A'+channel);
}

/**
 * rcd_clear_qrst
 *
 * Clears DRAMs QRST signal.
 */
void rcd_clear_qrst(int channel, int rank) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    // we send Clear CH_[AB]_DRAM Reset commands (CMD6 or CMD8)
    // to the RW04 register (JESD82-511 8.6.5)
    uint8_t cmd = 6 + (2 * channel);

    ok &= sdram_rcd_write(rcd, 0, 0, 0, 4, &cmd, 1, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with clearing DRAM reset for channel %c\n", 'A'+channel);
}

/**
 * rcd_forward_all_dram_cmds
 *
 * Sets "DRAM Interface Forward All CMDs" field of RCDs RW01 register.
 *
 * After Host->RCD training is complete, command blocking in the RCD
 * shall be disabled. It's a part of RCD initialization sequence.
 * JESD82-511 3.8 Figure 23
 */
void rcd_forward_all_dram_cmds(int channel, int rank, bool forward) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    uint8_t rw_data[5];

    // we need to modify RW01[1]
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    rw_data[1] &= ~(0b1 << 1);          // clear last setting
    rw_data[1] |= ((0b1 & forward) << 1); // and set a new one

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, rw_data, 4, false);

    if (!ok)
        printf("There was a problem with changing CMD blocking in the RCD\n");
    busy_wait_us(10);
}

/**
 * rcd_release_qcs
 *
 * Releases QCS signals for a selected channel.
 *
 * When `sideband` is true, it will send CMD14 or CMD15
 * to RW04 of the RCD.
 * When `sideband` is false, it will send a single NOP
 * on the DCS/DCA interface.
 *
 * It's a part of RCD initialization sequence.
 * JESD82-511 3.8 Figure 23
 */
void rcd_release_qcs(int channel, int rank, bool sideband) {
    if (sideband) {
        bool ok = true;
        uint8_t rcd = get_rcd_id(rank);

        // we send CH_[AB]_QCS_HIGH commands (CMD14 or CMD15)
        // to the RW04 register (JESD82-511 8.6.5)
        uint8_t cmd = 14 + channel;
        ok &= sdram_rcd_write(rcd, 0, 0, 0, 4, &cmd, 1, false);
        busy_wait_us(10);

        if (!ok)
            printf("There was a problem with releasing the QCS for channel %c\n", 'A'+channel);
    } else {
        cmd_injector(channel, 0xff,       0,    0, 0, 0, 0, 1);
        cmd_injector(channel, 0x01, 1<<rank, 0x1f, 0, 0, 0, 1);
        issue_single(channel);
        busy_wait_us(1);
    }
    busy_wait_us(10);
}

void enter_ca_pass(int rcd) {
    bool ok = true;

    uint8_t rw_data[5];

    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    rw_data[0] |= (0b1 << 2);

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, rw_data, 4, false);

    if (!ok)
        printf("There was a problem with entering CA pass Through in the RCD\n");
    busy_wait_us(10);
}

void exit_ca_pass(int rcd) {
    bool ok = true;

    uint8_t rw_data[5];

    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    rw_data[0] &= ~(0b1 << 2);

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, rw_data, 4, false);

    if (!ok)
        printf("There was a problem with exiting CA pass Through in the RCD\n");
    busy_wait_us(10);
}

void select_ca_pass(int rank) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    uint8_t rw_data[5];

    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    rw_data[0] &= ~(0b1 << 3);
    rw_data[0] |= ((rank & 0b1) << 3);

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, rw_data, 4, false);

    if (!ok)
        printf("There was a problem with selecting rank for CA pass Through in the RCD\n");
    busy_wait_us(10);
}

static int alert_or_reduce(void) {
    ddrphy_CSRModule_sample_alert_write(0);   // disable sampling
    ddrphy_CSRModule_alert_reduce_write(0x0); // start with 0 and reduce with OR
    ddrphy_CSRModule_reset_alert_write(1);    // apply above settings
    busy_wait_us(10);
    ddrphy_CSRModule_sample_alert_write(1);   // enable sampling
    busy_wait_us(10);
    ddrphy_CSRModule_sample_alert_write(0);   // disable sampling
    return !ddrphy_CSRModule_alert_read();
}

static int alert_and_reduce(void) {
    ddrphy_CSRModule_sample_alert_write(0);   // disable sampling
    ddrphy_CSRModule_alert_reduce_write(0x3); // start with 1 and reduce with AND
    ddrphy_CSRModule_reset_alert_write(1);    // apply above settings
    busy_wait_us(10);
    ddrphy_CSRModule_sample_alert_write(1);   // enable sampling
    busy_wait_us(10);
    ddrphy_CSRModule_sample_alert_write(0);   // disable sampling
    return !!ddrphy_CSRModule_alert_read();
}

/*-----------------------------------------------------------------------*/
/* Host->RCD CS Training (DCSTM) Helpers                                 */
/*-----------------------------------------------------------------------*/

/**
 * enter_dcstm
 *
 * Enables Host->RCD CS training (DCSTM) for selected subchannel on selected rank.
 * JESD82-511 5.1.1
 */
void enter_dcstm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t w_data[5];
    uint8_t r_data[5];

    // we need to modify RW01 and RW02
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, w_data, false);

    // in RW01 we unset bit 5 to make sure we get channel feedback on alert_n
    w_data[1] &= ~(1 << 5);

    // in RW02 we select CS training mode
    // channel A settings: RW02[1:0]
    // channel B settings: RW02[3:2]
    // higher bit selects CS training mode, while lower bit selects rank
    w_data[2] &= ~(0xf); // clear bits for all channels
    w_data[2] |= (0b10 | (rank & 1)) << (2 * channel); // set new bits

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, w_data, 4, false);
    busy_wait_us(10);
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, r_data, false);
    for (int i=0; i<4; ++i) {
        ok &= (w_data[i] == r_data[i]);
    }

    if (!ok) {
        printf("There was a problem with entering Host->RCD CS training (DCSTM)\n");
        busy_wait(10);
    }
}

/**
 * exit_dcstm
 *
 * Disables Host->RCD CS training (DCSTM) for selected subchannel on selected rank.
 * JESD82-511 5.1.1
 */
void exit_dcstm(int channel, int rank) {
    cmd_injector(channel, 0xf, 0, 0x7f, 0, 0, 0, 0);
    store_continuous(channel);
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t w_data[5];
    uint8_t r_data[5];

    // we need to modify RW02
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, w_data, false);

    // in RW02 we clear training mode setting
    // channel A settings: RW02[1:0]
    // channel B settings: RW02[3:2]
    w_data[2] &= ~(0xf); // clear bits for all channels

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, w_data, 4, false);
    busy_wait_us(10);
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, r_data, false);
    for (int i=0; i<4; ++i) {
        ok &= (w_data[i] == r_data[i]);
    }

    if (!ok) {
        printf("There was a problem with exiting Host->RCD CS training (DCSTM)\n");
        busy_wait(10);
    }
}

/**
 * dcs_check_if_works
 *
 * Checks if during DCSTM, DCS and CK signals are aligned.
 * When they are aligned, then RCD will send 0 on alert_n.
 * We sample DQ's over multiple cycles, reduce them with
 * the OR operation and check if all were 0s.
 * JESD82-511 5.1.1
 */
uint32_t dcs_check_if_works(int channel, int rank, int address, int shift_0101, int modules, int width) {
    cs_sample_prep(channel, rank, address, shift_0101);
    return alert_or_reduce();
}

/*-----------------------------------------------------------------------*/
/* RCD->DRAM CK Helpers                                                  */
/*-----------------------------------------------------------------------*/

void qck_inc(int channel, int rank, int address) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];
    uint8_t delay;
    ok &= sdram_rcd_read(rcd, 0, channel, 0, 0x10, rw_data, false);
    delay = (rw_data[2] + 1) & 0x3f;

    uint8_t rw_number = 0x12;
    uint8_t rw_value = delay | (1 << 7); // enable delays

    for (int i = 0; i< 4; ++i) {
        ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with incrementing Q%cCK output delay\n", 'A' + i);
        rw_number++;
    }
}

void qck_rst(int channel, int rank, int address) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);

    uint8_t rw_number = 0x12;
    uint8_t rw_value = 0 | (1 << 7); // enable delays

    for (int i = 0; i< 4; ++i) {
        ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
        busy_wait_us(1);
        if (!ok)
            printf("There was a problem with incrementing Q%cCK output delay\n", 'A' + i);
        rw_number++;
    }
}

/*-----------------------------------------------------------------------*/
/* RCD->DRAM CS Training (QCSTM) Helpers                                 */
/*-----------------------------------------------------------------------*/

/**
 * qcs_inc
 *
 * Increment output delay for QCS signal
 * JESD82-511 8.13.6-9
 */
void qcs_inc(int channel, int rank, int address) {
    bool ok = true;
    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];
    uint8_t delay;
    uint8_t rw_number_base = (rank & 1) ? 0x18 : 0x14;
    uint8_t rw_idx = (rank & 1) ? 0 : 3;
    ok &= sdram_rcd_read(rcd, 0, channel, 0, rw_number_base, rw_data, false);
    delay = (rw_data[rw_idx] + 1) & 0x3f;

    uint8_t rw_number = 0x17 + (rank & 1);
    uint8_t rw_value = delay | (1 << 7); // enable delays

    for (int i = 0; i < 2; ++i) {
        ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with incrementing Q%cCS%c_n output delay\n", 'A' + i, '0' + (rank & 1));
        rw_number += 2;
    }
}

/**
 * qcs_rst
 *
 * Reset output delay for QCS signal
 * JESD82-511 8.13.6-9
 */
void qcs_rst(int channel, int rank, int address) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    // 0x17: QACS0_n, 0x18: QACS1_n, 0x19: QBCS0_n, 0x1a: QBCS1_n
    uint8_t rw_number = 0x17 + (rank & 1);
    uint8_t rw_value = (1 << 7); // Reset value, keep enabled

    for (int i = 0; i < 2; ++i) {
        ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with resetting Q%cCS%c_n output delay\n", 'A' + i, '0' + (rank & 1));
        rw_number += 2;
    }
}

/**
 * enter_qcstm
 *
 * Enables RCD->DRAM CS training (QCSTM) for selected subchannel on selected rank.
 * JESD82-511 5.1.2
 */
void enter_qcstm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    enter_ca_pass(rcd);
    select_ca_pass(rank);
    enter_cstm(channel, rank);
    exit_ca_pass(rcd);

    // we need to modify RW03
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    // in RW03 we select CS training mode
    // QCSTM enable: RW03[0]
    // QCSTM rank selection: RW03[1]
    rw_data[3] &= ~(0b11); // clear setting bits
    rw_data[3] |= 0b1 | ((rank & 1) << 1); // set new bits

    // write RW03 setting back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 3, &rw_data[3], 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with entering RCD->DRAM CS training (QCSTM)\n");
}

void enter_qcstm_RAMBUS_QUIRK(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    enter_ca_pass(rcd);
    select_ca_pass(rank);
    enter_cstm(channel, rank);
    exit_ca_pass(rcd);

    // we need to modify RW03
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    // in RW03 we select CS training mode
    // QCSTM enable: RW03[0]
    // QCSTM rank selection: RW03[1]
    rw_data[3] &= ~(0b11); // clear setting bits

    // write RW03 setting back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 3, &rw_data[3], 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with entering RCD->DRAM CS training (QCSTM)\n");
}

/**
 * exit_qcstm
 *
 * Disables RCD->DRAM CS training (QCSTM) for selected subchannel on selected rank.
 * JESD82-511 5.1.2
 */
void exit_qcstm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    // we need to modify RW03
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    // in RW03 we disable CS training mode
    // QCSTM enable: RW03[0]
    // QCSTM rank selection: RW03[1]
    rw_data[3] &= ~(0b11); // clear setting bits

    // write RW03 setting back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 3, &rw_data[3], 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with exiting RCD->DRAM CS training (QCSTM)\n");

    enter_ca_pass(rcd);
    select_ca_pass(rank);
    exit_cstm(channel, rank);
    exit_ca_pass(rcd);
}

static void qcs_sample_prep(int channel) {
    cmd_injector(channel, 0xf, 0, 0, 0, 0, 1, 0);
    store_continuous(channel);
    busy_wait_us(1);
}

uint32_t qcs_check_if_works(int channel, int rank, int address, int shift_0101, int modules, int width) {
    int works = 0;
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];
    uint8_t delay;
    uint8_t rw_number_base = (rank & 1) ? 0x18 : 0x14;
    uint8_t rw_idx = (rank & 1) ? 0 : 3;
    ok &= sdram_rcd_read(rcd, 0, channel, 0, rw_number_base, rw_data, false);
    delay = rw_data[rw_idx] & 0x3f;
    delay |= shift_0101 << 6;

    uint8_t rw_number = 0x17 + (rank & 1);
    uint8_t rw_value = delay | (1 << 7); // enable delays

    ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with shifting CS Q%cCS%c_n output delay\n", 'A', '0' + (rank & 1));
    rw_number += 2;
    ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with shifting CS Q%cCS%c_n output delay\n", 'B', '0' + (rank & 1));

    qcs_sample_prep(channel);
    for (int module = 0; module < modules; ++module) {
        works |= or_sample_module(channel, module, width) << module;
    }
    return works;
}

static void qcs_sample_prep_RAMBUS_QUIRK(int channel, int rank) {
    cmd_injector(channel, 0xf, 0, 0x1f, 0, 0, 1, 0);
    cmd_injector(channel, 0x5, 1<<rank, 0x1f, 0, 0, 1, 0);
    store_continuous(channel);
    busy_wait_us(1);
}

uint32_t qcs_check_if_works_RAMBUS_QUIRK(int channel, int rank, int address, int shift_0101, int modules, int width) {
    int works = 0;
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];
    uint8_t delay;
    uint8_t rw_number_base = (rank & 1) ? 0x18 : 0x14;
    uint8_t rw_idx = (rank & 1) ? 0 : 3;
    ok &= sdram_rcd_read(rcd, 0, channel, 0, rw_number_base, rw_data, false);
    delay = rw_data[rw_idx] & 0x3f;
    delay |= shift_0101 << 6;

    uint8_t rw_number = 0x17 + (rank & 1);
    uint8_t rw_value = delay | (1 << 7); // enable delays

    ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with shifting CS Q%cCS%c_n output delay\n", 'A', '0' + (rank & 1));
    rw_number += 2;
    ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
    busy_wait_us(10);
    if (!ok)
        printf("There was a problem with shifting CS Q%cCS%c_n output delay\n", 'B', '0' + (rank & 1));

    qcs_sample_prep_RAMBUS_QUIRK(channel, rank);
    for (int module = 0; module < modules; ++module) {
        works |= or_sample_module(channel, module, width) << module;
    }
    return works;
}

/*-----------------------------------------------------------------------*/
/* Host->RCD CA Training (DCATM) Helpers                                 */
/*-----------------------------------------------------------------------*/

/**
 * enter_dcatm
 *
 * Enables Host->RCD CA training (DCATM) for selected subchannel on selected rank.
 * JESD82-511 5.2.1
 */
void enter_dcatm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t w_data[5];
    uint8_t r_data[5];

    // we need to modify RW01 and RW02
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, w_data, false);

    // in RW01 we unset bit 5 to make sure we get channel feedback on alert_n
    w_data[1] &= ~(1 << 5);

    // in RW02 we select CA training mode
    // channel A settings: RW02[1:0]
    // channel B settings: RW02[3:2]
    // write 0b01 to enter CA training
    w_data[2] &= ~(0xf); // clear bits for all channels
    w_data[2] |=   0b01 << (2 * channel);  // set new bits

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, w_data, 4, false);
    busy_wait_us(10);
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, r_data, false);
    for (int i=0; i<4; ++i) {
        ok &= (w_data[i] == r_data[i]);
    }

    if (!ok) {
        printf("There was a problem with entering Host->RCD CA training (DCATM)\n");
        busy_wait(10);
    }
}

/**
 * exit_dcatm
 *
 * Disables Host->RCD CA training (DCATM) for selected subchannel on selected rank.
 * JESD82-511 5.2.1
 */
void exit_dcatm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t w_data[5];
    uint8_t r_data[5];

    // we need to modify RW02
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, w_data, false);

    // channel A settings: RW02[1:0]
    // channel B settings: RW02[3:2]
    w_data[2] &= ~(0xf); // clear bits for all channels

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, w_data, 4, false);
    busy_wait_us(10);
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, r_data, false);
    for (int i=0; i<4; ++i) {
        ok &= (w_data[i] == r_data[i]);
    }

    if (!ok) {
        printf("There was a problem with exiting Host->RCD CA training (DCATM)\n");
        busy_wait(10);
    }
}

/**
 * dca_sample_prep
 *
 * Alternative implementation for ca_sample_prep to use
 * in Host->RCD DCA training.
 *
 * CA is being sent in 7-bit halves and ca_sample_prep
 * only sets values for selected address, so a sample DCA
 * state could look like the one below:
 *
 *  CA[x]   | 1 1 0 1  1 1 0 1  |
 *  CA[x+7] |  0 0 0 0  0 0 0 0 |
 * DCA[x]   | 10100010 10100010 |
 *
 * This completely prevents transition detection.
 * That's why this function sets the default state for CA
 * from the other half as well.
 * This way, DCA can look like this:
 *
 *  CA[x]   | 1 1 0 1  1 1 0 1  |
 *  CA[x+7] |  1 1 1 1  1 1 1 1 |
 * DCA[x]   | 11110111 11110111 |
 */
static void dca_sample_prep(int channel, int rank, int address, int l2h, int shift_back) {
    int address_other_half = (address + 7) % 14;

    // state where all CA bits have the same value
    int default_state = ((!l2h) << address) | ((!l2h) << address_other_half);

    // state where only the selected `address` bit is negated
    int negated_state =   (l2h  << address) | ((!l2h) << address_other_half);

    cmd_injector(    channel, 0xf,              0,       default_state, 0, 0, 1, 0);

    if (shift_back) {
        cmd_injector(channel, 0x1,              0,       negated_state, 0, 0, 1, 0);
        cmd_injector(channel, 0x1<<shift_back,  1<<rank, default_state, 0, 0, 1, 0);
    } else {
        cmd_injector(channel, 0x1,              1<<rank, negated_state, 0, 0, 1, 0);
    }
    store_continuous(channel);
    busy_wait_us(1);
}

static void dca_training_xor_sampling_edge(int channel, int rank, uint8_t edge) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t w_data[5];
    uint8_t r_data[5];

    // we need to modify RW02[5:4]
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, w_data, false);

    w_data[2] &= ~(0b11 << 4);       // clear last setting
    w_data[2] |= (0b11 & edge) << 4; // and set a new one

    // write the settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, w_data, 4, false);
    busy_wait_us(10);
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, r_data, false);
    for (int i=0; i<4; ++i) {
        ok &= (w_data[i] == r_data[i]);
    }

    if (!ok) {
        printf("There was a problem with changing DCA XOR sampling edge\n");
        busy_wait(10);
    }
}

/**
 * dca_check_if_works
 *
 * Checks if during DCATM, DCA and DCS signals are aligned.
 * The RCD will reduce sampled DCA values with the XOR
 * operation.
 *
 * To check if a specific CA line is correctly aligned, we
 * change only the CA line we want to test. If it is aligned,
 * the DRAM will respond with only 1s on DQ lines.
 *
 * First we test scenario, where selected line is set low
 * and for one phase when DCS_n is low, we set it high.
 * We sample DQ's over multiple cycles, reduce them with
 * the AND operation and check if all were 1s.
 *
 * We also perform a second test where the selected line is
 * inverted. So for all phases it is high and when DCS_n goes
 * low, selected DCA also goes low.
 * This time, we reduce sampled DQ's with the OR operation as
 * we expect the response to be 0s.
 *
 * Performing both tests, ensures that selected delay works
 * just as good when going low->high and high->low.
 * JESD82-511 5.2.1
 */
int dca_check_if_works_ddr(int channel, int rank, int address, int shift_back) {
    int ok = 1;
    int temp;

    for(int edge=0; edge<2; ++edge) {
        // Test change from low to high
        dca_sample_prep(channel, rank, address + edge*7, 1, shift_back);
        dca_training_xor_sampling_edge(channel, rank, 0);
        temp = alert_and_reduce();
        ok &= temp;
        dca_training_xor_sampling_edge(channel, rank, 1<<edge);
        temp = alert_and_reduce();
        ok &= temp;

        // Test change from high to low
        dca_sample_prep(channel, rank, address + edge*7, 0, shift_back);
        dca_training_xor_sampling_edge(channel, rank, 0);
        temp = alert_and_reduce();
        ok &= temp;
        dca_training_xor_sampling_edge(channel, rank, 1<<edge);
        temp = alert_or_reduce();
        ok &= temp;
    }
    dca_training_xor_sampling_edge(channel, rank, 0); // restore default values

    return ok;
}

int dca_check_if_works_ddr_MONTAGE_QUIRK(int channel, int rank, int address, int shift_back) {
    int ok = 1;
    int temp;

    for(int edge=0; edge<2; ++edge) {
        // Test change from low to high
        dca_sample_prep(channel, rank, address + edge*7, 1, shift_back);
        dca_training_xor_sampling_edge(channel, rank, 0);
        temp = alert_and_reduce();
        ok &= temp;
        dca_training_xor_sampling_edge(channel, rank, 1<<(edge^1));
        temp = alert_and_reduce();
        ok &= temp;

        // Test change from high to low
        dca_sample_prep(channel, rank, address + edge*7, 0, shift_back);
        dca_training_xor_sampling_edge(channel, rank, 0);
        temp = alert_and_reduce();
        ok &= temp;
        dca_training_xor_sampling_edge(channel, rank, 1<<(edge^1));
        temp = alert_or_reduce();
        ok &= temp;
    }
    dca_training_xor_sampling_edge(channel, rank, 0); // restore default values

    return ok;
}

int dca_check_if_works_sdr(int channel, int rank, int address, int shift_back) {
    int ok = 1;

    dca_training_xor_sampling_edge(channel, rank, 1);
    // Test change from low to high
    ca_sample_prep(channel, rank, address, 1, shift_back);
    ok &= alert_and_reduce();

    // Test change from high to low
    ca_sample_prep(channel, rank, address, 0, shift_back);
    ok &= !alert_or_reduce();

    dca_training_xor_sampling_edge(channel, rank, 0); // restore default values
    return ok;
}

/*-----------------------------------------------------------------------*/
/* RCD->DRAM CA Training (QCATM) Helpers                                 */
/*-----------------------------------------------------------------------*/

static uint8_t qca_address_lines = 0;

/**
 * qca_inc
 *
 * Increment output delay for QCA signal
 * JESD82-511 8.13.10-11
 */
void qca_inc(int channel, int rank, int address) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];
    uint8_t delay;
    ok &= sdram_rcd_read(rcd, 0, channel, 0, 0x18, rw_data, false);
    delay = (rw_data[3] + 1) & 0x3f;

    uint16_t rw_number = 0x1b;
    uint8_t rw_value = delay | (1 << 7); // enable delays

    for (int i = 0; i < 2; ++i) {
        ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with incrementing Q%cCA output delay\n", 'A' + i);
        rw_number += 1;
    }
}

/**
 * qca_rst
 *
 * Reset output delay for QCA signal
 * JESD82-511 8.13.10-11
 */
void qca_rst(int channel, int rank, int address) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);

    uint16_t rw_number = 0x1b;
    uint8_t rw_value = (1 << 7); // keep delay enabled

    for (int i = 0; i < 2; ++i) {
        ok &= sdram_rcd_write(rcd, 0, channel, 0, rw_number, &rw_value, 1, false);
        busy_wait_us(10);
        if (!ok)
            printf("There was a problem with resetting Q%cCA output delay\n", 'A' + channel);
        rw_number += 1;
    }
}

/**
 * enter_qcatm
 *
 * Enables RCD->DRAM CA training (QCATM) for selected subchannel on selected rank.
 * While there is no real QCA Training Mode, we still need to enable CA Pass-Through
 * mode, which can be treated like enabling QCA Training Mode.
 * JESD82-511 5.2.2
 */
void enter_qcatm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    enter_ca_pass(rcd);
    select_ca_pass(rank);
    enter_catm(channel, rank);
    exit_ca_pass(rcd);

    // we need to modify RW00, RW01
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    // we set RW00[2] to enable CA Pass Through mode
    rw_data[0] |= 1 << 2;
    // in RW00[3] we select rank for CA Pass Through mode
    rw_data[0] |= (rank & 1) << 3;
    // Power Down Mode (RW00[6]) must be disabled
    // TODO: I think Power Down Mode is already disabled at this point
    rw_data[0] &= ~(1 << 6);

    // CA Parity Checking (RW01[0]) needs to be disabled
    rw_data[1] &= ~1;
    // RCD must be set to forward DRAM commands (RW01[1])
    rw_data[1] |= 0b10;
    // RCD must be set to blcok BCOM commands (RW01[3])
    rw_data[1] &= ~(0b1000);

    // write RW00 and RW01 settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, rw_data, 2, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with entering RCD->DRAM CA training (QCATM)\n");
}

/**
 * exit_qcatm
 *
 * Disables RCD->DRAM CA training (QCATM) for selected subchannel on selected rank.
 * While there is no real QCA Training Mode, we still need to disable CA Pass-Through
 * mode, which can be treated like disabling QCA Training Mode.
 * JESD82-511 5.2.2
 */
void exit_qcatm(int channel, int rank) {
    bool ok = true;

    uint8_t rcd = get_rcd_id(rank);
    uint8_t rw_data[5];

    // we need to modify RW00, RW01
    ok &= sdram_rcd_read(rcd, 0, 0, 0, 0, rw_data, false);

    // we unset RW00[2] to disable CA Pass Through mode
    rw_data[0] &= ~(1 << 2);

    // TODO: do we reenable them?
    // // CA Parity Checking (RW01[0]) needs to be disabled
    // rw_data[1] &= ~1;

    // write RW00 and RW01 settings back
    ok &= sdram_rcd_write(rcd, 0, 0, 0, 0, rw_data, 2, false);
    busy_wait_us(10);

    if (!ok)
        printf("There was a problem with exiting RCD->DRAM CA training (QCATM)\n");

    enter_ca_pass(rcd);
    select_ca_pass(rank);
    exit_catm(channel, rank);
    exit_ca_pass(rcd);
}

int qca_check_if_works(int channel, int rank, int _address, int shift_back) {
    int ok = 1, res;
    if (qca_address_lines == 0) {
        qca_address_lines = 13;
        cmd_injector(channel, 0xf, 0, 1<<13, 0, 0, 1, 0);
        cmd_injector(channel, 0x1, 1, 1<<13, 0, 0, 1, 0);
        store_continuous(channel);
        if (and_sample(channel))
            qca_address_lines = 14;
    }

    for (int address = 0; address < qca_address_lines; ++address) {
        res = ca_check_if_works(channel, rank, address, shift_back);
        ok &= res;
    }
    return ok;
}

#endif // defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_DDR5)
