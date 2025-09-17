/* Copyright (C) 2017 LambdaConcept */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "Vsim.h"
#include "verilated.h"
#ifdef TRACE_FST
#include "verilated_fst_c.h"
#else
#include "verilated_vcd_c.h"
#endif

#ifdef TRACE_FST
VerilatedFstC* tfp;
#else
VerilatedVcdC* tfp;
#endif
uint64_t tfp_start;
uint64_t tfp_end;
uint64_t main_time = 0;
Vsim *g_sim = nullptr;

extern "C" uint64_t litex_sim_eval(void *vsim, uint64_t time_fs, uint64_t timebase_fs)
{
  Vsim *sim = (Vsim*)vsim;
  main_time = time_fs;
  sim->eval();
  uint64_t next_timestamp = (time_fs/timebase_fs)*timebase_fs + timebase_fs;
  while(sim->eventsPending() && sim->nextTimeSlot() == time_fs)
    sim->eval();
  if (sim->eventsPending() && sim->nextTimeSlot() < next_timestamp) {
    next_timestamp = sim->nextTimeSlot();
  }
  return next_timestamp;
}

extern "C" void litex_sim_init_cmdargs(int argc, char *argv[])
{
  Verilated::commandArgs(argc, argv);
}

extern "C" void litex_sim_init_tracer(void *vsim, long start, long end)
{
  Vsim *sim = (Vsim*)vsim;
  tfp_start = start;
  tfp_end = end >= 0 ? end : UINT64_MAX;
  Verilated::traceEverOn(true);
#ifdef TRACE_FST
      tfp = new VerilatedFstC;
      tfp->set_time_unit("1fs");
      tfp->set_time_resolution("1fs");
      sim->trace(tfp, 99);
      tfp->open("sim.fst");
#else
      tfp = new VerilatedVcdC;
      tfp->set_time_unit("1fs");
      tfp->set_time_resolution("1fs");
      sim->trace(tfp, 99);
      tfp->open("sim.vcd");
#endif
  g_sim = sim;
}

extern "C" void litex_sim_tracer_dump()
{
  static int last_enabled = 0;
  bool dump_enabled = true;

  if (g_sim != nullptr) {
    dump_enabled = g_sim->sim_trace != 0 ? true : false;
    if (last_enabled == 0 && dump_enabled) {
      printf("<DUMP ON>");
      fflush(stdout);
    } else if (last_enabled == 1 && !dump_enabled) {
      printf("<DUMP OFF>");
      fflush(stdout);
    }
    last_enabled = (int) dump_enabled;
  }

  if (dump_enabled && tfp_start <= main_time && main_time <= tfp_end) {
    tfp->dump((vluint64_t) main_time);
  }
}

extern "C" int litex_sim_got_finish()
{
  return Verilated::gotFinish();
}

#if VM_COVERAGE
extern "C" void litex_sim_coverage_dump()
{
  VerilatedCov::write("sim.cov");
}
#endif

extern "C" void litex_sim_trace_flush_and_close()
{
  tfp->flush();
  tfp->close();
}

double sc_time_stamp()
{
  return main_time;
}
