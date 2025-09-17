#include <liblitedram/ddr5/ddr5_spd_parse.h>

#include <stdbool.h>
#include <inttypes.h>
#include <stdio.h>

#include <liblitedram/sdram_spd.h>
#include <liblitedram/ddr5_helpers.h>

#if defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_DDR5)

enum module_type read_module_type(uint8_t spd) {
#ifdef DDR5_RDIMM_SIM
    return RDIMM;
#endif // DDR5_RDIMM_SIM
    uint8_t module_type;
    if (!sdram_read_spd(spd, 3, &module_type, 1, false)) {
        printf("Couldn't read the SPD and check the module type. Defaulting to UDIMM.\n");
        return UDIMM;
    }

    // Module type is in the lower nibble
    return module_type & 0x0f;
}

uint8_t read_module_width(uint8_t spd) {
    // TODO: change to actual spd data, when PHY will handle variable widths
    return SDRAM_PHY_DQ_DQS_RATIO;
    uint8_t buf;

    // Module width is stored in SPD[6][7:5]
    //     000: x4
    //     001: x8
    //     010: x16
    //     011: x32

    if (!sdram_read_spd(spd, 6, &buf, 1, false)) {
        printf("Couldn't read module width from the SPD, defaulting to x%d.\n", SDRAM_PHY_DQ_DQS_RATIO);
        return SDRAM_PHY_DQ_DQS_RATIO;
    }

    // minimal supported is x4
    uint8_t shift = (buf & 0xe0) >> 5;
    uint8_t module_width = 4 << shift;
    return module_width;
}

uint8_t read_module_ranks(uint8_t spd) {
    uint8_t buf;

    // Module ranks count is stored in SPD[234][5:3]
    //     000: 1
    //     001: 2
    //     010: 3
    //     .
    //     .
    //     .
    //     111: 8

    if (!sdram_read_spd(spd, 234, &buf, 1, false)) {
        printf("Couldn't read module ranks from the SPD, defaulting to x%d.\n", 1);
        return 1;
    }

    // minimal supported is x4
    uint8_t shift = (buf & 0x38) >> 3;
    uint8_t module_ranks = shift + 1;

    return module_ranks;
}

uint8_t read_module_channels(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[235][6:5]
    //     00: 1
    //     01: 2

    if (!sdram_read_spd(spd, 235, &buf, 1, false)) {
        printf("Couldn't read module channels from the SPD, defaulting to x%d.\n", CHANNELS);
        return CHANNELS;
    }

    // minimal supported is x4
    uint8_t shift = (buf & 0x60) >> 5;
    uint8_t module_channels = shift + 1;

    return module_channels;
}


uint16_t read_module_rcd_manufacturer(uint8_t spd) {
    uint8_t buf[2];

    // Module channels count is stored in SPD[240:241]

    if (!sdram_read_spd(spd, 240, &buf[0], 1, false)) {
        printf("Couldn't read module RCD manufacturer from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }
    if (!sdram_read_spd(spd, 241, &buf[1], 1, false)) {
        printf("Couldn't read module RCD manufacturer from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }
    uint16_t val;
    val = *(uint16_t*)buf;
    printf("RCD manufacturer: %x\n", val);

    return val;
}

uint8_t read_module_rcd_device_type(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[240:241]

    if (!sdram_read_spd(spd, 242, &buf, 1, false)) {
        printf("Couldn't read module RCD device type from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }
    printf("RCD type: %x\n", buf);

    return buf;
}

uint8_t read_module_rcd_device_rev(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[240:241]

    if (!sdram_read_spd(spd, 243, &buf, 1, false)) {
        printf("Couldn't read module RCD device rev from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }
    printf("RCD rev: %x\n", buf);

    return buf;
}

uint8_t read_module_enabled_clock(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[248]
    //     [0]: QACK: 0 enable/1 disable
    //     [1]: QBCK: 0 enable/1 disable
    //     [2]: QCCK: 0 enable/1 disable
    //     [3]: QDCK: 0 enable/1 disable
    //     [5]:  BCK: 0 enable/1 disable (LRDIMM)

    if (!sdram_read_spd(spd, 248, &buf, 1, false)) {
        printf("Couldn't read module clock enables from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }

    return buf & 0x2f;
}

uint8_t read_module_enabled_ca(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[249]
    //     [0]:    QACA: 0 enable/1 disable
    //     [1]:    QBCA: 0 enable/1 disable
    //     [2]:  DCS1_n: 0 enable/1 disable
    //     [3]:   BCS_n: 0 enable/1 disable
    //     [4]:  QxCA13: 0 enable/1 disable
    //     [5]: QACSx_n: 0 enable/1 disable
    //     [6]: QBCSx_n: 0 enable/1 disable

    if (!sdram_read_spd(spd, 249, &buf, 1, false)) {
        printf("Couldn't read module CA enables from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }

    return buf & 0x7f;
}

uint8_t read_module_qck_setup(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[250]
    // [1:0]: QACK: 00 20Ohm/ 01 14Ohm /10 10Ohm /11 RES
    // [3:2]: QBCK: 00 20Ohm/ 01 14Ohm /10 10Ohm /11 RES
    // [5:4]: QCCK: 00 20Ohm/ 01 14Ohm /10 10Ohm /11 RES
    // [7:6]: QDCK: 00 20Ohm/ 01 14Ohm /10 10Ohm /11 RES

    if (!sdram_read_spd(spd, 250, &buf, 1, false)) {
        printf("Couldn't read module QCK setup from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }

    return buf & 0xff;
}

uint8_t read_module_qca_qcs_setup(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[252]
    // [1:0]: QxCA: 00 20Ohm/ 01 14Ohm /10 10Ohm /11 RES
    // [5:4]: QxCS: 00 20Ohm/ 01 14Ohm /10 10Ohm /11 RES

    if (!sdram_read_spd(spd, 252, &buf, 1, false)) {
        printf("Couldn't read module QCA/QCS setup from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }

    return buf & 0x33;
}

uint8_t read_module_slew_rates(uint8_t spd) {
    uint8_t buf;

    // Module channels count is stored in SPD[252]
    // [1:0]: QxCK: 00 12-20 V/ns/ 01 14-27 V/ns /10 RES /11 RES
    // [3:2]: QxCA: 00   4-7 V/ns/ 01  6-10 V/ns /10 2.7-4.5 V/ns /11 RES
    // [5:4]: QxCS: 00   4-7 V/ns/ 01  6-10 V/ns /10 2.7-4.5 V/ns /11 RES

    if (!sdram_read_spd(spd, 254, &buf, 1, false)) {
        printf("Couldn't read module slew rates from the SPD, defaulting to x%d.\n", 0);
        return 0;
    }

    return buf & 0x3f;
}

#endif // defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_DDR5)
