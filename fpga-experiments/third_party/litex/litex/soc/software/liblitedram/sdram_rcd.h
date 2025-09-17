// This file is Copyright (c) 2023 Antmicro <www.antmicro.com>
// License: BSD

#ifndef __SDRAM_RCD_H
#define __SDRAM_RCD_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stdint.h>

#include <generated/csr.h>

#if defined(CSR_SDRAM_BASE) && defined(CONFIG_HAS_I2C)

#include <generated/sdram_phy.h>

#if defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_DDR4_RDIMM)

#define RCD_RW_PREAMBLE		0x58
#define RCD_RW_ADDR(a210)	((RCD_RW_PREAMBLE) | ((a210) & 0b111))

#define RCD_READ_CMD		0b00
#define RCD_WRITE_CMD(size)	(((size) >> 1) + 1)

bool sdram_rcd_read(uint8_t rcd, uint8_t dev, uint8_t function,
    uint8_t page_num, uint8_t reg_num, uint8_t *data, bool byte_read);
bool sdram_rcd_write(uint8_t rcd, uint8_t dev, uint8_t function,
    uint8_t page_num, uint8_t reg_num, const uint8_t *data, uint8_t size, bool byte_write);

#endif /* defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_DDR4_RDIMM) */

#elif defined(CSR_SDRAM_BASE)

bool sdram_rcd_read(uint8_t rcd, uint8_t dev, uint8_t function,
  uint8_t page_num, uint8_t reg_num, uint8_t *data, bool byte_read);
bool sdram_rcd_write(uint8_t rcd, uint8_t dev, uint8_t function,
  uint8_t page_num, uint8_t reg_num, const uint8_t *data, uint8_t size, bool byte_write);

#endif /* CSR_SDRAM_BASE && CONFIG_HAS_I2C */

#ifdef __cplusplus
}
#endif

#endif /* __SDRAM_RCD_H */
