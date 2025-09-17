// This file is Copyright (c) 2023 Antmicro <www.antmicro.com>
// License: BSD

#define I2C_FREQ_HZ 200000
#include <libbase/i2c.h>
#include <liblitedram/sdram_rcd.h>

#if defined(CSR_SDRAM_BASE) && defined(CONFIG_HAS_I2C)

#include <generated/sdram_phy.h>

#if defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_DDR4_RDIMM)

static uint8_t pec_calc(uint8_t pec, uint8_t *buf, uint8_t len) {
    uint16_t inter = 0;
    for (int i=0; i<len; ++i) {
        inter = (pec ^ buf[i]) << 8;
        for (int j=0; j<8; ++j) {
            if (inter & 0x8000)
                inter ^= 0x8380;
            inter = inter << 1;
        }
        pec = inter >> 8;
    }
    return pec;
}

#ifdef SDRAM_PHY_DDR5SIMPHY
bool sdram_rcd_read(uint8_t rcd, uint8_t dev, uint8_t function, uint8_t page_num, uint8_t reg_num, uint8_t *data, bool byte_read) {
	for (int i = 0; i < 4; i++) {
		// Right now reading RCD in simulation is not supported
		data[i] = 0;
	}

	data[4] = 0x01; // simulate successful reads, set status to 1

	return true;
}

bool sdram_rcd_write(uint8_t rcd, uint8_t dev, uint8_t function, uint8_t page_num, uint8_t reg_num, const uint8_t *data, uint8_t size, bool byte_write) {
	i2cmockmaster_internal_channel_write(function);
	i2cmockmaster_internal_page_num_write(page_num);

	for (int i = 0; i < size; i++) {
		i2cmockmaster_internal_reg_num_write(reg_num + i);
		i2cmockmaster_internal_data_write(data[i]);
		i2cmockmaster_internal_execute_write(0);
	}

	return true;
}
#else
static bool sdram_rcd_byte_read(uint8_t rcd, const uint8_t *rap_buf, uint8_t len, uint8_t *data, uint8_t internal_cmd) {
	bool ok = true;
	uint8_t sidebus_cmd = 0x00 | ((internal_cmd & 0b11) << 2); // | ((pec_en & 0b1) << 4);

	ok &= i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd | 0x80, &rap_buf[0], 1, 1); // start bit set
	ok &= i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd,        &rap_buf[1], 1, 1);
	ok &= i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd,        &rap_buf[2], 1, 1);
	ok &= i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd | 0x40, &rap_buf[3], 1, 1); // end bit set

	ok &= i2c_read(RCD_RW_ADDR(rcd), sidebus_cmd | 0x80, &data[4], 1, false, 1); // start bit set
	ok &= i2c_read(RCD_RW_ADDR(rcd), sidebus_cmd,        &data[3], 1, false, 1);
	ok &= i2c_read(RCD_RW_ADDR(rcd), sidebus_cmd,        &data[2], 1, false, 1);
	ok &= i2c_read(RCD_RW_ADDR(rcd), sidebus_cmd,        &data[1], 1, false, 1);
	ok &= i2c_read(RCD_RW_ADDR(rcd), sidebus_cmd | 0x40, &data[0], 1, false, 1); // end bit set

	return ok;
}

static bool sdram_rcd_block_read(uint8_t rcd, const uint8_t *rap_buf, uint8_t len, uint8_t *data, uint8_t internal_cmd) {
	uint8_t buf[
		  1 // 1 byte for count
		+ 4 // 4 bytes for register addressing
		+ 1 // 1 byte for status from read
		+ 1 // optional PEC
	]; // total 7 bytes using PEC

	buf[0] = len;
	for (int i = 0; i < len; i++)
		buf[1 + i] = rap_buf[i];

	uint8_t addr = 0x5f << 1;
	uint8_t pec = pec_calc(0, &addr, 1);
	uint8_t sidebus_cmd = 0xd2 | ((internal_cmd & 0b11) << 2);

	pec = pec_calc(pec, &sidebus_cmd, 1);
	buf[len+1] = pec_calc(pec, buf, len+1);

	bool ok = i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd, buf, sizeof(buf) - 1, 1); // -1 because no status byte
	ok &= i2c_read(RCD_RW_ADDR(rcd), sidebus_cmd, buf, (1 + 1 + 4 + 1), false, 1);  // byte count + status + data + PEC

	// copy status + data, ignore length
	data[4] = buf[1]; // status
	for (int i = 0; i < 4; i++) // DWORD
		data[3 - i] = buf[2 + i];

	return ok;
}

static bool sdram_rcd_byte_write(uint8_t rcd, const uint8_t *rap_buf, uint8_t len, uint8_t internal_cmd) {
	bool ok = true;
	uint8_t sidebus_cmd = 0x00 | ((internal_cmd & 0b11) << 2); // | ((pec_en & 0b1) << 4);

	ok &= i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd | 0x80, &rap_buf[0], 1, 1); // start bit set
	for (int i = 1; i < len; i++) {
		if (i == len - 1)
			sidebus_cmd = sidebus_cmd | 0x40; // end bit set

		ok &= i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd, &rap_buf[i], 1, 1);
	}

	return ok;
}

static bool sdram_rcd_block_write(uint8_t rcd, const uint8_t *rap_buf, uint8_t len, uint8_t internal_cmd) {
	uint8_t buf[
		  1 // 1 byte for count
		+ 4 // 4 bytes for register addressing
		+ 4 // at most 4 bytes of data
		+ 1 // optional PEC
	]; // total 10 bytes using PEC

	buf[0] = len;
	for (int i = 0; i < len; i++)
		buf[1 + i] = rap_buf[i];

	uint8_t addr = 0x5f << 1;
	uint8_t pec = pec_calc(0, &addr, 1);
	uint8_t sidebus_cmd = 0xd2 | ((internal_cmd & 0b11) << 2);

	pec = pec_calc(pec, &sidebus_cmd, 1);
	buf[len+1] = pec_calc(pec, buf, len+1);

	return i2c_write(RCD_RW_ADDR(rcd), sidebus_cmd, buf, (1 + len + 1), 1);
}

/**
 * sdram_rcd_read
 *
 * Reads one DWORD from the selected RCD.
 * `dev` parameter is unused as it is reserved.
 * For DDR5 RDIMMs, `function` selects channel (0: A, 1: B)
 * For DDR5 RDIMMs, parameter `address` is a `page_num` concatenated with a `reg_num`.
 * It also automatically adds 0x60 to the `reg_num` part if the `page_num != 0`.
 * `data` should be a pointer to 5 a byte array (status + DWORD)
 * `byte_read` selects between byte and block operation.
 */
bool sdram_rcd_read(uint8_t rcd, uint8_t dev, uint8_t function, uint8_t page_num, uint8_t reg_num, uint8_t *data, bool byte_read) {
	uint8_t rap_buf[4] = { // Register Access Protocol
		0x00,                     // reserved
		(dev << 4) | (function),  // device | function
		page_num,                 // page number
		reg_num                   // register number
	};

	bool ok = true;

	for (int i = 0; i < 1; i++) {
		if (byte_read)
			ok &= sdram_rcd_byte_read(rcd, rap_buf, sizeof(rap_buf), data, RCD_READ_CMD);
		else
			ok &= sdram_rcd_block_read(rcd, rap_buf, sizeof(rap_buf), data, RCD_READ_CMD);
	}

	return ok;
}

/**
 * sdram_rcd_write
 *
 * Writes `size` bytes to the selected RCD.
 * `dev` parameter is unused as it is reserved.
 * For DDR5 RDIMMs, `function` selects channel (0: A, 1: B)
 * For DDR5 RDIMMs, parameter `address` is a `page_num` concatenated with a `reg_num`.
 * It also automatically adds 0x60 to the `reg_num` part if the `page_num != 0`.
 * `data` should be a pointer to at least `size` byte array.
 * How many bytes will be written depends on the `size` parameter.
 * `byte_write` selects between byte and block operation.
 */
bool sdram_rcd_write(uint8_t rcd, uint8_t dev, uint8_t function, uint8_t page_num, uint8_t reg_num, const uint8_t *data, uint8_t size, bool byte_write) {
	uint8_t rap_buf[4 + 4] = { // Register Access Protocol
		0x00,                     // reserved
		(dev << 4) | (function),  // device | function
		page_num,                 // page number
		reg_num                   // register number
	};

	for (int i = 0; i < size; i++)
		rap_buf[4 + i] = data[size - i - 1];

	bool ok = true;

	for (int i = 0; i < 1; i++) {
		if (byte_write)
			ok &= sdram_rcd_byte_write(rcd, rap_buf, (4 + size), RCD_WRITE_CMD(size));
		else
			ok &= sdram_rcd_block_write(rcd, rap_buf, (4 + size), RCD_WRITE_CMD(size));
	}
	return ok;
}
#endif /* SDRAM_PHY_DDR5SIMPHY */

#endif /* defined(SDRAM_PHY_DDR5) || defined(SDRAM_PHY_DDR4_RDIMM) */

#elif defined(CSR_SDRAM_BASE)

bool sdram_rcd_read(uint8_t rcd, uint8_t dev, uint8_t function,
  uint8_t page_num, uint8_t reg_num, uint8_t *data, bool byte_read) {
    return false;
}
bool sdram_rcd_write(uint8_t rcd, uint8_t dev, uint8_t function,
  uint8_t page_num, uint8_t reg_num, const uint8_t *data, uint8_t size, bool byte_write) {
    return false;
}

#endif /* CSR_SDRAM_BASE && CONFIG_HAS_I2C */
