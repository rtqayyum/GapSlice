"""Explicit power/bandwidth accounting for the first revision diagnostic.

This is an analytical ablation, not an NR PHY implementation. Each attempt
occupies b PRBs for one 0.5 ms slot. All coextensive interferers spread their
fixed total power across the same b PRBs; fading/decoding are handled by the
caller. It deliberately isolates allocation-dependent thermal noise from
the legacy fixed-reference-bandwidth SINR. Other interference occupancies,
control channels, discrete transport blocks and correlated fading remain
separate validation obligations.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RadioBudget:
    prbs_per_slot: int
    slot_s: float = 0.0005
    deadline_s: float = 0.010
    subcarrier_hz: float = 30000.0
    subcarriers_per_prb: int = 12
    tx_power_dbm: float = 23.0
    tx_gain_db: float = 3.0
    rx_gain_db: float = 3.0
    noise_figure_db: float = 9.0

    def __post_init__(self):
        if self.prbs_per_slot < 1 or self.slot_s <= 0 or self.deadline_s <= 0:
            raise ValueError("Positive bandwidth, slot length and deadline required")

    @property
    def deadline_slots(self):
        return math.floor(self.deadline_s / self.slot_s + 1e-12)

    @property
    def resource_upper_bound(self):
        """Optimistic PRB-slot capacity before overhead and link conflicts."""
        return self.prbs_per_slot * self.deadline_slots

    def total_noise_dbm(self, allocated_prbs):
        if not 1 <= allocated_prbs <= self.prbs_per_slot:
            raise ValueError("Allocation must fit the configured slot bandwidth")
        bandwidth = allocated_prbs * self.subcarriers_per_prb * self.subcarrier_hz
        return -174.0 + 10.0 * math.log10(bandwidth) + self.noise_figure_db

    def sinr_db(self, desired_pathloss_db, interferer_pathloss_db, allocated_prbs):
        """Coextensive fixed-total-power users; all powers integrated over b PRBs."""
        noise = 10.0 ** (self.total_noise_dbm(allocated_prbs) / 10.0)
        received_power_dbm = self.tx_power_dbm + self.tx_gain_db + self.rx_gain_db
        desired = received_power_dbm - desired_pathloss_db
        interference = sum(10.0 ** ((received_power_dbm - pl) / 10.0)
                           for pl in interferer_pathloss_db)
        return desired - 10.0 * math.log10(noise + interference)
