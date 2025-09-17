#
# This file is part of LiteDRAM.
#
# Copyright (c) 2015 Sebastien Bourdeauducq <sb@m-labs.hk>
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from operator import or_, and_, add
from functools import reduce
from migen import *

from litedram.phy import dfi
from litedram.common import TappedDelayLine
from litex.soc.interconnect.csr import *
from litedram.phy.ddr5.commands import DFIPhaseAdapter

# PhaseInjector ------------------------------------------------------------------------------------

class PhaseInjector(Module, AutoCSR):
    def __init__(self, phase, write_latency):
        self._command       = CSRStorage(fields=[
            CSRField("cs",   size=1, description="DFI chip select bus"),
            CSRField("we",   size=1, description="DFI write enable bus"),
            CSRField("cas",  size=1, description="DFI column address strobe bus"),
            CSRField("ras",  size=1, description="DFI row address strobe bus"),
            CSRField("wren", size=1, description="DFI write data enable bus"),
            CSRField("rden", size=1, description="DFI read data enable bus"),
        ], description="Control DFI signals on a single phase")

        self._command_issue = CSR() # description="The command gets commited on a write to this register"
        self._address       = CSRStorage(len(phase.address), reset_less=True,  description="DFI address bus")
        self._baddress      = CSRStorage(len(phase.bank),    reset_less=True,  description="DFI bank address bus")
        self._wrdata        = CSRStorage(len(phase.wrdata),  reset_less=True,  description="DFI write data bus")
        self._rddata        = CSRStatus(len(phase.rddata), description="DFI read data bus")

        # # #

        wdata_ready = phase.wrdata_en
        for _ in range(write_latency):
            new_wdata_ready = Signal.like(wdata_ready)
            self.sync += new_wdata_ready.eq(wdata_ready)
            wdata_ready = new_wdata_ready

        self.comb += [
            If(self._command_issue.re,
                phase.cs_n.eq(Replicate(~self._command.fields.cs, len(phase.cs_n))),
                phase.we_n.eq(~self._command.fields.we),
                phase.cas_n.eq(~self._command.fields.cas),
                phase.ras_n.eq(~self._command.fields.ras)
            ).Else(
                phase.cs_n.eq(Replicate(1, len(phase.cs_n))),
                phase.we_n.eq(1),
                phase.cas_n.eq(1),
                phase.ras_n.eq(1)
            ),
            phase.address.eq(self._address.storage),
            phase.bank.eq(self._baddress.storage),
            phase.wrdata_en.eq(self._command_issue.re & self._command.fields.wren),
            phase.rddata_en.eq(self._command_issue.re & self._command.fields.rden),
            phase.wrdata.eq(self._wrdata.storage & Replicate(wdata_ready, len(phase.wrdata))),
            phase.wrdata_mask.eq(0)
        ]
        self.sync += If(phase.rddata_valid, self._rddata.status.eq(phase.rddata))

# CommandsInjector ------------------------------------------------------------------------------

class CmdInjector(Module, AutoCSR):
    def __init__(self, phases, force_issue, masked_writes=False):
        num_phases = len(phases)
        assert num_phases > 0
        cs_width = len(phases[0].cs_n)
        wrdata_width = len(phases[0].wrdata)
        rddata_width = len(phases[0].rddata)
        wrdata_mask_width = len(phases[0].wrdata_mask)

        self._command_storage = CSRStorage(fields=[
            CSRField("ca",          size=14,        description="Command/Address bus"),
            CSRField("cs",          size=cs_width,  description="DFI chip select bus"),
            CSRField("wrdata_en",   size=1),
            CSRField("rddata_en",   size=1),
        ], description="DDR5 command and control signals")
        self._command_storage_wr_mask = CSRStorage(fields=[
            CSRField("wrdata_mask", size=wrdata_mask_width),
        ], description="DDR5 wrdata mask control signals")
        self._phase_addr = CSRStorage(8)
        self._store_continuous_cmd = CSR()
        self._store_singleshot_cmd = CSR()
        self._single_shot = CSRStorage(reset=0b0)
        self._issue_command = CSR() # Issues command when in single shot, loads to _continuous_phase_signals when in continuous mode

        ca_start = 0
        cs_start = ca_end = 0 + 14
        wr_en_start = cs_end = cs_start + cs_width
        rd_en_start = wr_en_end = wr_en_start + 1
        wr_mask_start = rd_en_end = rd_en_start + 1
        wr_mask_end = wr_mask_start + wrdata_mask_width

        self._continuous_intermediate_store = Array(Signal(14 + cs_width + 2 + wrdata_mask_width, reset=0b11111) for _ in range(4))
        self._continuous_phase_signals = Array(Signal(14 + cs_width + 2 + wrdata_mask_width, reset=0b11111) for _ in range(4))
        # There are limited number of commands that make sens to be emitted continuously: DES, NOP. MPC, CS training pattern,
        self._singleshot_phase_signals = Array(Signal(14 + cs_width + 2 + wrdata_mask_width) for _ in range(8)) # BL 16 needs at most 8 DFI transactions (2 for command and 8 for wrdata/rddata)

        self.sync += [
            If(((self._issue_command.re | force_issue) & ~self._single_shot.storage),
                [self._continuous_phase_signals[i].eq(self._continuous_intermediate_store[i]) for i in range(4)]
            )
        ]

        continuous_max = max(4 // num_phases, 1)
        singleshot_max = max(8 // num_phases, 1)

        continuous_counter = Signal(max = continuous_max, reset=0) if continuous_max > 1 else Signal()
        singleshot_counter = Signal(max = singleshot_max, reset=0) if singleshot_max > 1 else Signal()

        singleshot_issue = Signal(2)

        self.sync += [
            If((singleshot_issue == 0) & (self._issue_command.re | force_issue) & self._single_shot.storage,
                singleshot_issue.eq(1),
            ).Elif((singleshot_issue == 1) & singleshot_counter == singleshot_max-1,
                singleshot_issue.eq(2),
            ).Elif((singleshot_issue == 2) & singleshot_counter == singleshot_max-1,
                singleshot_issue.eq(0),
            ),

            If(singleshot_counter == (singleshot_max - 1),
                singleshot_counter.eq(0),
            ).Else(
                singleshot_counter.eq(singleshot_counter + 1),
            ),

            If(continuous_counter == (continuous_max - 1),
                continuous_counter.eq(0),
            ).Else(
                continuous_counter.eq(continuous_counter + 1),
            ),
        ]

        for i in range(4):
            self.sync += [
                If(self._store_continuous_cmd.re,
                    If(self._phase_addr.storage[i],
                        self._continuous_intermediate_store[i].eq(
                            Cat(self._command_storage.storage,
                                self._command_storage_wr_mask.storage)),
                    ),
                ),
            ]

        for i in range(8):
            self.sync += [
                If(self._store_singleshot_cmd.re,
                    If(self._phase_addr.storage[i],
                        self._singleshot_phase_signals[i].eq(
                            Cat(self._command_storage.storage,
                                self._command_storage_wr_mask.storage)),
                    ),
                ),
            ]

        for phase in phases:
            self.comb += [
                phase.cs_n.eq(Replicate(1, cs_width)),
                phase.address.eq(Replicate(0, 14)),
                phase.wrdata_en.eq(0),
                phase.wrdata_mask.eq(Replicate(0, wrdata_mask_width)),
                phase.rddata_en.eq(0),
            ]

        for i in range(max(4, num_phases)):
            dfi_phase_num = i % num_phases
            reg_num       = i % 4
            counter       = i // num_phases
            phase         = phases[dfi_phase_num]
            self.comb += [
                If((singleshot_issue != 2) & (continuous_counter == counter),
                    phase.cs_n.eq(~self._continuous_phase_signals[reg_num][cs_start:cs_end]),
                    phase.address.eq(self._continuous_phase_signals[reg_num][ca_start:ca_end]),
                    phase.wrdata_en.eq(self._continuous_phase_signals[reg_num][wr_en_start:wr_en_end]),
                    phase.wrdata_mask.eq(self._continuous_phase_signals[reg_num][wr_mask_start:wr_mask_end]),
                    phase.rddata_en.eq(self._continuous_phase_signals[reg_num][rd_en_start:rd_en_end]),
                ),
            ]

        for i in range(max(8, num_phases)):
            dfi_phase_num = i % num_phases
            reg_num       = i % 8
            counter       = i // num_phases
            phase         = phases[dfi_phase_num]
            if dfi_phase_num < 8:
                self.comb += [
                    If((singleshot_issue == 2) & (singleshot_counter == counter),
                        phase.cs_n.eq(~self._singleshot_phase_signals[reg_num][cs_start:cs_end]),
                        phase.address.eq(self._singleshot_phase_signals[reg_num][ca_start:ca_end]),
                        phase.wrdata_en.eq(self._singleshot_phase_signals[reg_num][wr_en_start:wr_en_end]),
                        phase.wrdata_mask.eq(self._singleshot_phase_signals[reg_num][wr_mask_start:wr_mask_end]),
                        phase.rddata_en.eq(self._singleshot_phase_signals[reg_num][rd_en_start:rd_en_end]),
                    ),
                ]
            else:
                self.comb += [
                    If((singleshot_issue == 2) & (singleshot_counter == counter),
                        phase.cs_n.eq(Replicate(1, cs_width)),
                        phase.address.eq(Replicate(0, 14)),
                        phase.wrdata_en.eq(Replicate(0, 1)),
                        phase.wrdata_mask.eq(Replicate(0, wrdata_mask_width)),
                        phase.rddata_en.eq(Replicate(0,1)),
                    ),
                ]

        # Wrdata path

        self._wrdata_select = CSRStorage(int(8).bit_length())
        self._wrdata   = CSRStorage(wrdata_width)
        self._wrdata_s = CSRStatus(wrdata_width)
        self._wrdata_store = CSR()

        self.wrdata = Array(Signal(wrdata_width) for _ in range(8)) # DDR5 max length BL/2

        self.sync += [
            If(self._wrdata_store.re,
                self.wrdata[self._wrdata_select.storage].eq(self._wrdata.storage)
            ),
        ]

        self.sync += [
            self._wrdata_s.status.eq(self.wrdata[self._wrdata_select.storage])
        ]

        for phase in phases:
            self.comb += [
                phase.wrdata.eq(Replicate(0, wrdata_width)),
            ]

        for i in range(max(4, num_phases)):
            dfi_phase_num = i % num_phases
            reg_num       = i % 4
            counter       = i // num_phases
            phase         = phases[dfi_phase_num]
            self.comb += [
                If((singleshot_issue != 2) & (continuous_counter == counter) &
                    self._continuous_phase_signals[reg_num][wr_en_start:wr_en_end],
                    phase.wrdata.eq(self.wrdata[reg_num]),
                ),
            ]

        for i in range(max(8, num_phases)):
            dfi_phase_num = i % num_phases
            reg_num       = i % 8
            counter       = i // num_phases
            phase         = phases[dfi_phase_num]
            if dfi_phase_num < 8:
                self.comb += [
                    If((singleshot_issue == 2) & (singleshot_counter == counter) &
                        self._singleshot_phase_signals[reg_num][wr_en_start:wr_en_end],
                        phase.wrdata.eq(self.wrdata[reg_num]),
                    ),
                ]
            else:
                self.comb += [
                    If((singleshot_issue == 2) & (singleshot_counter == counter),
                        phase.wrdata.eq(Replicate(0, wrdata_width)),
                    ),
                ]

        # Continuous DQ sampling

        self._setup = CSRStorage(fields=[
            CSRField("initial_state", size=1,  description="Initial value of all bits"),
            CSRField("operation",     size=1,  description="0 - `or` (default), 1 -`and`"),
        ])

        self._sample       = CSRStorage()
        self._result_array = CSRStatus(rddata_width)
        self._reset        = CSR()

        op = Signal()

        self._sample_memory = Array(Signal(rddata_width) for  _ in range(num_phases))
        self.sync += [
            If(self._reset.re,
                *[mem.eq(Replicate(self._setup.fields.initial_state, rddata_width)) for mem in self._sample_memory],
                op.eq(self._setup.fields.operation),
            ).Elif(self._sample.storage,
                *[If(op,
                    self._sample_memory[i].eq(self._sample_memory[i] & phase.rddata)
                  ).Else(
                    self._sample_memory[i].eq(self._sample_memory[i] | phase.rddata)
                  ) for i, phase in enumerate(phases)],
            ).Else(
                If(op,
                    self._result_array.status.eq(reduce(and_, [self._sample_memory[i] for i in range(num_phases)])),
                ).Else(
                    self._result_array.status.eq(reduce(or_, [self._sample_memory[i] for i in range(num_phases)])),
                ),
            )
        ]

        # Rddata path

        self._rddata_select      = CSRStorage(int(8).bit_length())
        self._rddata_capture_cnt = CSRStorage(4)
        self._rddata = CSRStatus(rddata_width)

        self.rddata = Array(Signal(rddata_width) for _ in range(8)) # DDR5 max length BL/2

        self.sync += [
            self._rddata.status.eq(self.rddata[self._rddata_select.storage])
        ]

        self.rddata_valids    = rddata_valids    = Array([Signal(4) for _ in range(len(phases))])
        self.comb += [
            rddata_valids[i].eq(
                reduce(or_,
                    [phase.rddata_valid[j] for j in range(len(phase.rddata_valid))]
                )
            ) for i, phase in enumerate(phases)]

        self.any_rddata_valid = any_rddata_valid = Signal()
        self.comb += any_rddata_valid.eq(reduce(or_, rddata_valids))

        self.submodules.read_fsm = read_fsm = FSM()
        self.read_cnt = read_cnt = Signal(max=9)
        self.read_counts_tmp = read_counts_tmp = Array(Signal(4) for _ in range(8))

        read_fsm.act("IDLE",
            NextValue(read_cnt, 0),
            If(any_rddata_valid,
                *[read_counts_tmp[i].eq(read_cnt + reduce(add, rddata_valids[:i], 0)) for i in range(len(phases))],
                *[If(phase.rddata_valid,
                    NextValue(self.rddata[read_counts_tmp[i]], phases[i].rddata)
                ) for i, phase in enumerate(phases)],
                NextValue(read_cnt, reduce(add, rddata_valids)),
                NextState("CAPTURE"),
            ),
        )
        read_fsm.act("CAPTURE",
            If(any_rddata_valid,
                *[read_counts_tmp[i].eq(read_cnt + reduce(add, rddata_valids[:i], 0)) for i in range(len(phases))],
                *[If(phase.rddata_valid,
                    NextValue(self.rddata[read_counts_tmp[i]], phase.rddata),
                ) for i, phase in enumerate(phases)],
                NextValue(read_cnt, (read_cnt + reduce(add, rddata_valids))),
            ),
            If((self._rddata_capture_cnt.storage <= read_cnt),
                NextValue(read_cnt, 0),
                NextState("IDLE"),
            ),
        )
        read_fsm.finalize()

# DFISamplerDDR5 ----------------------------------------------------------------------------------

class DFISamplerDDR5(Module, AutoCSR):
    def __init__(self, phases, prefix):
        nphases = len(phases)
        phases_ = [getattr(phase, prefix) for phase in phases]
        self.trigger_cond  = CSRStorage(14)    # Capture start
        self.trigger_valid = CSRStorage(14)    # Checked bits

        self.select        = CSRStorage(nphases.bit_length()-1) # Access result
        self.capture       = CSRStatus(14)     # Captured bits
        self.captured      = CSRStatus()       # CApture was triggered

        self.reset         = CSR()             # Reset capture
        self.start         = CSR()             # Start capture

        counter = Signal(nphases.bit_length()) # Captured so far
        counter_temps = [Signal(nphases.bit_length()) for _ in range(nphases)]
        self.capture_mem   = Array([Signal(14) for _ in range(nphases)])
        triggered = Signal(nphases)

        self.comb += [
            counter_temps[i].eq(counter+i) for i in range(nphases)
        ]

        fsm = FSM()
        self.submodules += fsm
        fsm.act("READY",
            If(self.start.re,
                NextValue(counter, 0),
                NextState("AWAIT"),
            )
        )
        fsm.act("AWAIT",
            triggered.eq(
                Cat([
                    reduce(and_, [
                        ~((phase.address[j] ^ self.trigger_cond.storage[j]) & self.trigger_valid.storage[j]) for j in range(14)]
                    ) for i, phase in enumerate(phases_)]
                )
            ),
            [If(~phase.cs_n & ~reduce(or_, triggered[:i], 0) & triggered[i],
                *[NextValue(self.capture_mem[j], phases_[i+j].address) for j in range(nphases-i)],
                NextValue(counter, nphases-i),
                NextState("FIN-CAPTURE"),
            ) for i, phase in enumerate(phases_)],
        )
        capture_cases = {}
        for i in range(1, nphases):
            capture_cases[i] = [
                *[NextValue(self.capture_mem[counter_temps[j]], phases_[j].address) for j in range(i)],
                NextValue(counter, nphases),
            ]
        fsm.act("FIN-CAPTURE",
            Case(counter,
                capture_cases
            ),
            If(counter == nphases,
                NextState("DONE"),
            ),
        )
        fsm.act("DONE",
            self.captured.status.eq(1),
            If(self.reset.re,
                NextState("READY",)
            )
        )
        self.sync += [
            self.capture.status.eq(self.capture_mem[self.select.storage]),
        ]

# DFIInjector --------------------------------------------------------------------------------------

class DFIInjector(Module, AutoCSR):
    def __init__(self, addressbits, bankbits, nranks, databits, nphases=1, write_latency=0,
                 memtype=None, strobes=None, with_sub_channels=False, masked_writes_arg=None):
        self.slave   = dfi.Interface(addressbits, bankbits, nranks, databits, nphases)
        self.master  = dfi.Interface(addressbits, bankbits, nranks, databits, nphases)
        csr1_dfi     = dfi.Interface(addressbits, bankbits, nranks, databits, nphases)
        self.intermediate   = dfi.Interface(addressbits, bankbits, nranks, databits, nphases)

        self.ext_dfi     = dfi.Interface(addressbits, bankbits, nranks, databits, nphases)
        self.ext_dfi_sel = Signal()

        prefixes = [""] if not with_sub_channels else ["A_", "B_"]

        if memtype == "DDR5":
            csr2_dfi     = dfi.Interface(14, 1, nranks, databits, nphases, with_sub_channels)
            ddr5_dfi     = dfi.Interface(14, 1, nranks, databits, nphases)

            if masked_writes_arg is None:
                masked_writes  = False
                if databits//2//strobes in [8, 16]:
                    masked_writes = True
            else:
                assert isinstance(masked_writes_arg, bool)
                masked_writes = masked_writes_arg
                assert not masked_writes or databits//2//strobes in [8, 16]

            adapters = [DFIPhaseAdapter(phase, masked_writes) for phase in self.intermediate.phases]
            self.submodules += adapters
            self.master = dfi.Interface(14, 1, nranks, databits, nphases, with_sub_channels)

        extra_fields = []
        if memtype == "DDR5":
            extra_fields.append(
                CSRField("mode_2n", size=1, values=[
                    ("``0b0``", "In 1N mode"),
                    ("``0b1``", "In 2N mode (Default)"),
                ], reset=0b1)
            )
            for prefix in prefixes:
                extra_fields.append(
                    CSRField(prefix+"control", size=1, values=[
                        ("``0b1``", prefix+"Cmd Injector"),
                    ], reset=0b0)
                )

        self._control = CSRStorage(fields=[
            CSRField("sel",     size=1, values=[
                ("``0b0``", "Software (CPU) control."),
                ("``0b1``", "Hardware control (default)."),
            ], reset=0b1), # Defaults to HW control.
            CSRField("cke",     size=1, description="DFI clock enable bus"),
            CSRField("odt",     size=1, description="DFI on-die termination bus"),
            CSRField("reset_n", size=1, description="DFI clock reset bus"),
        ] + extra_fields,
        description="Control DFI signals common to all phases")

        if memtype == "DDR5":
            self._force_issue = CSR()

        if memtype != "DDR5":
            for n, phase in enumerate(csr1_dfi.phases):
                setattr(self.submodules, "pi" + str(n), PhaseInjector(phase, write_latency))
            # # #

            self.comb += [
                Case(self._control.fields.sel, {
                    # Software Control (through CSRs).
                    # --------------------------------
                    0: csr1_dfi.connect(self.intermediate),
                    # Hardware Control.
                    # -----------------
                    1: # Through External DFI.
                        If(self.ext_dfi_sel,
                            self.ext_dfi.connect(self.intermediate)
                        # Through LiteDRAM controller.
                        ).Else(
                            self.slave.connect(self.intermediate)
                        ),
                })
            ]
            for i in range(nranks):
                self.comb += [phase.cke[i].eq(self._control.fields.cke) for phase in csr1_dfi.phases]
                self.comb += [phase.odt[i].eq(self._control.fields.odt) for phase in csr1_dfi.phases if hasattr(phase, "odt")]
            self.comb += [phase.reset_n.eq(self._control.fields.reset_n) for phase in csr1_dfi.phases if hasattr(phase, "reset_n")]
            self.comb += [self.intermediate.connect(self.master)]

        else: # memtype == "DDR5"
            self.comb += [
                # Hardware Control.
                # -----------------
                # Through External DFI
                If(self.ext_dfi_sel,
                    self.ext_dfi.connect(self.intermediate)
                # Through LiteDRAM controller.
                ).Else(
                    self.slave.connect(self.intermediate)
                ),
            ]

            for prefix in prefixes:
                setattr(self.submodules, prefix.lower()+"cmdinjector",
                    CmdInjector(
                        phases=csr2_dfi.get_subchannel(prefix),
                        force_issue=self._force_issue.re,
                        masked_writes=masked_writes))

            # DRAM controller is not DFI compliant. It creats only single wrdata_en/rddata_en strobe,
            # but DFI requires wrdata_en/rddata_en per each data slice,
            # so in BL16 it should create 8 and in BL8 , it should do 4

            # We need to store at least 16 wrdata_en and rddata en.
            # Code assumes that wrdata_en/rddata_en are transmitted
            # in the same DFI cycle and in the phase as WRITE/READ commands
            data_en_depth = max(16//nphases + 1, 2)

            data_en_delays = [None] * data_en_depth

            for i in range(data_en_depth):
                assert data_en_delays[i] == None
                data_en_delays[i] = []
                for _ in range(nphases):
                    _input  = Signal(2)
                    _output = Signal(2)
                    self.comb += _output.eq(_input)
                    if i:
                        tap_line = TappedDelayLine(signal=_input, ntaps=i)
                        self.submodules += tap_line
                        self.comb += _output.eq(tap_line.output)
                    assert i <= data_en_depth, (i, data_en_depth)
                    data_en_delays[i].append((_input, _output))

            for i, adapter in enumerate(adapters):
                _bl8_acts = []
                _bl16_acts = []
                origin_phase = self.intermediate.phases[i]
                for j in range(4):
                    phase_num = (i+j)  % nphases
                    delay     = (i+j) // nphases
                    _input, _ = data_en_delays[delay][phase_num]
                    _bl8_acts.append(_input.eq(_input | Cat(origin_phase.wrdata_en, origin_phase.rddata_en)))

                for j in range(8):
                    phase_num = (i+j)  % nphases
                    delay     = (i+j) // nphases
                    _input, _ = data_en_delays[delay][phase_num]
                    _bl16_acts.append(_input.eq(_input | Cat(origin_phase.wrdata_en, origin_phase.rddata_en)))

                self.comb += [
                    If(adapter.bl16,
                        *_bl16_acts,
                    ).Else(
                        *_bl8_acts,
                    )
                ]

            for ddr5_phase, inter_phase in zip(ddr5_dfi.phases, self.intermediate.phases):
                self.comb += [
                    ddr5_phase.wrdata.eq(inter_phase.wrdata),
                    ddr5_phase.wrdata_mask.eq(inter_phase.wrdata_mask),
                    inter_phase.rddata.eq(ddr5_phase.rddata),
                    inter_phase.rddata_valid.eq(ddr5_phase.rddata_valid),
                ]
            for i in range(data_en_depth):
                for (_, _output), phase in zip(data_en_delays[i], ddr5_dfi.phases):
                    self.comb += [
                        phase.wrdata_en.eq(phase.wrdata_en | _output[0]),
                        phase.rddata_en.eq(phase.rddata_en | _output[1]),
                    ]

            # DDR5 has commands that take either 1 or 2 CA cycles.
            # It also has the 2N mode, that is enabled by default.
            # It stretches single CA packet to 2 clock cycles. It is necessary when CA and
            # CS aren't trained. Adapter modules from phy/ddr5/commands.py solve
            # translation from the old DDR4 commands to DDR5 type. If an adapter
            # creates 2 beat command, and command was in phase 3 and DFI has 4
            # phases, we have to carry next part of command to the next clock cycle.
            # This issue is even more profound when 2N mode is used. All commands
            # will take 2 or 4 cycles to be correctly transmitted.

            depth = max(4//nphases + 1, 2)

            delays = [None] * depth

            for i in range(depth):
                assert delays[i] == None
                delays[i] = []
                for _ in range(nphases):
                    _input = Signal(14+nranks, reset=2**nranks-1)
                    tap_line = TappedDelayLine(signal=_input, ntaps=i+1)
                    self.submodules += tap_line
                    delays[i].append((_input, tap_line))

            address_for_phase = [None] * len(ddr5_dfi.phases)
            cs_n_for_phase = [None] * len(ddr5_dfi.phases)
            for i in range(len(address_for_phase)):
                address_for_phase[i] = []
                cs_n_for_phase[i] = []
            for i, adapter in enumerate(adapters):
                # 0 CA0 always
                # 1 CA0 if 2N mode or CA1 if 1N mode
                # 2 CA1 if 2N mode
                # 3 CA1 if 2N mode

                phase = ddr5_dfi.phases[i]
                _address = Signal.like(phase.address)
                address_for_phase[i].append(_address)
                _cs_n = Signal.like(phase.cs_n, reset=2**len(phase.cs_n)-1)
                cs_n_for_phase[i].append(_cs_n)
                self.comb += [
                    If(adapter.valid,
                        _address.eq(adapter.ca[0]),
                        _cs_n.eq(adapter.cs_n[0]),
                    ),
                    phase.reset_n.eq(self._control.fields.reset_n),
                    phase.mode_2n.eq(self._control.fields.mode_2n),
                ]

                phase_num = (i+1) % nphases
                delay     = (i+1) // nphases
                if delay:
                    _input, _ = delays[delay-1][phase_num]
                    self.comb += If(self._control.fields.mode_2n & adapter.valid,
                        _input.eq(Cat(adapter.cs_n[1], adapter.ca[0])),
                    ).Elif(adapter.valid,
                        _input.eq(Cat(adapter.cs_n[1], adapter.ca[1])),
                    )
                else:
                    phase = ddr5_dfi.phases[phase_num]
                    _address = Signal.like(phase.address)
                    address_for_phase[phase_num].append(_address)
                    _cs_n = Signal.like(phase.cs_n, reset=2**len(phase.cs_n)-1)
                    cs_n_for_phase[i].append(_cs_n)
                    self.comb += If(self._control.fields.mode_2n & adapter.valid,
                        _address.eq(adapter.ca[0]),
                        _cs_n.eq(adapter.cs_n[1]),
                    ).Elif(adapter.valid,
                        _address.eq(adapter.ca[1]),
                        _cs_n.eq(adapter.cs_n[1]),
                    )

                for j in [2,3]:
                    phase_num = (j+i) % nphases
                    delay     = (i+j) // nphases # Number of cycles to delay
                    if delay:
                        _input, _ = delays[delay-1][phase_num]
                        self.comb += If(self._control.fields.mode_2n & adapter.valid,
                            _input.eq(Cat(adapter.cs_n[j//2], adapter.ca[j//2])),
                        )
                    else:
                        phase = ddr5_dfi.phases[phase_num]
                        _address = Signal.like(phase.address)
                        address_for_phase[phase_num].append(_address)
                        _cs_n = Signal.like(phase.cs_n, reset=2**len(phase.cs_n)-1)
                        cs_n_for_phase[i].append(_cs_n)
                        self.comb += If(self._control.fields.mode_2n & adapter.valid,
                            _address.eq(adapter.ca[j//2]),
                            _cs_n.eq(adapter.cs_n[j//2]),
                        )

            for i in range(depth):
                for j, ((_, delay_out), phase) in enumerate(zip(delays[i], ddr5_dfi.phases)):
                    cs_n_for_phase[j].append(delay_out.output[0:nranks])
                    address_for_phase[j].append(delay_out.output[nranks:-1])

            for i, phase in enumerate(ddr5_dfi.phases):
                self.comb += phase.address.eq(reduce(or_, address_for_phase[i]))
                self.comb += phase.cs_n.eq(reduce(and_, cs_n_for_phase[i]))

            if with_sub_channels:
                self.submodules += ddr5_dfi.create_sub_channels()
                ddr5_dfi.remove_common_signals()

            self.comb += [
                Case(self._control.fields.sel, {
                    # Software Control (through CSRs).
                    # --------------------------------
                    0: [
                        Case(getattr(self._control.fields, prefix+"control"), {
                            1: [cp.connect(mp) for cp, mp in zip(csr2_dfi.get_subchannel(prefix), self.master.get_subchannel(prefix))],
                            0: [mp.cs_n.eq(Replicate(1, nranks)) for mp in self.master.get_subchannel(prefix)], # Use DES on unselected channels
                        }) for prefix in prefixes
                    ] + [
                        phase.reset_n.eq(self._control.fields.reset_n) for phase in self.master.phases if hasattr(phase, "reset_n")
                    ] + [
                        phase.mode_2n.eq(self._control.fields.mode_2n) for phase in self.master.phases if hasattr(phase, "mode_2n")
                    ],
                    # Hardware Control.
                    # -----------------
                    1: ddr5_dfi.connect(self.master),
                })
            ]
