# This file provides fast way for defininig new SDRAM modules.
# Modules defined in this files, after verifying that the settings are correct,
# should be later moved to LiteDRAM repository in a PR and removed from here.

from litedram.modules import DDR4Module, _SpeedgradeTimings, _TechnologyTimings, DDR5RegisteredModule


class MTA4ATF1G64HZ(DDR4Module):
    # geometry
    ngroupbanks = 4
    ngroups = 2
    nbanks = ngroups * ngroupbanks
    nrows = 128 * 1024
    ncols = 1024
    # timings
    trefi = {"1x": 64e6 / 8192, "2x": (64e6 / 8192) / 2, "4x": (64e6 / 8192) / 4}
    trfc = {"1x": (None, 350), "2x": (None, 260), "4x": (None, 160)}
    technology_timings = _TechnologyTimings(
        tREFI=trefi, tWTR=(4, 7.5), tCCD=(4, 6.25), tRRD=(4, 7.5), tZQCS=(128, None)
    )
    speedgrade_timings = {
        "2666": _SpeedgradeTimings(
            tRP=13.75, tRCD=13.75, tWR=15, tRFC=trfc, tFAW=(28, 30), tRAS=32
        ),
    }
    speedgrade_timings["default"] = speedgrade_timings["2666"]

class dimm_303_std(DDR5RegisteredModule):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=16.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=16.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]

class dimm_303_trc1(dimm_303_std):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    # tRC = 20.0
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=16.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=20.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]

class dimm_303_trc2(dimm_303_std):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    # tRC = 24.0
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=16.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=24.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]

class dimm_303_trp2(dimm_303_std):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    # tRP = 18.0 (trp=20 did not work anymore)
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=18.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=16.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]

class dimm_303_trp_trc(dimm_303_std):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    # tRP = 18.0
    # tRC = 18.0
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=17.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=17.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]

class dimm_303_trc3(dimm_303_std):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    # tRC = 17.0
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=16.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=17.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]

class dimm_303_trp3(dimm_303_std):
    ngroupbanks, ngroups, nbanks, nrows, ncols = 4, 8, 32, 65536, 2048
    trefi       = {'1x': 3906.25, '2x': 1953.125}
    trfc        = {'1x': (None, 295), '2x': (None, 160)}
    technology_timings = _TechnologyTimings(tREFI=trefi, tWTR=(10, 16), tCCD=(8, 5), tRRD=(8, 5), tZQCS=None)
    # tRP = 17.0
    speedgrade_timings = { "4800": _SpeedgradeTimings(tRP=17.0, tRCD=16.0, tWR=30.0, tRFC=trfc, tFAW=(13.333, 32), tRAS=32.0, tRC=16.0) }
    speedgrade_timings["default"] = speedgrade_timings["4800"]


