// SPDX-License-Identifier: BSD-Source-Code

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <libbase/memtest.h>

#include <generated/soc.h>
#include <generated/csr.h>
#include <generated/mem.h>
#if defined(CSR_SDRAM_BASE)
#include <generated/sdram_phy.h>
#endif // defined(CSR_SDRAM_BASE)
#include <libbase/i2c.h>

#include <liblitedram/sdram.h>
#include <liblitedram/sdram_spd.h>
#include <liblitedram/sdram_rcd.h>
#include <liblitedram/bist.h>
#include <liblitedram/accessors.h>

#include "../command.h"
#include "../helpers.h"

/**
 * Command "sdram_bist"
 *
 * Run SDRAM Build-In Self-Test
 *
 */
#if defined(CSR_SDRAM_GENERATOR_BASE) && defined(CSR_SDRAM_CHECKER_BASE)
static void sdram_bist_handler(int nb_params, char **params)
{
	char *c;
	int burst_length;
	int random;
	if (nb_params < 2) {
		printf("sdram_bist <burst_length> <random>");
		return;
	}
	burst_length = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect burst_length");
		return;
	}
	random = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect random");
		return;
	}
	sdram_bist(burst_length, random);
}
define_command(sdram_bist, sdram_bist_handler, "Run SDRAM Build-In Self-Test", LITEDRAM_CMDS);
#endif

/**
 * Command "sdram_hw_test"
 *
 * Run SDRAM HW-accelerated memtest
 *
 */
#if defined(CSR_SDRAM_GENERATOR_BASE) && defined(CSR_SDRAM_CHECKER_BASE)
static void sdram_hw_test_handler(int nb_params, char **params)
{
	char *c;
	uint64_t origin;
	uint64_t size;
	uint64_t burst_length = 1;
	if (nb_params < 2) {
		printf("sdram_hw_test <origin> <size> [<burst_length>]");
		return;
	}
	origin = strtoull(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect origin");
		return;
	}
	size = strtoull(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect size");
		return;
	}
	if (nb_params > 2) {
		burst_length = strtoull(params[2], &c, 0);
		if (*c != 0) {
			printf("Incorrect burst length");
			return;
		}
	}
	int errors = sdram_hw_test(origin, size, burst_length);
	printf("%d errors found\n", errors);
}
define_command(sdram_hw_test, sdram_hw_test_handler, "Run SDRAM HW-accelerated memtest", LITEDRAM_CMDS);
#endif

#ifdef CSR_DDRPHY_RDPHASE_ADDR
/**
 * Command "sdram_force_rdphase"
 *
 * Force read phase
 *
 */
static void sdram_force_rdphase_handler(int nb_params, char **params)
{
	char *c;
	int phase;
	if (nb_params < 1) {
		printf("sdram_force_rdphase <phase>");
		return;
	}
	phase = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect phase");
		return;
	}
	printf("Forcing read phase to %d\n", phase);
	ddrphy_rdphase_write(phase);
}
define_command(sdram_force_rdphase, sdram_force_rdphase_handler, "Force read phase", LITEDRAM_CMDS);
#endif

#ifdef CSR_DDRPHY_WRPHASE_ADDR
/**
 * Command "sdram_force_wrphase"
 *
 * Force write phase
 *
 */
static void sdram_force_wrphase_handler(int nb_params, char **params)
{
	char *c;
	int phase;
	if (nb_params < 1) {
		printf("sdram_force_wrphase <phase>");
		return;
	}
	phase = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect phase");
		return;
	}
	printf("Forcing write phase to %d\n", phase);
	ddrphy_wrphase_write(phase);
}
define_command(sdram_force_wrphase, sdram_force_wrphase_handler, "Force write phase", LITEDRAM_CMDS);
#endif

#ifdef CSR_DDRPHY_CDLY_RST_ADDR

/**
 * Command "sdram_rst_cmd_delay"
 *
 * Reset write leveling Cmd delay
 *
 */
#if defined(CSR_SDRAM_BASE) && defined(CSR_DDRPHY_BASE)
static void sdram_rst_cmd_delay_handler(int nb_params, char **params)
{
	sdram_software_control_on();
	sdram_write_leveling_rst_cmd_delay(1);
	sdram_software_control_off();
}
define_command(sdram_rst_cmd_delay, sdram_rst_cmd_delay_handler, "Reset write leveling Cmd delay", LITEDRAM_CMDS);
#endif

/**
 * Command "sdram_force_cmd_delay"
 *
 * Force write leveling Cmd delay
 *
 */
#if defined(CSR_SDRAM_BASE) && defined(CSR_DDRPHY_BASE)
static void sdram_force_cmd_delay_handler(int nb_params, char **params)
{
	char *c;
	int taps;
	if (nb_params < 1) {
		printf("sdram_force_cmd_delay <taps>");
		return;
	}
	taps = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect taps");
		return;
	}
	sdram_software_control_on();
	sdram_write_leveling_force_cmd_delay(taps, 1);
	sdram_software_control_off();
}
define_command(sdram_force_cmd_delay, sdram_force_cmd_delay_handler, "Force write leveling Cmd delay", LITEDRAM_CMDS);
#endif

#endif

#if defined(CSR_SDRAM_BASE)
/**
 * Command "sdram_init"
 *
 * Initialize SDRAM (Init + Calibration)
 *
 */
define_command(sdram_init, sdram_init, "Initialize SDRAM (Init + Calibration)", LITEDRAM_CMDS);

/**
 * Command "sdram_test"
 *
 * Test SDRAM
 *
 */
static void sdram_test_handler(int nb_params, char **params)
{
	memtest((unsigned int *)MAIN_RAM_BASE, MAIN_RAM_SIZE/32);
}
define_command(sdram_test, sdram_test_handler, "Test SDRAM", LITEDRAM_CMDS);

/**
 * Command "sdram_cal"
 *
 * Calibrate SDRAM
 *
 */
#if defined(CSR_DDRPHY_BASE)
static void sdram_cal_handler(int nb_params, char **params)
{
	sdram_software_control_on();
	sdram_leveling();
	sdram_software_control_off();
}
define_command(sdram_cal, sdram_cal_handler, "Calibrate SDRAM", LITEDRAM_CMDS);
#endif

#ifdef SDRAM_PHY_WRITE_LEVELING_CAPABLE

/**
 * Command "sdram_rst_dat_delay"
 *
 * Reset write leveling Dat delay
 *
 */
#if defined(CSR_DDRPHY_BASE)
static void sdram_rst_dat_delay_handler(int nb_params, char **params)
{
	char *c;
	int module;
	if (nb_params < 1) {
		printf("sdram_rst_dat_delay <module>");
		return;
	}
	module = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect module");
		return;
	}
	sdram_software_control_on();
	sdram_write_leveling_rst_dat_delay(module, 1);
	sdram_software_control_off();
}
define_command(sdram_rst_dat_delay, sdram_rst_dat_delay_handler, "Reset write leveling Dat delay", LITEDRAM_CMDS);
#endif

/**
 * Command "sdram_force_dat_delay"
 *
 * Force write leveling Dat delay
 *
 */
#if defined(CSR_DDRPHY_BASE)
static void sdram_force_dat_delay_handler(int nb_params, char **params)
{
	char *c;
	int module;
	int taps;
	if (nb_params < 2) {
		printf("sdram_force_dat_delay <module> <taps>");
		return;
	}
	module = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect module");
		return;
	}
	taps = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect taps");
		return;
	}
	sdram_software_control_on();
	sdram_write_leveling_force_dat_delay(module, taps, 1);
	sdram_software_control_off();
}
define_command(sdram_force_dat_delay, sdram_force_dat_delay_handler, "Force write leveling Dat delay", LITEDRAM_CMDS);
#endif /* defined(CSR_SDRAM_BASE) && defined(CSR_DDRPHY_BASE) */

#endif /* SDRAM_PHY_WRITE_LEVELING_CAPABLE */

#if defined(SDRAM_PHY_BITSLIPS) && defined(SDRAM_PHY_WRITE_LEVELING_CAPABLE)
/**
 * Command "sdram_rst_bitslip"
 *
 * Reset write leveling Bitslip
 *
 */
#if defined(CSR_DDRPHY_BASE)
static void sdram_rst_bitslip_handler(int nb_params, char **params)
{
	char *c;
	int module;
	if (nb_params < 1) {
		printf("sdram_rst_bitslip <module>");
		return;
	}
	module = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect module");
		return;
	}
	sdram_software_control_on();
	sdram_write_leveling_rst_bitslip(module, 1);
	sdram_software_control_off();
}
define_command(sdram_rst_bitslip, sdram_rst_bitslip_handler, "Reset write leveling Bitslip", LITEDRAM_CMDS);
#endif

/**
 * Command "sdram_force_bitslip"
 *
 * Force write leveling Bitslip
 *
 */
#if defined(CSR_DDRPHY_BASE)
static void sdram_force_bitslip_handler(int nb_params, char **params)
{
	char *c;
	int module;
	int bitslip;
	if (nb_params < 2) {
		printf("sdram_force_bitslip <module> <bitslip>");
		return;
	}
	module = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect module");
		return;
	}
	bitslip = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect bitslip");
		return;
	}
	sdram_software_control_on();
	sdram_write_leveling_force_bitslip(module, bitslip, 1);
	sdram_software_control_off();
}
define_command(sdram_force_bitslip, sdram_force_bitslip_handler, "Force write leveling Bitslip", LITEDRAM_CMDS);
#endif

#endif /* defined(SDRAM_PHY_BITSLIPS) && defined(SDRAM_PHY_WRITE_LEVELING_CAPABLE) */

/**
 * Command "sdram_mr_write"
 *
 * Write SDRAM Mode Register
 *
 */
static void sdram_mr_write_handler(int nb_params, char **params)
{
	char *c;
	uint8_t reg;
	uint16_t value;

	if (nb_params < 2) {
		printf("sdram_mr_write <reg> <value>");
		return;
	}
	reg = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect reg");
		return;
	}
	value = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect value");
		return;
	}
	sdram_software_control_on();
	printf("Writing 0x%04x to MR%d\n", value, reg);
	sdram_mode_register_write(reg, value);
	sdram_software_control_off();
}
define_command(sdram_mr_write, sdram_mr_write_handler, "Write SDRAM Mode Register", LITEDRAM_CMDS);

#if defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_LPDDR5)
/**
 * Command "sdram_mr_read"
 *
 * Read SDRAM Mode Register (only DDR5)
 *
 */
static void sdram_mr_read_handler(int nb_params, char **params)
{
	char *c;
	uint8_t channel;
	uint8_t device;
	uint8_t reg;

	if (nb_params < 3) {
		printf("sdram_mr_read <channel> <device> <reg>");
		return;
	}

	channel = strtoul(params[0], &c, 0);
	if (*c != 0 || channel > 1) {
		printf("Incorrect channel");
		return;
	}

	device = strtoul(params[1], &c, 0);
	if (*c != 0 || device == 15) {
		printf("Incorrect device");
		return;
	}

	reg = strtoul(params[2], &c, 0);
	if (*c != 0) {
		printf("Incorrect reg");
		return;
	}
	sdram_software_control_on();
	printf("Reading from channel:%d device:%d MR%d\n", channel, device, reg);
	#ifdef SDRAM_PHY_DDR5
		printf("Value:%02x\n", sdram_mode_register_read(channel, device, reg));
	#else
		printf("Value:%02x\n", sdram_mode_register_read(reg));
	#endif
	// sdram_software_control_off();
}
define_command(sdram_mr_read, sdram_mr_read_handler, "Read SDRAM Mode Register", LITEDRAM_CMDS);
#endif // defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_LPDDR5)

#if defined(SDRAM_PHY_LPDDR5)
#include <liblitedram/lpddr5_helpers.h>
/**
 * Command "sdram_read"
 *
 * Read SDRAM (only LPDDR5)
 *
 */
static void sdram_read_handler(int nb_params, char **params)
{
	char *c;
	uint8_t bank;
	uint16_t row;
	uint8_t column;

	if (nb_params < 3) {
		printf("sdram_read <bank> <row> <column>");
		return;
	}

	bank = strtoul(params[0], &c, 0);
	if (*c != 0 || bank > 15) {
		printf("Incorrect bank");
		return;
	}

	row = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect row");
		return;
	}

	column = strtoul(params[2], &c, 0);
	if (*c != 0 || column > 63) {
		printf("Incorrect device");
		return;
	}

	sdram_software_control_on();
	printf("Reading from bank:%d row:%"PRId16" column:%d\n", bank, row, column);
	sdram_read(bank, row, column);
	sdram_software_control_off();
}
define_command(sdram_read, sdram_read_handler, "Read SDRAM", LITEDRAM_CMDS);

/**
 * Command "sdram_write"
 *
 * Write SDRAM (only LPDDR5)
 *
 */
static void sdram_write_handler(int nb_params, char **params)
{
	char *c;
	uint8_t bank;
	uint16_t row;
	uint8_t column;
	uint8_t value;

	if (nb_params < 4) {
		printf("sdram_write <bank> <row> <column> <value>");
		return;
	}

	bank = strtoul(params[0], &c, 0);
	if (*c != 0 || bank > 15) {
		printf("Incorrect bank");
		return;
	}

	row = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect row");
		return;
	}

	column = strtoul(params[2], &c, 0);
	if (*c != 0 || column > 63) {
		printf("Incorrect device");
		return;
	}

	value = strtoul(params[3], &c, 0);

	sdram_software_control_on();
	printf("Writing to bank:%d row:%"PRId16" column:%d value:%d\n", bank, row, column, value);
	sdram_write(bank, row, column, value);
	sdram_software_control_off();
}
define_command(sdram_write, sdram_write_handler, "Write SDRAM", LITEDRAM_CMDS);
#endif // defined(SDRAM_PHY_LPDDR5)

#endif /* CSR_SDRAM_BASE */

/**
 * Command "sdram_spd"
 *
 * Read contents of SPD EEPROM memory.
 * SPD address is a 3-bit address defined by the pins A0, A1, A2.
 *
 */
#if defined(CSR_SDRAM_BASE) && defined(CONFIG_HAS_I2C)
static void sdram_spd_handler(int nb_params, char **params)
{
	char *c;
	unsigned char spdaddr;
	unsigned char buf[SDRAM_SPD_SIZE];
	int len = sizeof(buf);
	bool send_stop = true;

	if (nb_params < 1) {
		printf("sdram_spd <spdaddr> [<send_stop>]");
		return;
	}

	spdaddr = strtoul(params[0], &c, 0);
	if (*c != 0) {
		printf("Incorrect address");
		return;
	}
	if (spdaddr > 0b111) {
		printf("SPD EEPROM max address is 0b111 (defined by A0, A1, A2 pins)");
		return;
	}

	if (nb_params > 1) {
		send_stop = strtoul(params[1], &c, 0) != 0;
		if (*c != 0) {
			printf("Incorrect send_stop value");
			return;
		}
	}

	if (!sdram_read_spd(spdaddr, 0, buf, (uint16_t)len, send_stop)) {
		printf("Error when reading SPD EEPROM");
		return;
	}

	dump_bytes((unsigned int *) buf, len, 0);

#ifdef SPD_BASE
	{
		int cmp_result;
		cmp_result = memcmp(buf, (void *) SPD_BASE, SPD_SIZE);
		if (cmp_result == 0) {
			printf("Memory contents matches the data used for gateware generation\n");
		} else {
			printf("\nWARNING: memory differs from the data used during gateware generation:\n");
			dump_bytes((void *) SPD_BASE, SPD_SIZE, 0);
		}
	}
#endif
}
define_command(sdram_spd, sdram_spd_handler, "Read SDRAM SPD EEPROM", LITEDRAM_CMDS);
#endif /* defined(CSR_SDRAM_BASE) && defined(CONFIG_HAS_I2C) */

#if defined(CONFIG_HAS_I2C) && (defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_DDR4_RDIMM))
#define EXTRACT_BYTE(data, i)	(((data) & (0xff << ((i) * 8))) >> ((i) * 8))

/**
 * Command "sdram_rcd_read_dword"
 *
 * Read from SDRAM RCD
 *
 */
static void sdram_rcd_read_handler(int nb_params, char **params)
{
	char *c;
	uint8_t rcd = 0;
	uint8_t reg_num = 0;
	uint8_t page_num = 0;
	uint8_t function = 0;
	bool byte_read = false;

	if (nb_params < 3) {
		printf("sdram_rcd_read <rcd> <page_num> <reg_num> [<function>] [<byte_read>]");
		return;
	}

	rcd = strtoul(params[0], &c, 0);
	if (*c != 0 || rcd > 7) {
		printf("Incorrect RCD number");
		return;
	}

	page_num = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect page number");
		return;
	}

	reg_num = strtoul(params[2], &c, 0);
	if (*c != 0) {
		printf("Incorrect register number");
		return;
	}

	if (nb_params > 3) {
		function = strtoul(params[3], &c, 0);
		if (*c != 0) {
			printf("Incorrect function");
			return;
		}
	}

	if (nb_params > 4) {
		byte_read = strtoul(params[4], &c, 0);
		if (*c != 0) {
			printf("Incorrect byte_read value");
			return;
		}
	}

	uint8_t data[5];
	if (!sdram_rcd_read(rcd, 0, function, page_num, reg_num, data, byte_read)) {
		printf("NACK received");
		return;
	}

	uint8_t status = data[4];
	if (!(status & 0x01))
		printf("Status byte reported operation not successful\n");

	if (status & 0x10)
		printf("Status byte reported internal target abort\n");

	reg_num &= 0xfffffffc; // reads are aligned to 4 bytes
	printf("Page: 0x%02x\n", page_num);
	for (int i = 0; i < 4; i++) {
		printf("RW%02X: 0x%02x\n", reg_num + i, data[i]);
	}
}
define_command(sdram_rcd_read, sdram_rcd_read_handler, "Read from SDRAM RCD", LITEDRAM_CMDS);

/**
 * Command "sdram_rcd_write"
 *
 * Write to SDRAM RCD
 *
 */
static void sdram_rcd_write_handler(int nb_params, char **params)
{
	char *c;
	uint8_t rcd = 0;
	uint8_t reg_num = 0;
	uint8_t page_num = 0;
	uint32_t data = 0;
	uint8_t size = 0;
	uint8_t function = 0;
	bool byte_write = false;

	if (nb_params < 5) {
		printf("sdram_rcd_write <rcd> <page_num> <reg_num> <data> <size> [<function>] [<byte_write>]");
		return;
	}

	rcd = strtoul(params[0], &c, 0);
	if (*c != 0 || rcd > 7) {
		printf("Incorrect RCD number");
		return;
	}

	page_num = strtoul(params[1], &c, 0);
	if (*c != 0) {
		printf("Incorrect page number");
		return;
	}

	reg_num = strtoul(params[2], &c, 0);
	if (*c != 0) {
		printf("Incorrect register number");
		return;
	}

	data = strtoul(params[3], &c, 0);
	if (*c != 0) {
		printf("Incorrect data value");
		return;
	}

	size = strtoul(params[4], &c, 0);
	if (*c != 0 || (size != 1 && size != 2 && size != 4)) {
		printf("Incorrect size");
		return;
	}

	if (nb_params > 5) {
		function = strtoul(params[5], &c, 0);
		if (*c != 0) {
			printf("Incorrect function");
			return;
		}
	}

	if (nb_params > 6) {
		byte_write = strtoul(params[6], &c, 0);
		if (*c != 0) {
			printf("Incorrect byte_write value");
			return;
		}
	}

	const uint8_t data_array[4] = {
		EXTRACT_BYTE(data, 0),
		EXTRACT_BYTE(data, 1),
		EXTRACT_BYTE(data, 2),
		EXTRACT_BYTE(data, 3),
	};

	if (!sdram_rcd_write(rcd, 0, function, page_num, reg_num, data_array, size, byte_write)) {
		printf("NACK received");
		return;
	}
}
define_command(sdram_rcd_write, sdram_rcd_write_handler, "Write to SDRAM RCD", LITEDRAM_CMDS);
#endif /* defined(CONFIG_HAS_I2C) && (defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_DDR4_RDIMM)) */

#ifdef SDRAM_DEBUG
define_command(sdram_debug, sdram_debug, "Run SDRAM debug tests", LITEDRAM_CMDS);
#endif
