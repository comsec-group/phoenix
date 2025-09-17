#include <liblitedram/lpddr5_training.h>
#include <liblitedram/lpddr5_helpers.h>
#include <liblitedram/utils/eye_detection_helper.h>

#if defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_LPDDR5)

#include <stdbool.h>
#include <stdio.h>
#include <inttypes.h>

//TODO: Add support for x16 modules
//TODO: Add support for multiple modules

//#define INFO_LPDDR5
//#define DEBUG_LPDDR5
//#define CA_INFO_LPDDR5
//#define CA_DEBUG_LPDDR5
//#define READ_INFO_LPDDR5
//#define READ_DEBUG_LPDDR5
//#define READ_DEEP_DEBUG_LPDDR5
//#define WRITE_INFO_LPDDR5
//#define WRITE_DEBUG_LPDDR5
//#define WRITE_DEEP_DEBUG_LPDDR5
#if defined(DEBUG_LPDDR5) && !defined(CA_DEBUG_LPDDR5)
    #define CA_DEBUG_LPDDR5
#endif
#if defined(INFO_LPDDR5) && !defined(READ_INFO_LPDDR5)
    #define READ_INFO_LPDDR5
#endif
#if defined(DEBUG_LPDDR5) && !defined(WRITE_INFO_LPDDR5)
    #define WRITE_INFO_LPDDR5
#endif
#if defined(DEBUG_LPDDR5) && !defined(READ_DEBUG_LPDDR5)
    #define READ_DEBUG_LPDDR5
#endif
#if defined(DEBUG_LPDDR5) && !defined(WRITE_DEBUG_LPDDR5)
    #define WRITE_DEBUG_LPDDR5
#endif

#define MAX(a, b) (a > b ? a : b)
#define MIN(a, b) (a < b ? a : b)

// Addressing: channel, pin, 0-right eye closing, 1-left eye closing
//      \______________/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
//      --------<============>-------------
//              | valid data |
//most left point            most right point
//
// Delay clock has effects of moving signal to "the left"
//      ‾‾‾‾‾\______________/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
//      --------<============>-------------
// while delaying signal itself to "the right"
//      \______________/‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
//      --------------<============>-------------

/**
 * sdram_lpddr5_wck_training
 *
 * This training step aligns command CK and WCK.
 *
 * JESD209-5B 4.2.5
 */
static bool sdram_lpddr5_wck_training(training_ctx_t *const ctx) {
    int phase, prev_phase, count;
    enter_CK2WCK_leveling();
    // initial aligment
    ddrphy_cadly_rst_write(1);
    ddrphy_wdly_dqs_rst_write(1);
    ddrphy_wdly_dqs_bitslip_rst_write(1);
    phase = sample_CK2WCK_shift();
    prev_phase = phase;
    for (count = 0; count < ctx->max_delay_taps && phase == prev_phase; ++count) {
        prev_phase = phase;
        if (phase) {
            ddrphy_cadly_inc_write(1);
        } else {
            ddrphy_wdly_dqs_inc_write(1);
        }
        phase = sample_CK2WCK_shift();
    }
    exit_CK2WCK_leveling();
    return phase != prev_phase;
}

static const uint16_t serial[] = {
    0x0000, 0xffff,
    0xfffe, 0xfffd, 0xfffb, 0xfff7, 0xffef, 0xffdf, 0xffbf, 0xff7f,
    0xfeff, 0xfdff, 0xfbff, 0xf7ff, 0xefff, 0xdfff, 0xbfff, 0x7fff,
    0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0020, 0x0040, 0x0080,
    0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000, 0x4000, 0x8000};
static const int serial_count = sizeof(serial) / sizeof(serial[0]);

#ifdef READ_DEEP_DEBUG_LPDDR5
static int _read_verbosity = 3;
#elif defined(READ_DEBUG_LPDDR5)
static int _read_verbosity = 2;
#elif defined(READ_INFO_LPDDR5)
static int _read_verbosity = 1;
#else
static int _read_verbosity = 0;
#endif

/**
 * read_serial_number
 *
 * Reads serial number from the mode registers.
 * It is a 8 byte value stored in registers
 * MR47-MR54.
 * JESD209-5B 6.3
 */
static uint64_t read_serial_number(int module, int width) {
    int i;
    uint64_t serial_number = 0;

    // Serial number is a 5 byte value
    for (i = 0; i < 8; i++) {
        // Base register 65
        send_mrr(47+i);
        serial_number = (serial_number << 8) | recover_mrr_value(module, width);
    }

    return serial_number;
}

/**
 * rd_bitslip_idly_check_if_works
 *
 * Checks if for selected read cycle delay and
 * input DQ delay Mode Register readout is returning
 * correct data.
 *
 * Single serial test is being performed.
 *
 * JESD209-5B 4.2.9
 */
static int rd_bitslip_idly_check_if_works(int module, int width) {
    int works = 1;
    int seed;

    send_mrw(31, 0xA5);
    // Check if Serial readout works
    for (seed = 0; seed < serial_count && works; seed++) {
        /* Setup MRs */
        send_mrw(33, serial[seed]&0xff);
        send_mrw(34, serial[seed]>>8);
        for (int i = 0 ; i < 16 && works; ++i) {
            send_rdc();
            works &= compare_serial(module, width, serial[seed], 0xA5, 0);
            if (!works && _read_verbosity > 1) {
                compare_serial(module, width, serial[seed], 0xA5, 1);
            }
        }
    }
    return works;
}

/**
 * read_training_data_scan
 *
 * Performs a search for working pair of read bitslips and DQ delays.
 * It finds the first eye of working delays and selects its center
 * to configure the read bitslips and DQ delays.
 */

static eye_t read_training_data_scan(int module, int width, int max_delay_taps) {
    eye_t eye = DEFAULT_EYE;

    int rd_bitslip, idly;
    int works;

    printf("Data scan:\n");

    // Set read cycle delay
    rd_rst(module);

    for (rd_bitslip = 0; rd_bitslip < SDRAM_PHY_BITSLIPS; ++rd_bitslip) {
        printf("%2d|", rd_bitslip);
        idly_rst(module);
        for(idly = 0; idly < max_delay_taps; idly++){

            works = rd_bitslip_idly_check_if_works(module, width);
            printf("%d", works);

            if (works && eye.state == BEFORE) {
                eye.start = rd_bitslip * max_delay_taps + idly;
                eye.state = INSIDE;
            } else if (!works && eye.state == INSIDE) {
                eye.end = rd_bitslip * max_delay_taps + idly;
                eye.state = AFTER;
            }

            idly_inc(module);
        }
        printf("|\n");
        rd_inc(module);
    }

    if (eye.state != AFTER) {
        printf("Read training data scan failed for: "
               "module:%d\n", module);
    }
    return eye;
}

static bool read_training(int modules, int die_width, int max_taps) {
    int module;
    bool good = true;
    int eye_width, eye_center_bitslip, eye_center_delay;
    int rd_bitslip, idly;
//  int vref;

//#if defined(COMMON_VREF_CONTROL)
//  for(vref=0; vref<MAX_VREF; ++vref) {
//      set_verf(vref);
//#endif // defined(COMMON_VREF_CONTROL)
    for (module = 0; module < modules; module++) {
        printf("Training module%2d\n", module);
        eye_t eye = read_training_data_scan(module, die_width, max_taps);
        if (eye.state != AFTER) {
#ifndef KEEP_GOING_ON_DRAM_ERROR
            good = false;
#endif // KEEP_GOING_ON_DRAM_ERROR
            continue;
        }

        eye_width = eye.end - eye.start;
        eye.center = eye.start + (eye_width / 2);
        eye_center_bitslip = eye.center / max_taps;
        eye_center_delay = eye.center % max_taps;

        printf("eye_width:%2d; eye center: bitslip:%2d,delay:%2d\n",
            eye_width, eye_center_bitslip, eye_center_delay);

        // Setting read delay to eye center
        rd_rst(module);
        for (rd_bitslip = 0; rd_bitslip < eye_center_bitslip; ++rd_bitslip) {
            rd_inc(module);
        }

        idly_rst(module);
        for (idly = 0; idly < eye_center_delay; idly++) {
            idly_inc(module);
        }
    }
//#if defined(COMMON_VREF_CONTROL)
//  }
//#endif // defined(COMMON_VREF_CONTROL)

    return good;
}

static void read_check(
    int modules, int die_width) {

    int module;
    for (module = 0; module < modules; module++) {
        // Read the serial number
        printf(
            "Module:%2d serial number: 0x%010"PRIX64"\n",
            module,
            read_serial_number(module, die_width)
        );
    }

    if (_read_verbosity) {
        for (module = 0; module < modules; module++) {
            printf("Module:%d\n", module);
            read_registers(module, die_width);
        }
    }
    return;
}


/**
 * sdram_lpddr5_read_training
 *
 * Performs read preamble training for each module.
 *
 * It consists of 3 major steps:
 * 1. Find read cycle
 * 2. Perform a simple read check
 */

static bool sdram_lpddr5_read_training(training_ctx_t *const ctx) {
    bool good = true;
    printf("DQ read training\n");
    good &= read_training(ctx->modules,
                          ctx->die_width,
                          ctx->max_delay_taps);
#ifndef KEEP_GOING_ON_DRAM_ERROR
    if (!good)
        return good;
#endif // KEEP_GOING_ON_DRAM_ERROR
    // We must perform read checks below after exiting RPTM
    read_check(ctx->modules,
               ctx->die_width);
#ifndef KEEP_GOING_ON_DRAM_ERROR
    if (!good)
        return good;
#endif // KEEP_GOING_ON_DRAM_ERROR
    return true;
}

#ifdef WRITE_DEEP_DEBUG_LPDDR5
static int _write_verbosity = 3;
#elif defined(WRITE_DEBUG_LPDDR5)
static int _write_verbosity = 2;
#elif defined(WRITE_INFO_LPDDR5)
static int _write_verbosity = 1;
#else
static int _write_verbosity = 0;
#endif

static int write_serial_check(training_ctx_t *const ctx, int module) {
    int cnt_seed, i;
    int works = 1;
    for (cnt_seed = 0; cnt_seed < serial_count; ++cnt_seed) {
        setup_serial_write_data(module, ctx->die_width, serial[cnt_seed], 0, 0);
        for (i = 0; i < 8; ++i) {
            send_fifo_write();
            send_fifo_read();
            works &= compare_serial(module, ctx->die_width, serial[cnt_seed], 0, 0);
            if (!works && _write_verbosity > 1) {
                setup_serial_write_data(module, ctx->die_width, serial[cnt_seed], 0, 1);
                compare_serial(module, ctx->die_width, serial[cnt_seed], 0, 1);
            }
            if (!works)
                return works;
        }
    }
    return works;
}

static eye_t write_data_scan(training_ctx_t *const ctx, int module, int initial_bitslip, int print) {
    eye_t eye = DEFAULT_EYE;
    int works = 1;
    int bitslip;

    if (print)
        printf("Data scan:\n");
    wr_rst(module);
    for(bitslip = 0; bitslip < initial_bitslip; ++bitslip) {
        wr_inc(module);
    }
    for (bitslip = initial_bitslip; bitslip < SDRAM_PHY_BITSLIPS && eye.state != AFTER; ++bitslip) {
        if (print) {
            printf("%2d|", bitslip);
            if (_write_verbosity > 2)
                printf("\n");
        }

        odly_rst(module);
        for(int delay = 0; delay < ctx->max_delay_taps && eye.state != AFTER; ++delay){
            works = 1;
#ifndef LPDDR5_TRAINING_SIM
            works &= write_serial_check(ctx, module);
#endif // LPDDR5_TRAINING_SIM
            if (print)
                printf("%d", works);
            if (_write_verbosity > 1)
                printf("\n");

            if (works && eye.state == BEFORE) {
                eye.start = bitslip * ctx->max_delay_taps + delay;
                eye.state  = INSIDE;
            } else if (!works && eye.state == INSIDE) {
                eye.end = bitslip * ctx->max_delay_taps + delay;
                eye.state  = AFTER;
            }

            odly_inc(module);
        }
        if (print)
            printf("|\n");
        wr_inc(module);
    }
    return eye;
}

static int moduel_dq_vref_scan(training_ctx_t *const ctx, int module) {
#ifdef LPDDR5_TRAINING_SIM
    return 0x30;
#endif
    int eye_width_range [2][SDRAM_PHY_DELAYS];
    int vref, _width, initial_bitslip;
    eye_t last_eye = DEFAULT_EYE;
    int best_vref = -1;

    for(_width = 0; _width < SDRAM_PHY_DELAYS; ++_width) {
        eye_width_range[0][_width] = -1;
        eye_width_range[1][_width] = -1;
    }

    for(vref = 0xA; vref < 0x80; ++vref) { // FIXME: check over whole DQ VREF space, but keep performance
        if (_write_verbosity)
            printf("Vref:%2X", vref);
        send_mrw(14, vref);
        busy_wait_us(1);
        if (_write_verbosity)
            printf("\n");
        if (last_eye.state == BEFORE) {
            initial_bitslip = 0;
        } else {
            initial_bitslip = last_eye.start/ctx->max_delay_taps - 1;
        }
        eye_t eye = write_data_scan(ctx, module, initial_bitslip, _write_verbosity);
        if (_write_verbosity)
            printf("|start cycle:%2d, delay:%2d; end cycle:%2d, delay:%2d|",
                eye.start/ctx->max_delay_taps, eye.start%ctx->max_delay_taps,
                eye.end/ctx->max_delay_taps, eye.end%ctx->max_delay_taps);
        eye.center = eye.end - eye.start;

        if (_write_verbosity)
            printf("eye_width:%2d; eye center: cycle:%2d,delay:%2d\n", eye.center,
                ((eye.start + eye.end)/2)/ctx->max_delay_taps,
                ((eye.start + eye.end)/2)%ctx->max_delay_taps);

        for(_width = 0; _width < eye.center; ++_width) {
            if (eye_width_range[0][_width] == -1)
                eye_width_range[0][_width] = vref;
            eye_width_range[1][_width] = vref + 1;
        }
        last_eye = eye;
    }

    for (_width = 0; _width < SDRAM_PHY_DELAYS; ++_width) {
        if (eye_width_range[0][_width] != -1)
            best_vref = (eye_width_range[0][_width] + eye_width_range[1][_width]) / 2;
    }
    printf("m%2d|Best Vref:%2x\n", module, best_vref);
    if (best_vref > -1) {
        send_mrw(14, best_vref);
        busy_wait_us(1);
    }
    send_mrr(14);
    if (_write_verbosity)
        printf("MR10:%02"PRIx8"\n", recover_mrr_value(module, ctx->die_width));
    return best_vref;
}

static int module_vref_scan(training_ctx_t *const ctx, int module) {
    int best_vref, middle_cycle, middle_delay, it;

    wr_rst(module);
    odly_rst(module);
    best_vref = moduel_dq_vref_scan(ctx, module);

#ifndef KEEP_GOING_ON_DRAM_ERROR
    if (best_vref == -1)
        return best_vref;
#endif // KEEP_GOING_ON_DRAM_ERROR

    // Setting read delay to eye center
    wr_rst(module);
    odly_rst(module);
    eye_t eye = write_data_scan(ctx, module, 0, 1);
    middle_cycle = ((eye.start + eye.end)/2)/ctx->max_delay_taps;
    middle_delay = ((eye.start + eye.end)/2)%ctx->max_delay_taps;
    eye.center = eye.end - eye.start;
    printf("m%2d|start cycle:%2d, delay:%2d; end cycle:%2d, delay:%2d|",
        module,
        eye.start/ctx->max_delay_taps, eye.start%ctx->max_delay_taps,
        eye.end/ctx->max_delay_taps, eye.end%ctx->max_delay_taps);
    printf("eye_width:%2d; eye center: cycle:%2d,delay:%2d\n",
        eye.center, middle_cycle, middle_delay);

    wr_rst(module);
    odly_rst(module);
    if (eye.state == AFTER)
        for (it = 0; it < middle_cycle; ++it) {
            wr_inc(module);
        }
    if (eye.state == AFTER)
    for (it = 0; it < middle_delay; ++it) {
        odly_inc(module);
    }

    return best_vref;
}

static bool sdram_lpddr5_write_training(training_ctx_t *const ctx ) {
    int module;
    bool good = true;

    if (_write_verbosity > 1)
        for (module = 0; module < ctx->modules; module++) {
            read_registers(module, ctx->die_width);
        }

    printf("DQ write training\n");
// TODO: Vref scan over all modules at once
    for (module = 0; module < ctx->modules; module++) {
        good &= (module_vref_scan(ctx, module) != -1);
#ifndef KEEP_GOING_ON_DRAM_ERROR
        if (!good)
            return good;
#endif // KEEP_GOING_ON_DRAM_ERROR
    }
#ifndef KEEP_GOING_ON_DRAM_ERROR
    return good;
#endif // KEEP_GOING_ON_DRAM_ERROR
    return true;
}


training_ctx_t host_dram_ctx;

static void init_structs(void) {
    host_dram_ctx = (training_ctx_t) DEFAULT_HOST_DRAM;
}

/**
 * sdram_lpddr5_flow
 *
 * Performs the entire initialization and training
 * procedure for LPDDR5 memory.
 */
void sdram_lpddr5_flow(void) {
    clear_helper_arr();
    init_structs();

    training_ctx_t *base_ctx = &host_dram_ctx;

    // Reset PHY state
    ddrphy_cadly_rst_write(1);
    ddrphy_wdly_dqs_rst_write(1);
    ddrphy_wdly_dqs_bitslip_rst_write(1);
    for (int module = 0; module < base_ctx->modules; ++module) {
        rd_rst(module);
        idly_rst(module);
        wr_rst(module);
        odly_rst(module);
    }

    if (!sdram_lpddr5_wck_training(base_ctx)) {
        return;
    }
    printf("CK2WCK done\n");
    if (!sdram_lpddr5_read_training(base_ctx)) {
        return;
    }
    printf("Read training done\n");
    if (!sdram_lpddr5_write_training(base_ctx)) {
        return;
    }
    printf("Write training done\n");
}

#endif // defined(CSR_SDRAM_BASE) && defined(SDRAM_PHY_LPDDR5)
