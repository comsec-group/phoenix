# PC Proof-of-Concept

A DDR5 Rowhammer attack proof-of-concept that implements two specific access patterns—**skh_mod128** (Algorithm 1) and **skh_mod2608** (Algorithm 2) from the paper—to bypass SK Hynix DDR5 DIMMs and induce bit flips.

Phoenix automatically sweeps critical timing parameters to align access patterns with the DRAM controller’s refresh schedule, i.e.,
* the number of memory reads per tREFI interval (`--reads-per-trefi`), and  
* the self-synchronization cycle count (`--self-sync-cycles`).

Once a working combination has been found, Rowhammer-induced bit flips appear within seconds. By default, `make run` explores a reasonable parameter range. You must always specify `--pattern` to choose which attack pattern to evaluate. If you do not know 

We evaluated the attack on an **AMD Ryzen 7 7700X**,  but the same technique should apply to **any Zen 4 CPU**. To extend support to additional models, update the list of allowed CPU identifiers in `tools/phoenix.cpp`.

## Prerequisites

Make sure the following tools are installed (tested versions shown):

- `cmake` (tested: 3.22.5)  
- `g++` (tested: 9.4.0)  
- `make` (tested: 4.2.1)  
- `clang-format` (tested: 10.0.0)  

On Debian/Ubuntu you can install them with:

```bash
sudo apt update
sudo apt install build-essential cmake make clang-format
```

## Building

Generate the build files and compile (Release, Unix Makefiles):

```bash
# Remove all build artifacts from prior build
make clean
# Generate build files and compile (Release, Unix Makefiles)
make build
```

## Running

This target builds (if needed), creates a `results/` directory, and runs Phoenix.  
Results are stored in a timestamped CSV file:

```bash
make run ARGS="--pattern skh_mod2608"
```

By default this writes to:

```
results/bit_flips_<YYYYMMDD_HHMMSS>.csv
```

## Command-Line Interface

Phoenix provides a variety of command-line options. The most relevant are shown below:

```text
Phoenix

./build/tools/phoenix [OPTIONS]

OPTIONS:
  -h, --help
      Print this help message and exit

  -c, --core INT [5]
      CPU core to pin the running process to

      --sync-rows INT [8]
      Number of rows to use for synchronization

      --sync-row-start INT [512]
      Starting row index from which to allocate sync rows

      --self-sync-cycles TEXT [23000:26000:1000]
      Self-synchronization delay thresholds for detecting missed REF
      commands (format: start:end:step). The program will fuzz these
      parameters.

      --reads-per-trefi TEXT [86:92:2]
      Number of memory reads to issue per tREFI interval (format:
      start:end:step). The program will fuzz these parameters.

      --trefi-repeat INT [2048000]
      Number of tREFI intervals to execute the access pattern

      --ref-threshold INT [1150]
      Latency threshold to infer that a REF command occurred (by
      detecting access slowdowns)

      --hammer-fn TEXT
      Which hammer function to use (e.g., self_sync or seq_sync)

  -p, --pattern TEXT
      Which pattern to use (e.g., skh_mod128 or skh_mod2608)

      --aggressor-row-start INT [0]
      Starting row index for the first aggressor pair; each iteration
      advances this start row until --aggressor-row-end

      --aggressor-row-end INT [8]
      Row index at which to stop advancing the first aggressor pair

      --aggressor-spacing INT [8]
      Distance between each aggressor pair within the same bank (4
      pairs tested per bank)

      --column-stride INT [512]
      Stride in columns between adjacent memory accesses

      --pattern-trefi-offset-per-bank INT:NONNEGATIVE [16]
      Number of tREFI intervals to offset pattern start time per
      additional bank (increases chance of hitting vulnerable REF
      alignment)

  -S, --target-subch INT [0]
      Index of the target subchannel (default: 0)

  -R, --target-ranks INT [0]
      Index of the target memory rank (default: 0)

  -G, --target-bg INT [[0,1,2,3]]
      List of target bank groups to test (default: 0 1 2 3)

  -B, --target-banks INT [0]
      Index of the target bank within each group (default: 0)

      --csv TEXT
      Path to output CSV file containing bit flip results
```

For a full list of options and their descriptions, run:

```bash
./build/tools/phoenix --help
```

## Extending the code

Before submitting a PR, please apply `clang-format` to all tracked C/C++ sources in parallel:

```bash
make format
```
