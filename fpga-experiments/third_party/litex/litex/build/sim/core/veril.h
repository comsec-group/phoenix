/* Copyright (C) 2017 LambdaConcept */

#ifndef __VERIL_H_
#define __VERIL_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" void litex_sim_init_cmdargs(int argc, char *argv[]);
extern "C" uint64_t litex_sim_eval(void *vsim, uint64_t time_fs, uint64_t timebase_fs);
extern "C" void litex_sim_init_tracer(void *vsim, long start, long end);
extern "C" void litex_sim_tracer_dump();
extern "C" int litex_sim_got_finish();
extern "C" void litex_sim_trace_flush_and_close();
#if VM_COVERAGE
extern "C" void litex_sim_coverage_dump();
#endif
#else
uint64_t litex_sim_eval(void *vsim, uint64_t time_fs, uint64_t timebase_fs);
void litex_sim_init_tracer(void *vsim);
void litex_sim_tracer_dump();
int litex_sim_got_finish();
void litex_sim_trace_flush_and_close();
void litex_sim_init_cmdargs(int argc, char *argv[]);
#if VM_COVERAGE
void litex_sim_coverage_dump();
#endif
#endif

#endif
