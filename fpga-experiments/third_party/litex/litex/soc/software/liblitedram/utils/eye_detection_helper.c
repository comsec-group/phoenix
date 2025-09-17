#include <liblitedram/utils/eye_detection_helper.h>

#if defined(CSR_SDRAM_BASE)

#include <stdbool.h>
#include <inttypes.h>
#include <stdio.h>

#include <liblitedram/sdram_spd.h>

#define MAX(a, b) (a > b ? a : b)
#define MIN(a, b) (a < b ? a : b)

#ifndef SDRAM_PHY_DELAYS
#define SDRAM_PHY_DELAYS 0
#endif

static int32_t helper_arr[2*MAX(64, SDRAM_PHY_DELAYS)];
static int32_t helper_arr_it;

void clear_helper_arr(void) {
    helper_arr_it = 0;
    for (int i = 0; i < sizeof(helper_arr)/sizeof(int); ++i)
        helper_arr[i] = 0;
}

void set_helper_arr_value_and_advance(uint32_t value) {
    helper_arr[helper_arr_it++] = value;
}

int one_in_helper_arr(int max) {
    if (helper_arr[0]) return -1;
    for (int it = 1; it < max; ++it) {
       if (helper_arr[it]) return 1;
    }
    return 0;
}

int one_stride_helper_arr(int max) {
    for (int it = 0; it < max; ++it) {
       if (!helper_arr[it]) return it;
    }
    return max;
}

void find_eye_in_helper_arr(int *left, int *right, int max) {
    for (int it = 0; it < 2* max; ++it) {
        if (helper_arr[it] && *right == UNSET_DELAY)
            *right = it;
        if (!helper_arr[it] && *right != UNSET_DELAY) {
            *left = it;
            return;
        }
    }
    if (helper_arr[2*max - 1])
        *left = 2 * max;
}
#endif // defined(CSR_SDRAM_BASE)
