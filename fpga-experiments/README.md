# DDR5 Rowhammer Tester Fork

This project is a fork of [antmicro/rowhammer-tester](https://github.com/antmicro/rowhammer-tester).
The upstream project provides the foundation: FPGA platform setup, bitstream generation, 
and low-level tooling to investigate the Rowhammer vulnerability on DDR5 devices.

This fork extends the upstream codebase with two main additions:

1. PyRAM, a domain-specific language to define and execute arbitrary DDR5 payloads
2. U-TRR, a methodology to study how target row refresh (TRR) is implemented in DDR5 devices

A payload is written in PyRAM, which uses Python-like syntax, and then executed on the DDR5 Tester. For example, a simple double-sided hammering pattern looks like this:

```python
for _ in range({hammer_count}):
    act(bank=addresses[0].bank, row=addresses[0].row)  # aggressor A
    pre()
    act(bank=addresses[1].bank, row=addresses[1].row)  # aggressor B
    pre()
```

In this snippet, `addresses` and `hammer_count` are placeholders.
At compile time, the user specifies the actual values, 
for example by loading them from a configuration file or passing them as command line arguments. 
These values are then translated into the DDR5 command stream that the FPGA executes on the DIMM.

## Getting Started

Before running any experiments, the environment must be prepared. This includes
installing system-level dependencies, setting up the Python environment, and
building the FPGA bitstream for the DDR5 tester.

### 1.1 Install system dependencies

The project depends on a number of external tools and libraries (such as
compilers, FPGA toolchains, and utility programs). Install them by running:

```bash
./install_dependencies.sh
````

### 1.2 Set up the Python environment and libraries

Next, install all required Python packages and project-specific libraries:

```bash
make deps
```

This command creates a local virtual environment in the `venv/` directory.
Activate it as follows:

```bash
source venv/bin/activate
```

All subsequent commands should be executed within this virtual environment to
ensure the correct dependencies are used.

### 1.3 Build the DDR5 tester bitstream

Once the environment is prepared, generate the FPGA bitstream used to interact
with the DDR5 DIMM under test. This step compiles the design based on
configuration parameters such as payload size and the DIMM’s SPD file.

For example, to build a bitstream with a payload size of 2¹⁷ and a specific SPD
description file:

```bash
python3 tools/bitstream/build_ddr5_tester.py \
    --payload-size $((2 ** 17)) \
    --spd-file ~/ddr5-rdimm-info/spd/dimm_314.spd
```

Replace the `--spd-file` path with the SPD file corresponding to the DIMM you
intend to test.

### 1.4 Flash the bitstream

Once the bitstream archive is available, flash it to the board using:

```bash
python3 tools/bitstream/flash.py \
    --bitstream-file \
    bitstreams/ddr5_tester_dimeyer_add-repo-b_77825ea_dimm_payload131072.zip
```

---

### 1.5 Initialize the memory

After flashing, initialize the DDR5 memory before starting any experiments:

```bash
python3 rowhammer_tester/scripts/mem.py
```

## Rowhammer Pattern Executor

This tool provides a script to load a PyRAM program, 
compile it with user-specified parameters, execute it on the DDR5 tester, 
and log resulting bit flips to a CSV file.

Some DDR5 DIMMs implement TRR (Target Row Refresh) state tracking 
that depends on the number of `REF` commands issued since initialization. 
To reproduce results on such DIMMs, the script supports issuing `REF` commands up 
to a user-defined modulo boundary before running the payload. 
This allows experiments to be aligned with the refresh counter state.

### Provided Patterns

We include two ready-to-use patterns as PyRAM files in:

```
fpga-experiments/payloads/patterns/
```

You can execute one of these patterns with the script. For example:

```bash
python3 utrr/scripts/exec_pattern.py \
  --banks 0 \
  --victim-rows 1000 \
  --aggressor-offsets -1 1 \
  --patterns 0x00 \
  --dram-mapping direct \
  --modulo {0..127} \
  --modulus 128 \
  --iterations 3 \
  --decoy-rows 6 \
  --pattern-code-path payloads/patterns/align_mod128_template.pyram \
  --output-dir exec_pattern_results \
  --pattern-repetitions 320 \
  --refs-per-pattern 128 \
  --acts-per-trefi 50
```

### What the Script Does

* Scans the entire modulo space (`--modulo {0..127}` with `--modulus 128`) to test every possible refresh counter alignment.
* Executes the provided PyRAM pattern on the DDR5 tester.
* Logs all detected bit flips to a CSV file, annotated with the tested modulo case.

This way, the script can reveal which modulo offsets are vulnerable, as shown in **Table 3 of the paper**.

To reproduce the findings:

* With the **128-REF pattern**, you should observe **2 vulnerable offsets**.
* With the **2608-REF pattern**, you should observe **92 vulnerable offsets**.

### Sweeping Activation Rates and Pattern Length

Once a vulnerable offset is identified, you no longer need to scan the whole modulo space. Instead:

* Fix the offset you found (for example, `--modulo 42`).
* Sweep `--acts-per-trefi` (for example, `30 40 50`) to evaluate how many activations per refresh interval are needed to trigger flips.
* Sweep `--pattern-repetitions` to see how effective the pattern is when executed over multiple refresh windows. For example:

  * `64 * 128 = 8192` (one tREFW)
  * `2 * 8192 = 16384` (two tREFW)
  * `3 * 8192 = 24576` (three tREFW)

## U-TRR: Finding Retention Rows

As a first step toward U-TRR experiments, we provide a script to identify DRAM rows with **similar retention times**.

The script works in two phases:

1. **Upper bound filtering (intersection phase)**
   Test rows are written with a pattern, refresh is disabled for `wait_upper_ms`, and only rows that always flip across multiple iterations are kept.

2. **Lower bound filtering (union phase)**
   The surviving rows are retested with a shorter wait time `wait_lower_ms`, and any row that ever flips at this shorter interval is discarded.

The result is a set of rows that reliably flip after the upper wait but not after the lower wait. These rows share similar retention characteristics and are saved for later use in U-TRR experiments.

### Running the Script

```bash
python3 utrr/scripts/find_retention_rows.py \
  --config payloads/utrr/retention_config.yml
```

All fields shown in the YAML config below can also be specified directly via CLI arguments.

### Example YAML config

```yaml
name: retention_scan
dram_mapping: direct        # or "samsung"
bank: 0                     # DRAM bank to analyze
start: 1000                 # starting row index
end: 1250                   # ending row index
pattern_32bit: 0xFFFFFFFF   # test pattern to initialize memory
wait_lower_ms: 900          # lower bound wait in ms
wait_upper_ms: 1000         # upper bound wait in ms
iterations: 100             # number of repetitions per test
# addresses_file: addresses_input.json  # optional: reuse existing test addresses
```

### Output

A JSON file named:

```
addresses_<start>_<end>_<wait_lower_ms>_<wait_upper_ms>.json
```

containing the list of addresses that meet the retention time criteria.

Example:

```
addresses_1000_1250_900_1000.json
```

## U-TRR: Executing Experiments

After identifying retention rows, this fork provides a script to run U-TRR experiments. The script selects suitable victim rows, compiles one or more PyRAM payloads, and executes them under controlled refresh conditions. Bitflips are logged, and all experiment data is saved for later analysis.

To reproduce the results of Section 4 of the paper, we provide three ready-to-use experiments in `fpga-experiments/payloads/utrr`. Each experiment highlights a different aspect of TRR behavior on vulnerable DIMMs.

### Section 4.1 – Candidate Period

Program: `4_1_candidate_period.pyram`  

This experiment investigates how TRR samples refresh windows. It allows you to test candidate sampling periods (N) and observe how often TRR targets particular tREFI windows.  

- For `N = 128`, a vulnerable DIMM shows 64 consecutive tREFI windows, 32 of which form a regular pattern sampled less frequently by TRR.  
- For `N = 2 × 128`, the same behavior repeats across the DIMM.  

This experiment applies to DIMMs that are vulnerable to the P128 pattern (128 REF commands).  

#### Example Command

```bash
python3 utrr/scripts/exec_utrr.py \
--addresses-file addresses_1000_2000_16000_23000.json \
--num-rows 128 \
--min-row-distance 10 \
--pre-wait-ms 15000 \
--wait-ms 24000 \
--program fpga-experiments/payloads/utrr/4_1_candidate_period.pyram \
--execute-payload \
--num-runs 25 \
--output-dir experiments/candidate_period \
--dram-mapping direct \
--template-var candidate_length=128 \
--log-file-level DEBUG \
--log-console-level INFO
````

#### Explanation of Key Parameters

* `--addresses-file addresses_1000_2000_16000_23000.json`
  This file contains retention rows selected from indices 1000 to 2000, each with a retention time between 16s and 23s. Retention time depends strongly on DIMM temperature; the provided dataset was collected at 50 °C.

* `--num-rows 128` and `--min-row-distance 10`
  From this pool, the experiment selects 128 rows. Each chosen row is at least 10 rows apart from the others to avoid interference between neighboring victims.

* `--pre-wait-ms 15000`
  Before issuing the experiment-specific payload, the FPGA waits 15s. At this point, rows are close to losing their data. Rows that are refreshed by TRR should receive additional refreshes, effectively extending their retention by at least another 15s.

* `--wait-ms 24000`
  After payload execution, the FPGA waits until 24s total before checking for bit flips. Rows without additional refreshes should show retention errors after \~23 s, so 24s ensures they are reliably caught (with a 1s safety margin).

* `--template-var candidate_length=128`
  Sets the number of candidate periods (N=128) to test in the `4_1_candidate_period.pyram` program. This defines the loop length in the PyRAM template.

#### Output

Each experiment produces a structured result directory containing:

* the compiled PyRAM payload(s) and the binary instruction streams
* the set of victim and program addresses used
* a JSON export of the experiment arguments
* result files with refresh counters and rows that did or did not flip
* log files

### Section 4.2 – Probing Lightly Sampled tREFI Intervals

Program: `4_2_act_sampling.pyram`  

This experiment investigates what happens inside the lightly sampled tREFI intervals identified in Section 4.1. The goal is to determine which ACTs within these intervals are actually being tracked by TRR.  

By aligning the refresh counter to a specific modulo boundary, the lightly sampled intervals can always be studied in the same alignment. During these intervals, the program hammers the neighbors of canary rows. The canary rows themselves are retention profiled, allowing the retention side channel to reveal whether TRR refreshed them indirectly. This shows if certain ACTs are targeted more frequently by TRR than others.  

This experiment therefore provides insight into whether TRR applies mitigation uniformly across an interval or selectively to a subset of ACTs.  

#### Example Command

```bash
python3 utrr/scripts/exec_utrr.py \
--addresses-file addresses_1000_2000_16000_23000.json \
--num-rows 59 \
--min-row-distance 10 \
--pre-wait-ms 15000 \
--wait-ms 24000 \
--program fpga-experiments/payloads/utrr/4_2_act_sampling.pyram \
--execute-payload \
--num-runs 100 \
--output-dir experiments/act_sampling \
--dram-mapping direct \
--log-file-level DEBUG \
--log-console-level INFO
````
