#ifndef LIBLITEDRAM_DDR5_TRAINING_H
#define LIBLITEDRAM_DDR5_TRAINING_H

#include <generated/csr.h>
#ifdef CSR_SDRAM_BASE
#include <generated/sdram_phy.h>

#ifdef SDRAM_PHY_DDR5
#include <liblitedram/ddr5_helpers.h>

// DRAM Mode Registers Definitions
#define DRAM_SCRATCH_PAD 63

// max CL is 66 (JESD79-5A 3.5.2)
// if in 2N Mode, 1 more cycle is used for the command
#define MAX_READ_CYCLE_DELAY (66 + 1)

// as per spec, WL = RL - 2 (JESD79-5A 3.5.2 NOTE 2)
#define MAX_WRITE_CYCLE_DELAY (MAX_READ_CYCLE_DELAY - 2)

typedef void (*action_callback_t)(int channel, int rank, int address);
typedef void (*training_mode_callback_t)(int channel, int rank);

typedef uint32_t (*delay_checker_cs_t)(int channel, int rank, int address, int shift_0101, int modules, int width);
typedef int (*delay_checker_ca_t)(int channel, int rank, int address, int shift_back);

typedef struct {
    struct {
        action_callback_t rst_dly;
        action_callback_t inc_dly;
    } ck;
    struct {
        int delays[CHANNELS][2][2];
        int coarse_delays[CHANNELS][2];
        int final_delays[CHANNELS][2];

        training_mode_callback_t enter_training_mode;
        training_mode_callback_t exit_training_mode;

        action_callback_t rst_dly;
        action_callback_t inc_dly;

        delay_checker_cs_t check;
        uint8_t invert[CHANNELS];
    } cs;
    struct {
        int line_count;

        int delays[CHANNELS][14][2];
        int final_delays[CHANNELS][14];
        // If per-rank timings are available, the arrays above should be [CHANNELS][SDRAM_PHY_RANKS][14][2]
        // to cover clock/ca delays per rank

        training_mode_callback_t enter_training_mode;
        training_mode_callback_t exit_training_mode;

        action_callback_t rst_dly;
        action_callback_t inc_dly;

        delay_checker_ca_t check;

        int (*has_line13)(int32_t channel, int32_t rank);
    } ca;
    struct {
        int delays[CHANNELS][2];
        int final_delays[CHANNELS];

        action_callback_t rst_dly;
        action_callback_t inc_dly;
    } par;
    enum {
        HOST_DRAM,
        HOST_RCD,
        RCD_DRAM,
        TRAINING_TYPE_COUNT,
    } training_type;
    enum dca_rate rate;
    int ranks;
    int channels;
    int all_ca_count;
    int die_width;
    int max_delay_taps;
    int modules;
    bool CS_CA_successful;
    bool RDIMM;
    uint16_t manufacturer;
    uint8_t device_type;
    uint8_t device_rev;
} training_ctx_t;

// So far, all PHYs have support for single delay far all ranks,
// use only first rank, leave all other as inactive.
// Use SDRAM_PHY_RANKS if we ever support multiple ranks
// and independent timing for them.

// should be populated from SPD
// defualts to dq_dqs_ratio from sdram_phy.h

#define DEFAULT_HOST_DRAM {                   \
    .ck = {                                   \
        .rst_dly = ck_rst,                    \
        .inc_dly = ck_inc,                    \
    },                                        \
    .cs = {                                   \
        .enter_training_mode = enter_cstm,    \
        .exit_training_mode  = exit_cstm,     \
        .rst_dly = cs_rst,                    \
        .inc_dly = cs_inc,                    \
        .check = cs_check_if_works,           \
    },                                        \
    .ca = {                                   \
        .line_count = 13,                     \
        .enter_training_mode = enter_catm,    \
        .exit_training_mode  = exit_catm,     \
        .inc_dly = ca_inc,                    \
        .rst_dly = ca_rst,                    \
        .check = ca_check_if_works,           \
        .has_line13 = check_ca_13th_line,     \
    },                                        \
    .training_type = HOST_DRAM,               \
                                              \
    .ranks = 1,                               \
    .channels = CHANNELS,                     \
    .all_ca_count = SDRAM_PHY_ADDRESS_LINES,  \
    .die_width = SDRAM_PHY_DQ_DQS_RATIO,      \
    .rate = DDR,                              \
    .CS_CA_successful = true,                 \
    .max_delay_taps = SDRAM_PHY_DELAYS,       \
    .modules = SDRAM_PHY_MODULES/CHANNELS,    \
    .RDIMM = false,                           \
    .manufacturer = 0,                        \
}

// die_width must be populated from SPD
// has_line13 = NULL, RCD has always 7 DCA lines

#define DEFAULT_HOST_RCD {                   \
    .ck = {                                  \
        .rst_dly = ck_rst,                   \
        .inc_dly = ck_inc,                   \
    },                                       \
    .cs = {                                  \
        .enter_training_mode = enter_dcstm,  \
        .exit_training_mode  = exit_dcstm,   \
        .rst_dly = cs_rst,                   \
        .inc_dly = cs_inc,                   \
        .check = dcs_check_if_works,         \
    },                                       \
    .ca = {                                  \
        .line_count = 7,                     \
        .enter_training_mode = enter_dcatm,  \
        .exit_training_mode  = exit_dcatm,   \
        .inc_dly = ca_inc,                   \
        .rst_dly = ca_rst,                   \
        .check = dca_check_if_works_ddr,     \
        .has_line13 = NULL,                  \
    },                                       \
    .par = {                                 \
        .rst_dly = par_rst,                  \
        .inc_dly = par_inc,                  \
    },                                       \
    .training_type = HOST_RCD,               \
                                             \
    .ranks = 2,                              \
    .channels = 2,                           \
    .all_ca_count = SDRAM_PHY_ADDRESS_LINES, \
    .die_width = -1,                         \
    .rate = DDR,                             \
    .CS_CA_successful = true,                \
    .max_delay_taps = SDRAM_PHY_DELAYS,      \
    .modules = 1,                            \
    .RDIMM = true,                           \
    .manufacturer = 0,                       \
}

#define DEFAULT_RCD_DRAM {                  \
    .ck = {                                 \
        .rst_dly = qck_rst,                 \
        .inc_dly = qck_inc,                 \
    },                                      \
    .cs = {                                 \
        .enter_training_mode = enter_qcstm, \
        .exit_training_mode  = exit_qcstm,  \
        .rst_dly = qcs_rst,                 \
        .inc_dly = qcs_inc,                 \
        .check = qcs_check_if_works,        \
    },                                      \
    .ca = {                                 \
        .line_count = 1,                    \
        .enter_training_mode = enter_qcatm, \
        .exit_training_mode  = exit_qcatm,  \
        .inc_dly = qca_inc,                 \
        .rst_dly = qca_rst,                 \
        .check = qca_check_if_works,        \
        .has_line13 = NULL,                 \
    },                                      \
    .training_type = RCD_DRAM,              \
                                            \
    .ranks = 2,                             \
    .channels = 2,                          \
    .all_ca_count = -1,                     \
    .die_width = -1,                        \
    .rate = DDR,                            \
    .CS_CA_successful = true,               \
    .max_delay_taps = 64,                   \
    .modules = SDRAM_PHY_MODULES/CHANNELS,  \
    .RDIMM = true,                          \
    .manufacturer = 0,                      \
}


bool sdram_ddr5_read_training(training_ctx_t *ctx);
bool sdram_ddr5_write_training(training_ctx_t *ctx);

extern training_ctx_t host_dram_ctx;
#if defined(CONFIG_HAS_I2C)
extern training_ctx_t host_rcd_ctx;
#endif // defined(CONFIG_HAS_I2C)

void sdram_ddr5_flow(void);

#endif // SDRAM_PHY_DDR5

#endif // CSR_SDRAM_BASE

#endif // LIBLITEDRAM_DDR5_TRAINING_H
