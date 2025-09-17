#ifndef LIBLITEDRAM_DDR5_DDR5_SPD_PARSE_H
#define LIBLITEDRAM_DDR5_DDR5_SPD_PARSE_H
#include <generated/csr.h>
#ifdef CSR_SDRAM_BASE
#include <generated/sdram_phy.h>

enum module_type {
    RDIMM       = 0b0001,
    UDIMM       = 0b0010,
    SODIMM      = 0b0011,
    LRDIMM      = 0b0100,
    DDIM        = 0b1010,
    SOLDER_DOWN = 0b1011,
};

/**
 * read_module_type
 *
 * Reads the 3rd byte of the SPD and extracts the module type.
 * If the SPD cannot be read, it defaults to the UDIMM.
 */
enum module_type read_module_type(uint8_t spd);

/**
 * read_module_width
 * Reads the 6th byte of the SPD and extracts the primary SDRAM
 * module width. If SPD cannot be read, it defaults to the
 * SDRAM_PHY_DQ_DQS_RATIO.
 */
uint8_t read_module_width(uint8_t spd);

/**
 * read_module_ranks
 * Reads 234h byte of the SPD and extracts number of ranks.
 */
uint8_t read_module_ranks(uint8_t spd);

/**
 * read_module_channels
 * Reads 235th byte of th SPD and extracts DIMM channel count.
 */
uint8_t read_module_channels(uint8_t spd);

/**
 * read_module_rcd_manufacturer
 * Reads 240th and 241th bytes of the SPD and extracts
 * RCD manufacturer.
 */
uint16_t read_module_rcd_manufacturer(uint8_t spd);

/**
 * read_module_rcd_device_type
 * Reads 242th byte of the SPD and returns device type.
 */
uint8_t read_module_rcd_device_type(uint8_t spd);

/**
 * read_module_rcd_device_rev
 * Reads 243th byte of the SPD and returns device revision.
 */
uint8_t read_module_rcd_device_rev(uint8_t spd);

/**
 * read_module_enabled_clock
 * Reads 248th byte of the SPD and parses QCK enabled drivers
 */
uint8_t read_module_enabled_clock(uint8_t spd);

/**
 * read_module_enabled_ca
 * Reads 249th byte of the SPD and parses Qx enabled drivers.
 */
uint8_t read_module_enabled_ca(uint8_t spd);

/**
 * read_module_qck_setup
 * Reads 250th byte of the SPD and pareses QCK driver strengths.
 */
uint8_t read_module_qck_setup(uint8_t spd);

/**
 * read_module_qca_qcs_setup
 * Reads 252th byte of the SPD and pareses QCA and QCS driver strengths.
 */
uint8_t read_module_qca_qcs_setup(uint8_t spd);

/**
 * read_module_slew_rates
 * Reads 254th byte of the SPD and parses QCK, QCA and QCS slew rates.
 */
uint8_t read_module_slew_rates(uint8_t spd);

#endif // CSR_SDRAM_BASE
#endif // LIBLITEDRAM_DDR5_DDR5_SPD_PARSE_H
