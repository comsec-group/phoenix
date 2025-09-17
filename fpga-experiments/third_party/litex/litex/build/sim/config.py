#
# This file is part of LiteX.
#
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept>
# Copyright (c) 2018 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import json
import math

class SimConfig():
    def __init__(self, default_clk=None, default_clk_freq=int(1e6)):
        self.modules = []
        if default_clk is not None:
            self.add_clocker(default_clk, default_clk_freq)

    def _format_interfaces(self, interfaces):
        if not isinstance(interfaces, list):
            interfaces = [interfaces]
        new = []
        for it in interfaces:
            obj = it
            if isinstance(it, tuple):
                name, index = it
                obj = {"name": name, "index": index}
            new.append(obj)
        return new

    def _format_timebase(self):
        clockers = [m for m in self.modules if m["module"] == "clocker"]
        timebase_fs = _calculate_timebase_fs(clockers)
        return {"timebase": int(timebase_fs)}

    def add_clocker(self, clk, freq_hz, phase_deg=0):
        args = {"freq_hz": freq_hz, "phase_deg": phase_deg}
        self.add_module("clocker", [], clocks=clk, tickfirst=True, args=args)

    def add_module(self, name, interfaces, clocks="sys_clk", args=None, tickfirst=False):
        interfaces = self._format_interfaces(interfaces)
        interfaces += self._format_interfaces(clocks)
        newmod = {
            "module": name,
            "interface": interfaces,
        }
        if args:
            newmod.update({"args": args})
        if tickfirst:
            newmod.update({"tickfirst": tickfirst})
        self.modules.append(newmod)

    def has_module(self, name):
        for module in self.modules:
            if module["module"] == name:
                return True
        return False

    def get_json(self):
        assert "clocker" in (m["module"] for m in self.modules), \
            "No simulation clocker found! Use sim_config.add_clocker() to define one or more clockers."
        config = self.modules + [self._format_timebase()]
        return json.dumps(config, indent=4)

def _calculate_timebase_fs(clockers):
    """Calculate timebase for a list of clocker modules

    Clock edges happen at time instants:
        t(n) = n * T/2 + P/360 * T
    where: T - clock period, P - clock phase [deg]
    We must be able to represent clock edges with the timebase B:
        t(n) mod B = 0, for all n
    In this function checks that:
        ((T/2) mod B = 0) AND ((P/360 * T) mod B = 0)

    Currently we allow only for integer periods (in fs), which it's quite restrictive.
    """
    # convert to picoseconds, 1fs is our finest timebase for dumping simulation data
    periods_fs = [1e15 / c["args"]["freq_hz"] for c in clockers]
    phase_shifts_fs = [int(p * c["args"]["phase_deg"]/360 + 0.5) for c, p in zip(clockers, periods_fs)]

    # calculate timebase as greatest common denominator
    timebase_fs = None
    for period, phase_shift in zip(periods_fs, phase_shifts_fs):
        if timebase_fs is None:
            timebase_fs = int(period/2)
        timebase_fs = math.gcd(timebase_fs, int(period/2))
        timebase_fs = math.gcd(timebase_fs, int(phase_shift))

    # check correctness
    for clocker, period, phase_shift in zip(clockers, periods_fs, phase_shifts_fs):
        def error(description):
            return f"""
SimConfig:
{description}:
  timebase = {timebase_fs}fs, period = {period}fs, phase_shift = {phase_shift}fs,
  clocker[args] = {clocker["args"]}
Adjust clock definitions so that integer multiple of 1fs can be used as a timebase.
            """.strip()

        assert int(period) == period, error("Non-integer period")
        assert int(phase_shift) == phase_shift, error("Non-integer phase_shift")

        assert (period/2 % timebase_fs) == 0, \
            error("Could not find an integer timebase for period")
        assert (phase_shift % timebase_fs) == 0, \
            error("Could not find an integer timebase for phase shift")

    return timebase_fs
