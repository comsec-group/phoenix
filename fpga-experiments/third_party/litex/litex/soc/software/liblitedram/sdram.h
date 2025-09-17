#ifndef __SDRAM_H
#define __SDRAM_H

#ifdef __cplusplus
extern "C" {
#endif

#include <generated/csr.h>


/*---------*/
/* Timings */
/*---------*/
struct sdram_timings_s {
    uint32_t trp;
    uint32_t trcd;
    uint32_t twr;
    uint32_t twtr;
    uint32_t trefi;
    uint32_t trfc;
    uint32_t tfaw;
    uint32_t tccd;
    uint32_t trrd;
    uint32_t trc;
    uint32_t tras;
    uint32_t tzqcs;
};

/*-----------------------------------------------------------------------*/
/* Constants                                                             */
/*-----------------------------------------------------------------------*/
int sdram_get_databits(void);
int sdram_get_freq(void);
int sdram_get_cl(void);
int sdram_get_cwl(void);

/*-----------------------------------------------------------------------*/
/* Software/Hardware Control                                             */
/*-----------------------------------------------------------------------*/
void sdram_software_control_on(void);
void sdram_software_control_off(void);

/*-----------------------------------------------------------------------*/
/* Mode Register                                                         */
/*-----------------------------------------------------------------------*/
void sdram_mode_register_write(char reg, int value);
#if defined(SDRAM_PHY_DDR5)
uint8_t sdram_mode_register_read(int channel, int pda, int reg);
#elif defined(SDRAM_PHY_LPDDR5)
// void cmd_injector(int channel, int phases, int cs, int command,
//                  int wrdata_en, uint64_t wrdata_mask, int rddata_en, int single)
uint8_t sdram_mode_register_read(int reg);
#endif

/*-----------------------------------------------------------------------*/
/* Write Leveling                                                        */
/*-----------------------------------------------------------------------*/
void sdram_write_leveling_rst_cmd_delay(int show);
void sdram_write_leveling_force_cmd_delay(int taps, int show);
int sdram_write_leveling(void);

/*-----------------------------------------------------------------------*/
/* Read Leveling                                                         */
/*-----------------------------------------------------------------------*/
void sdram_read_leveling(void);

/*-----------------------------------------------------------------------*/
/* Leveling                                                              */
/*-----------------------------------------------------------------------*/
int sdram_leveling(void);

/*-----------------------------------------------------------------------*/
/* Initialization                                                        */
/*-----------------------------------------------------------------------*/
int sdram_init(void);
int sdram_set_timings(struct sdram_timings_s *timings);
int sdram_timings_init(void);

/*-----------------------------------------------------------------------*/
/* Debugging                                                             */
/*-----------------------------------------------------------------------*/
void sdram_debug(void);

#ifdef __cplusplus
}
#endif

#endif /* __SDRAM_H */
