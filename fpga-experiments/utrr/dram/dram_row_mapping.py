from abc import ABC, abstractmethod


# Define the interface for internal on-die DRAM row mapping
class DramRowMapping(ABC):
    @abstractmethod
    def logical_to_physical(self, logical_row: int) -> int:
        """Translate a logical row to its physical row equivalent."""
        pass

    @abstractmethod
    def physical_to_logical(self, physical_row: int) -> int:
        """Translate a physical row to its logical row equivalent."""
        pass


class DirectDramRowMapping(DramRowMapping):
    def logical_to_physical(self, logical_row: int) -> int:
        """Directly returns the logical row as the physical row."""
        return logical_row

    def physical_to_logical(self, physical_row: int) -> int:
        """Directly returns the physical row as the logical row."""
        return physical_row


class MicronSamsungDramRowMapping(DramRowMapping):
    def logical_to_physical(self, logical_row: int) -> int:
        """Applies Samsung-specific bitwise manipulation on the logical row to map to the physical row."""
        bit3 = (logical_row & 8) >> 3  # Extracts the 3rd bit (from LSB)
        return logical_row ^ (bit3 << 1) ^ (bit3 << 2)

    def physical_to_logical(self, physical_row: int) -> int:
        """Reverses the Samsung-specific bitwise manipulation to map the physical row back to the logical row."""
        bit3 = (physical_row & 8) >> 3  # Extracts the 3rd bit (from LSB)
        return physical_row ^ (bit3 << 1) ^ (bit3 << 2)


mappings = {
    "direct": DirectDramRowMapping(),
    "micron": MicronSamsungDramRowMapping(),
    "samsung": MicronSamsungDramRowMapping(),
}


def get_dram_row_mapping(mapping_type: str) -> DramRowMapping:
    try:
        return mappings[mapping_type]
    except KeyError:
        raise ValueError(f"Unsupported DRAM mapping type: {mapping_type}")
