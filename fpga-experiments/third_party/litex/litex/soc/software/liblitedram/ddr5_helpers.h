#ifndef LIBLITEDRAM_DDR5_HELPERS_H
#define LIBLITEDRAM_DDR5_HELPERS_H

#include <stdbool.h>

#include <generated/csr.h>

#ifdef CSR_SDRAM_BASE
#include <generated/sdram_phy.h>

#ifdef SDRAM_PHY_DDR5

#ifdef SDRAM_PHY_SUBCHANNELS
#define CHANNELS 2
#else
#define CHANNELS 1
#endif

typedef struct {
    enum {
        BEFORE,
        INSIDE,
        AFTER,
    } state;
    int start;
    int center;
    int end;
} eye_t;

#define DEFAULT_EYE   { \
    .state  = BEFORE,   \
    .start  = -1,       \
    .center = -1,       \
    .end    = -1,       \
}

// 0xf addresses all DRAM modules on selected rank
#define MODULE_BROADCAST (0xf)

void prep_payload(int channel, int cs, int command, int wrdata_en,
                  uint64_t wrdata_mask, int rddata_en);
void upload_payload(int channel, int phases);
void store_payload(int channel, int single);
void cmd_injector(int channel, int phases, int cs, int command,
                  int wrdata_en, uint64_t wrdata_mask, int rddata_en, int single);
void setup_rddata_cnt(int channel, int value);
void store_continuous(int channel);
void issue_single(int channel);
uint16_t get_data_module_phase(int channel, int module, int width, int phase);
uint16_t get_wdata_module_phase(int channel, int module, int width, int phase);
void set_data_module_phase(int channel, int module, int width, int phase, uint16_t wrdata);

void reset_all_phy_regs(int channels, int ranks, int addresses, int modules, int width);
void enable_phy(void);

void setup_capture(int channel, int setup);
void start_capture(int channel);
void stop_capture(int channel);
uint32_t capture_and_reduce_result(int channel, int operation);
uint32_t capture_and_reduce_module(int channel, int module, int width, int operation);
int or_sample(int channel);
int and_sample(int channel);
int or_sample_module(int channel, int module, int width);
int and_sample_module(int channel, int module, int width);

void read_registers(int channel, int rank, int module, int width);

int check_ca_13th_line(int32_t channel, int32_t rank);

void enable_dfi_2n_mode(void);
void disable_dfi_2n_mode(void);
void disable_dram_2n_mode(int, int);
int in_2n_mode(void);

#define WRDATA_BITMASK ((1<<(2*SDRAM_PHY_MODULES/CHANNELS))-1)

typedef void (*inc_func)(int, int, int);

void ck_rst(int channel, int rank, int address);
void ck_inc(int channel, int rank, int address);

void cs_rst(int channel, int rank, int address);
void cs_inc(int channel, int rank, int address);
uint16_t get_cs_dly(int channel, int rank, int address);

void ca_rst(int channel, int rank, int address);
void ca_inc(int channel, int rank, int address);
uint16_t get_ca_dly(int channel, int rank, int address);

void par_rst(int channel, int rank, int address);
void par_inc(int channel, int rank, int address);

void get_dimm_dq_remapping(int channel, int modules, int width);
uint8_t lfsr_next(uint8_t input);
int compare_serial(int channel, int rank, int module, int width,
                   uint16_t data, int inv, int print);
int compare(int channel, int rank, int module, int width,
            int data0, int data1,
            int inv, int select, int print);

void rd_rst(int channel, int module, int width);
void rd_inc(int channel, int module, int width);
void idly_rst(int channel, int module, int width);
void idly_inc(int channel, int module, int width);
void idly_dq_rst(int channel, int module, int dq_line, int width);
void idly_dq_inc(int channel, int module, int dq_line, int width);

uint16_t get_rd_dq_dly(int channel, int module, int width);
uint16_t get_rd_dqs_dly(int channel, int module, int width);
uint16_t get_rd_dq_ck_dly(int channel, int module, int width);
uint16_t get_rd_preamble_ck_dly(int channel, int module, int width);

void wr_dqs_rst(int channel, int module, int width);
void wr_dqs_inc(int channel, int module, int width);
void odly_dqs_rst(int channel, int module, int width);
void odly_dqs_inc(int channel, int module, int width);

uint16_t get_wr_dqs_dly(int channel, int module, int width);

void wr_dq_rst(int channel, int module, int width);
void wr_dq_inc(int channel, int module, int width);
void odly_dm_rst(int channel, int module, int width);
void odly_dm_inc(int channel, int module, int width);
void odly_dq_rst(int channel, int module, int width);
void odly_dq_inc(int channel, int module, int width);
void odly_per_dq_rst(int channel, int module, int width, int dq);
void odly_per_dq_inc(int channel, int module, int width, int dq);

uint16_t get_wr_dq_dly(int channel, int module, int width);
uint16_t get_wr_dm_dly(int channel, int module, int width);

int captured_preamble(int channel, int module, int width);
uint8_t recover_mrr_value(int channel, int module, int width);
void setup_enumerate(int channel, int rank, int module, int width, int verbose);
bool check_enumerate(int channel, int rank, int module, int width, int verbose);
void send_mpc(int channel, int rank, int cmd, int wrdata_active);
void send_mrw_rcd(int channel, int rank, int reg, int value);
void send_mrw_no_mpc(int channel, int rank, int reg, int value);
void send_mrw(int channel, int rank, int module, int reg, int value);
void send_mrr(int channel, int rank, int reg);
void send_wleveling_write(int channel, int rank);
void send_activate(int channel, int rank);
void send_precharge(int channel, int rank);
void send_write(int channel, int rank);
void send_write_byte(int channel, int rank, int module, int byte);
void send_read(int channel, int rank);
void prep_nop(int channel, int rank);
void force_issue_single(void);

void enter_cstm(int channel, int rank);
void exit_cstm(int channel, int rank);
uint32_t cs_check_if_works(int channel, int rank, int address, int shift_0101, int modules, int width);

void enter_catm(int channel, int rank);
void exit_catm(int channel, int rank);
int ca_check_if_works(int channel, int rank, int address, int shift_back);

void enter_write_leveling(int channel);
void exit_write_leveling(int channel);
void clear_phy_fifos(int channel);
int wr_dqs_check_if_works(int channel, int rank, int module, int width);
void wleveling_scan(int channel, int rank, int module, int width, int max_delay, eye_t *eye_state);

uint8_t get_rcd_id(int rank);

enum dca_rate {
    SDR1 = 0b00,
    SDR2 = 0b10,
    DDR  = 0b01,
};

void rcd_set_dca_rate(int channel, int rank, enum dca_rate rate);
void rcd_set_dimm_operating_speed(int channel, int rank, int target_speed);
void rcd_set_dimm_operating_speed_band(int channel, int rank, int target_speed);
void rcd_set_termination_and_vref(int rank);
void rcd_set_enables_and_slew_rates(
    int rank, int qcke, int qcae, int qckh, int qcah, int slew);
void rcd_set_qrst(int channel, int rank);
void rcd_clear_qrst(int channel, int rank);
void rcd_forward_all_dram_cmds(int channel, int rank, bool forward);
void rcd_release_qcs(int channel, int rank, bool sideband);

void enter_ca_pass(int rank);
void exit_ca_pass(int rank);
void select_ca_pass(int rank);

void enter_dcstm(int channel, int rank);
void exit_dcstm(int channel, int rank);
uint32_t dcs_check_if_works(int channel, int rank, int address, int shift_0101, int modules, int width);

void qck_inc(int channel, int rank, int address);
void qck_rst(int channel, int rank, int address);

void qcs_inc(int channel, int rank, int address);
void qcs_rst(int channel, int rank, int address);
void enter_qcstm(int channel, int rank);
void enter_qcstm_RAMBUS_QUIRK(int channel, int rank);
void exit_qcstm(int channel, int rank);
uint32_t qcs_check_if_works(int channel, int rank, int address, int shift_0101, int modules, int width);
uint32_t qcs_check_if_works_RAMBUS_QUIRK(int channel, int rank, int address, int shift_0101, int modules, int width);

void enter_dcatm(int channel, int rank);
void exit_dcatm(int channel, int rank);
int dca_check_if_works_ddr(int channel, int rank, int address, int shift_back);
int dca_check_if_works_ddr_MONTAGE_QUIRK(int channel, int rank, int address, int shift_back);
int dca_check_if_works_sdr(int channel, int rank, int address, int shift_back);

void qca_inc(int channel, int rank, int address);
void qca_rst(int channel, int rank, int address);
void enter_qcatm(int channel, int rank);
void exit_qcatm(int channel, int rank);
int qca_check_if_works(int channel, int rank, int _address, int shift_back);

#endif // SDRAM_PHY_DDR5

#endif // CSR_SDRAM_BASE

#endif // LIBLITEDRAM_DDR5_HELPERS_H
