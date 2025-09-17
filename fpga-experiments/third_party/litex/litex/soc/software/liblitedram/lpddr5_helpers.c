#include <liblitedram/lpddr5_helpers.h>

#if defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_LPDDR5)

#include <stdio.h>
#define DFII_PIX_DATA_BYTES SDRAM_PHY_DFI_DATABITS/8

void rd_rst(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_rdly_dq_bitslip_rst_write(1);
}

void rd_inc(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_rdly_dq_bitslip_write(1);
}

void idly_rst(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_rdly_dq_rst_write(1);
}

void idly_inc(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_rdly_dq_inc_write(1);
}

void wr_rst(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_wdly_dq_bitslip_rst_write(1);
}

void wr_inc(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_wdly_dq_bitslip_write(1);
}

void odly_rst(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_wdly_dq_rst_write(1);
}

void odly_inc(uint8_t module) {
    ddrphy_dly_sel_write(1<<module);
    ddrphy_wdly_dq_inc_write(1);
}

void enter_CK2WCK_leveling(void) {
    ddrphy_wlevel_en_write(1);
    busy_wait_us(1);
    send_mrw(18, DDRX_MR_WRLVL_RESET | 1<<6);
}

bool sample_CK2WCK_shift(void) {
    uint8_t _buff[DFII_PIX_DATA_BYTES];
    uint8_t ans;
    int i;
    ddrphy_wlevel_strobe_write(1);
    sdram_dfii_pi0_address_write(0);
    sdram_dfii_pi0_baddress_write(0);
    sdram_dfii_pi0_command_write(DFII_COMMAND_RDDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_ck(20);
    csr_rd_buf_uint32(CSR_SDRAM_DFII_PI0_RDDATA_ADDR, (uint32_t *)_buff, DFII_PIX_DATA_BYTES/4);
    ans = _buff[0];
    for (i=1; i<DFII_PIX_DATA_BYTES; ++i) {
        ans &= _buff[i];
    }
    ans = ans & (ans >> 4);
    ans = ans & (ans >> 2);
    ans = ans & (ans >> 1);
    return ans;
}

void exit_CK2WCK_leveling(void) {
    send_mrw(18, DDRX_MR_WRLVL_RESET);
    busy_wait_us(1);
    ddrphy_wlevel_en_write(0);
}

void send_rdc(void) {
    sdram_dfii_pi0_address_write(0);
    sdram_dfii_pi0_baddress_write(5);
    sdram_dfii_pi0_command_write(DFII_COMMAND_WE|DFII_COMMAND_CS|DFII_COMMAND_RDDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

static uint16_t get_data_module_phase(int module, int width, int phase, bool print) {
    uint16_t ret_value;
    int pebo;   // module's positive_edge_byte_offset
    int nebo;   // module's negative_edge_byte_offset, could be undefined if SDR DRAM is used
    uint8_t data[DFII_PIX_DATA_BYTES];
    uint16_t die_mask = (1<<width)-1;
    uint16_t single_transfer_size = DFII_PIX_DATA_BYTES / 16;
    ret_value = 0;
    csr_rd_buf_uint8(CSR_SDRAM_DFII_PI0_RDDATA_ADDR, data, DFII_PIX_DATA_BYTES);
    if(phase == 0 && print) {
        for (int i = 0; i < DFII_PIX_DATA_BYTES; ++i) {
            printf("%"PRIx8"|", data[DFII_PIX_DATA_BYTES-1-i]);
        }
        printf("\n");
    }
    // CSR are read as BIG Endian

    pebo = 2 * (8 - phase) * single_transfer_size - 1 - (module * SDRAM_PHY_DQ_DQS_RATIO)/8;
    nebo = pebo - single_transfer_size;

    ret_value |= data[pebo] & die_mask;
    ret_value |= (data[nebo] & die_mask) << width;
    return ret_value;
}

static void set_data_module_phase(int module, int width, int phase, uint16_t wrdata, bool print) {
    int pebo;   // module's positive_edge_byte_offset
    int nebo;   // module's negative_edge_byte_offset, could be undefined if SDR DRAM is used
    uint8_t data[DFII_PIX_DATA_BYTES];
    uint16_t die_mask = (1<<width)-1;
    uint16_t single_transfer_size = DFII_PIX_DATA_BYTES / 16;
    csr_rd_buf_uint8(CSR_SDRAM_DFII_PI0_WRDATA_ADDR, data, DFII_PIX_DATA_BYTES);
    // CSR are read as BIG Endian

    pebo = 2 * (8 - phase) * single_transfer_size - 1 - (module * SDRAM_PHY_DQ_DQS_RATIO)/8;
    nebo = pebo - single_transfer_size;

    data[pebo] = wrdata & die_mask;
    data[nebo] = (wrdata >>width ) & die_mask;

    if(phase == 7 && print) {
        for (int i = 0; i < DFII_PIX_DATA_BYTES; ++i) {
            printf("%"PRIx8"|", data[DFII_PIX_DATA_BYTES-1-i]);
        }
        printf("\n");
    }
    csr_wr_buf_uint8(CSR_SDRAM_DFII_PI0_WRDATA_ADDR, data, DFII_PIX_DATA_BYTES);
}

int compare_serial(int module, int width,
                   uint16_t data, int inv, int print) {
    uint16_t module_data;
    uint16_t expected_data[8];
    uint16_t phase, _temp, _mask, _error;
    int _it;

    if (width == 16)
        width /= 2;
    _mask = (1<<width) - 1;
    if (print)
        printf("expected:");
    for (phase = 0; phase < 8; ++phase) {
        _temp = 0;
        _temp |=   (((data & 1) << width) - (data & 1)) ^ (inv & _mask);
        data >>= 1;
        _temp |= (((((data & 1) << width) - (data & 1)) ^ (inv & _mask)) << width);
        data >>= 1;
        expected_data[phase] = _temp;
        if (print)
            printf("%04"PRIx16"|", expected_data[phase]);
    }
    if (print)
        printf("\nrddata:");
    for (phase = 0; phase < 8; ++phase) {
        module_data = get_data_module_phase(module, width, phase, print);
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

void send_mrw(uint8_t reg, uint8_t val) {
    sdram_dfii_pi0_address_write(val);
    sdram_dfii_pi0_baddress_write(reg);
    sdram_dfii_pi0_command_write(DFII_COMMAND_RAS|DFII_COMMAND_CAS|DFII_COMMAND_WE|DFII_COMMAND_CS);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

void send_mrr(uint8_t reg) {
    sdram_dfii_pi0_address_write(reg);
    sdram_dfii_pi0_baddress_write(1);
    sdram_dfii_pi0_command_write(DFII_COMMAND_WE|DFII_COMMAND_CS|DFII_COMMAND_RDDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

// TODO: Add support for multiple modules and x16 width
uint8_t recover_mrr_value(uint8_t module, uint8_t width) {
    int i, j, idx;
    uint8_t _buff[DFII_PIX_DATA_BYTES];
    uint8_t tst[DFII_PIX_DATA_BYTES];

    csr_rd_buf_uint32(CSR_SDRAM_DFII_PI0_RDDATA_ADDR, (uint32_t *)_buff, DFII_PIX_DATA_BYTES/4);
    for (i=0;i<DFII_PIX_DATA_BYTES/4;++i) {
        for (j=0;j<4;++j) {
            tst[i*4+j] = _buff[(i+1)*4-j-1];
        }
    }
    idx = DFII_PIX_DATA_BYTES - 1 - (module * SDRAM_PHY_DQ_DQS_RATIO)/8;
    return tst[idx];
}

void read_registers(int module, int width) {
    int i;
    for (i = 0; i < 128; ++i) {
        send_mrr(i);
        printf("\tMR:%3d %02"PRIX8"\n", i, recover_mrr_value(module, width));
    }
}

void send_fifo_write(void) {
    sdram_dfii_pi0_address_write(0);
    sdram_dfii_pi0_baddress_write(3);
    sdram_dfii_pi0_command_write(DFII_COMMAND_WE|DFII_COMMAND_CS|DFII_COMMAND_WRDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

void send_fifo_read(void) {
    sdram_dfii_pi0_address_write(0);
    sdram_dfii_pi0_baddress_write(4);
    sdram_dfii_pi0_command_write(DFII_COMMAND_WE|DFII_COMMAND_CS|DFII_COMMAND_RDDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

void setup_serial_write_data(uint8_t module, uint8_t width,
                             uint16_t data, int inv, int print) {
    int it;
    uint16_t wrdata, _mask;
    if(width == 16)
        width /= 2;
    _mask = (1<<width) - 1;

    if(print)
        printf("wrdata:");
    for (it =0; it <8; ++it) {
        wrdata = 0;
        wrdata |=   (((data & 1) << width) - (data & 1)) ^ (inv & _mask);
        data >>= 1;
        wrdata |= (((((data & 1) << width) - (data & 1)) ^ (inv & _mask)) << width);
        data >>= 1;
        if(print)
            printf("%04"PRIx16"|", wrdata);
        set_data_module_phase(module, width, it, wrdata, print);
    }
    if(print)
        printf("\n");
}

void sdram_read(uint8_t bank, uint16_t row, uint8_t column) {
    sdram_dfii_pi0_address_write(row);
    sdram_dfii_pi0_baddress_write(bank);
    sdram_dfii_pi0_command_write(DFII_COMMAND_RAS|DFII_COMMAND_CS);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);

    sdram_dfii_pi0_address_write(column);
    sdram_dfii_pi0_baddress_write(bank);
    sdram_dfii_pi0_command_write(DFII_COMMAND_CAS|DFII_COMMAND_CS|DFII_COMMAND_RDDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

void sdram_write(uint8_t bank, uint16_t row, uint8_t column, uint8_t value) {
    uint8_t data[DFII_PIX_DATA_BYTES];
    int p, i;
    for(i=0;i<DFII_PIX_DATA_BYTES;i++) {
        if (i&2) {
            data[i] = value;
        } else {
            data[i] = ~value;
        }
        printf("%"PRIx8":", data[i]);
    }
    for(p=0;p<SDRAM_PHY_PHASES;p++) {
            csr_wr_buf_uint8(sdram_dfii_pix_wrdata_addr(p),
                             data,
                             DFII_PIX_DATA_BYTES);
    }

    sdram_dfii_pi0_address_write(row);
    sdram_dfii_pi0_baddress_write(bank);
    sdram_dfii_pi0_command_write(DFII_COMMAND_RAS|DFII_COMMAND_CS);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);

    sdram_dfii_pi0_address_write(column);
    sdram_dfii_pi0_baddress_write(bank);
    sdram_dfii_pi0_command_write(DFII_COMMAND_CAS|DFII_COMMAND_CS|DFII_COMMAND_WRDATA);
    sdram_dfii_pi0_command_issue_write(1);
    busy_wait_us(1);
}

#endif // defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_DDR5)
