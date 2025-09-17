import json
from dataclasses import dataclass
from typing import Optional, Dict, Any

from litedram.common import burst_lengths
from rowhammer_tester.scripts.utils import get_generated_file


@dataclass
class PHYSettings:
    phytype: str
    memtype: str
    databits: int
    dfi_databits: int
    nphases: int
    rdphase: int
    wrphase: int
    cl: int
    read_latency: int
    write_latency: int
    strobes: int
    nranks: int
    cwl: int
    cmd_latency: int
    cmd_delay: Optional[int]
    bitslips: int
    delays: int
    masked_write: bool
    with_alert: bool
    min_write_latency: int
    min_read_latency: int
    write_leveling: bool
    write_dq_dqs_training: bool
    write_latency_calibration: bool
    read_leveling: bool
    with_sub_channels: bool
    nibbles: int
    address_lines: int
    with_per_dq_idelay: bool
    with_address_odelay: bool
    with_clock_odelay: bool
    with_odelay: bool
    with_idelay: bool
    direct_control: bool
    t_ctrl_delay: int
    t_parin_lat: int
    t_cmd_lat: int
    t_phy_wrdata: int
    t_phy_wrlat: int
    t_phy_wrcsgap: int
    t_phy_wrcslat: int
    t_phy_rdlat: int
    t_rddata_en: int
    t_phy_rdcsgap: int
    t_phy_rdcslat: int
    soc_freq: int


@dataclass
class GeometrySettings:
    bankbits: int
    rowbits: int
    colbits: int
    addressbits: int

    def num_banks(self):
        return 2**self.bankbits

    def num_rows(self):
        return 2**self.rowbits


@dataclass
class TimingSettings:
    """
    Data class to store various DRAM timing parameters used in memory operations.

    Attributes:
        tRP (int): Row Precharge Delay - the minimum time between a precharge command and another row command.
        tRCD (int): Row to Column Delay - the minimum time between the row address being loaded and the data being available.
        tWR (int): Write Recovery Time - the minimum time from the last data write command to the precharge command.
        tWTR (int): Write to Read Delay - the minimum delay between a write and the next read command.
        tREFI (int): Refresh Interval - the typical interval between automatic refresh operations.
        tRFC (int): Refresh Cycle Time - the total time of a refresh operation.
        tFAW (int): Four Bank Activate Window - the maximum number of activate commands in a rolling window that can be issued.
        tCCD (int): Column to Column Delay - the minimum delay between subsequent column access commands.
        tCCD_WR (int): Write to Read Delay for different banks - minimum delay between last write and first read command when switching banks.
        tRTP (int): Read to Precharge Delay - minimum time from read command to precharge command.
        tRRD (int): Row to Row Delay - minimum time between activations of different rows.
        tRC (int): Row Cycle Delay - minimum time required before another access can be started to the same row.
        tRAS (int): Row Active Time - time that the row remains open before it must be closed.
        tZQCS (Optional[int]): ZQ Calibration Short command cycle time.
    """

    tRP: int
    tRCD: int
    tWR: int
    tWTR: int
    tREFI: int
    tRFC: int
    tFAW: int
    tCCD: int
    tCCD_WR: int
    tRTP: int
    tRRD: int
    tRC: int
    tRAS: int
    tZQCS: Optional[int]
    fine_refresh_mode: str

    def max_acts_per_trefi(self) -> int:
        return (self.tREFI - self.tRFC) // (self.tRP + self.tRAS)


@dataclass
class LiteDramSettings:
    cmd_buffer_depth: int
    cmd_buffer_buffered: bool
    read_time: int
    write_time: int
    with_bandwidth: bool
    with_refresh: int
    refresh_zqcs_freq: float
    refresh_postponing: int
    with_auto_precharge: bool
    address_mapping: str
    phy: PHYSettings
    geom: GeometrySettings
    timing: TimingSettings

    @staticmethod
    def from_generate_settings() -> "LiteDramSettings":
        json_file = get_generated_file("litedram_settings.json")
        return LiteDramSettings.from_json_file(json_file)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "LiteDramSettings":
        phy = PHYSettings(**data["phy"])
        geom = GeometrySettings(**data["geom"])
        timing = TimingSettings(**data["timing"])
        return LiteDramSettings(
            cmd_buffer_depth=data["cmd_buffer_depth"],
            cmd_buffer_buffered=data["cmd_buffer_buffered"],
            read_time=data["read_time"],
            write_time=data["write_time"],
            with_bandwidth=data["with_bandwidth"],
            with_refresh=data["with_refresh"],
            refresh_zqcs_freq=data["refresh_zqcs_freq"],
            refresh_postponing=data["refresh_postponing"],
            with_auto_precharge=data["with_auto_precharge"],
            address_mapping=data["address_mapping"],
            phy=phy,
            geom=geom,
            timing=timing,
        )

    @staticmethod
    def from_json_file(file_path: str) -> "LiteDramSettings":
        with open(file_path, "r") as file:
            data = json.load(file)
        return LiteDramSettings.from_dict(data)

    def get_dram_port_width_bits(self) -> int:
        """Calculates and returns the DRAM port width in bits."""
        return self.phy.nphases * self.phy.dfi_databits

    def get_dram_port_width_bytes(self) -> int:
        """Calculates and returns the DRAM port width in bytes."""
        return self.get_dram_port_width_bits() // 8

    def get_burst_length(self) -> int:
        """
        Calculates and returns the burst length based on the memory type.

        Burst length refers to the number of data words transferred in one burst during a read or write operation.
        Different DRAM types have different burst lengths.

        Returns:
            int: The burst length for the configured memory type.

        Raises:
            KeyError: If the memory type is not recognized.
        """
        if self.phy.memtype == "SDR":
            return self.phy.nphases
        else:
            try:
                return burst_lengths[self.phy.memtype]
            except KeyError:
                raise KeyError(f"Unknown memory type: {self.phy.memtype}")
