#ifndef LIBLITEDRAM_DDR5_HELPERS_H
#define LIBLITEDRAM_DDR5_HELPERS_H

#include <stdbool.h>

#include <generated/csr.h>

#ifdef CSR_SDRAM_BASE
#include <generated/sdram_phy.h>

#ifdef SDRAM_PHY_LPDDR5

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

void rd_rst(uint8_t module);
void rd_inc(uint8_t module);
void idly_rst(uint8_t module);
void idly_inc(uint8_t module);

void wr_rst(uint8_t module);
void wr_inc(uint8_t module);
void odly_rst(uint8_t module);
void odly_inc(uint8_t module);

void enter_CK2WCK_leveling(void);
bool sample_CK2WCK_shift(void);
void exit_CK2WCK_leveling(void);

void send_rdc(void);
int compare_serial(int module, int width,
                   uint16_t data, int inv, int print);

void send_mrw(uint8_t reg, uint8_t val);
void send_mrr(uint8_t reg);
uint8_t recover_mrr_value(uint8_t module, uint8_t width);
void read_registers(int module, int width);

void send_fifo_write(void);
void send_fifo_read(void);
void setup_serial_write_data(uint8_t module, uint8_t width,
                             uint16_t data, int inv, int print);

void sdram_read(uint8_t bank, uint16_t row, uint8_t column);
void sdram_write(uint8_t bank, uint16_t row, uint8_t column, uint8_t value);

#endif // SDRAM_PHY_LPDDR5

#endif // CSR_SDRAM_BASE

#endif // LIBLITEDRAM_DDR5_HELPERS_H
