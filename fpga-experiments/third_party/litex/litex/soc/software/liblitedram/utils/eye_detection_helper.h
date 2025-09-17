#ifndef LIBLITEDRAM_UTILS_EYE_DETECTION_HELPER_H
#define LIBLITEDRAM_UTILS_EYE_DETECTION_HELPER_H
#include <generated/csr.h>
#ifdef CSR_SDRAM_BASE
#include <generated/sdram_phy.h>

#include <inttypes.h>

// Use max int16_t, all Fs could be interpreted as -1
#define UNSET_DELAY 0xefff

/**
 * clear_helper_arr
 * This function clears helper array and resets access iterator
 * to 0.
 */
void clear_helper_arr(void);

/**
 * set_helper_arr_value_and_advance
 * Stores `value` in helper array. It also advances access iterator by 1.
 */
void set_helper_arr_value_and_advance(uint32_t value);

/**
 * one_in_helper_arr
 * Searches helper array from 0 up to `max`, `max` not included.
 * Returns:
 *  -1 if index 0 has non zero value;
 *  1 if any other index has non-zero value,
 *  0 in all other cases.
 */
int one_in_helper_arr(int max);

/**
 * one_stride_helper_arr
 * Iterates over helper array from 0 up to `max`.
 * Returns:
 *  `idx` if `idx` contains 0 and all previous indices
 *  had non zero value
 *  max if array is full of non zero values
 */
int one_stride_helper_arr(int max);

/**
 * find_eye_in_helper_arr
 * Searches helper array from 0 to 2*`max`, `max` not included.
 * It returns first index with non-zero value in the `right` variable,
 * and in the `left` variable it returns first index with value of zero that
 * is after `right`.
 */
void find_eye_in_helper_arr(int *left, int *right, int max);
#endif // CSR_SDRAM_BASE
#endif // LIBLITEDRAM_UTILS_EYE_DETECTION_HELPER_H
