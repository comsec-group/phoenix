#ifndef LIBLITEDRAM_LPDDR5_TRAINING_H
#define LIBLITEDRAM_LPDDR5_TRAINING_H

#include <generated/csr.h>
#ifdef CSR_SDRAM_BASE
#include <generated/sdram_phy.h>

#ifdef SDRAM_PHY_LPDDR5
#include <liblitedram/lpddr5_helpers.h>


typedef void (*action_callback_t)(int address);

typedef struct {
//    struct {
//        action_callback_t rst_dly;
//        action_callback_t inc_dly;
//    } ck;
    int die_width;
    int max_delay_taps;
    int modules;
} training_ctx_t;

#define DEFAULT_HOST_DRAM {                   \
                                              \
    .die_width = SDRAM_PHY_DQ_DQS_RATIO,      \
    .max_delay_taps = SDRAM_PHY_DELAYS,       \
    .modules = SDRAM_PHY_MODULES,             \
}

/*
    .ca = {                                   \
        .rst_dly = ca_rst,                    \
        .inc_dly = ca_inc,                    \
    },                                        \
*/
extern training_ctx_t host_dram_ctx;

void sdram_lpddr5_flow(void);

#endif // SDRAM_PHY_LPDDR5

#endif // CSR_SDRAM_BASE

#endif // LIBLITEDRAM_DDR5_TRAINING_H
