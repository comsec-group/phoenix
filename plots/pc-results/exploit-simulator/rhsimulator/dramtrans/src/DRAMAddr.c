#include "DRAMAddr.h"


static MemConfiguration config;


int init_lib(unsigned int config_sel) {
	config = Configurations[config_sel];
	return 0;
}


DRAMAddr to_dram(size_t a) {
	physaddr_t p = (physaddr_t) a;
	size_t res = 0;
	for (size_t i = 0; i < MTX_SIZE; i++) {
		res <<= 1ULL;
		res |=  (size_t) __builtin_parityl(p & config.DRAM_MTX[i]);
	}
	return (DRAMAddr) {
		((res>>config.BK_SHIFT)&config.BK_MASK),
		((res>>config.ROW_SHIFT)& config.ROW_MASK), 
		((res >>config.COL_SHIFT)& config.COL_MASK)
	};

}

size_t linearize(DRAMAddr d) {
	return (d.bank << config.BK_SHIFT) | (d.row << config.ROW_SHIFT) | (d.col << config.COL_SHIFT);
}                                                                                 

size_t to_addr(DRAMAddr d) {
	size_t res = 0;
	d.bank 	&= config.BK_MASK;
	d.row  	&= config.ROW_MASK;
	d.col 	&= config.COL_MASK;
	size_t l = linearize(d);
	for (size_t i = 0; i < MTX_SIZE; i++) {
		res <<= 1ULL;
		res |= (size_t) __builtin_parityl(l & config.ADDR_MTX[i]);
	}
	return res;
}

