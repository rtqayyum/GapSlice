"""Default parameters for the GapSlice experiments.

Sources for standardized values:
  * 3GPP TS 22.186 V17.0.0, Table 5.2-1 (platooning, highest degree of
    automation): payload 50-1200 B, 30 msg/s, 10 ms end-to-end latency, 99.99 %
    reliability (the per-V2V-link application of the 99.99 % is ours).
  * 3GPP TR 37.885, Table 6.2.1-1: highway V2V LOS path loss
    PL = 32.4 + 20 log10(d) + 20 log10(fc[GHz]), shadow-fading std 3 dB;
    NLOSv vehicle-blockage loss mean 9 dB, std 4.5 dB (antennas below blocker).
Everything else is a modelling assumption and is listed in the paper's
simulation-setup table.
"""
import numpy as np

# ---------------- control loop ----------------
T = 1.0 / 30.0          # CAM / control period [s]  (30 msg/s, TS 22.186)
TAU = 0.010             # delivery deadline [s]     (10 ms, TS 22.186)
K_FALLBACK = 5          # consecutive losses before ACC fallback (~167 ms)
KP, KD = 0.2, 0.7       # CACC gains (Ploeg et al., T-ITS 2014)
ETA_DEFAULT = 0.30      # truck driveline time constant [s]
V0 = 80 / 3.6           # cruise speed [m/s]
TRUCK_LEN = 16.5        # [m]
R_STAND = 2.0           # standstill distance [m]

# contract tolerances (gain >= 1 at DC for any CACC, so "string stable"
# is defined with a small tolerance above 1)
GAMMA_UNIT = 1.0025     # gain ladder step: ladder = GAMMA_UNIT**j
GAMMA_LINK = GAMMA_UNIT ** 5  # per-vehicle bound (~1.0126)
GAMMA_H2T = GAMMA_LINK ** 4  # head-to-tail bound for a 5-truck platoon (~1.051)
H_ACC = 2.8             # smallest gap at which ACC (no V2V) is string stable (computed)

# gap grid offered to tenants [s]
H_GRID = np.round(np.arange(0.3, 1.51, 0.1), 2)

# ---------------- radio ----------------
FC_GHZ = 5.9
P_URLLC = 0.9999        # network-level SLA of the baseline (TS 22.186)
PAYLOAD_BITS = 1200 * 8 # 1200 B CAM (upper value of TS 22.186 range)
N_RE_PRB = 108          # data REs per PRB per slot (12 sc x 9 data symbols)
SE_MAX = 5.55           # max spectral efficiency [bit/RE] (64QAM, r=0.925)
M_MAX = 4               # max (blind, frequency-hopped) attempts within TAU
B_MAX = 4000            # search limit on PRBs per attempt
REUSE_D = 300.0         # Mode-1 co-channel reuse distance [m]
N_INTERF = 2            # co-channel interferers at REUSE_D (front/back)
SIGMA_LS_DB = 4.2       # large-scale std of SIR [dB] (3 dB link + 3 dB interferer)
EPS_LS = 0.05           # platoon-level outage share: all links meet the target 95 % of the time
N_LINKS_REF = 4         # links of the reference 5-truck platoon (per-link tables)


def eps_link(n_links):
    """Per-link outage share that guarantees the platoon-level availability
    1 - EPS_LS for a platoon with n_links V2V links (union bound: the
    platoon is unavailable only if some link is, so per-link shares that sum
    to EPS_LS suffice, whatever the correlation between the links)."""
    return EPS_LS / max(int(n_links), 1)


EPS_LINK_REF = eps_link(N_LINKS_REF)   # 1.25 % per link
RICE_K_DB = 3.0         # Rician K-factor of LOS V2V link (sensitivity: -inf, 10)
N_RX = 1                # receive antennas (sensitivity: 2, MRC)
BLOCK_MU_DB, BLOCK_SIGMA_DB = 9.0, 4.5  # NLOSv trailer blockage (TR 37.885)


def antenna_distance(h, v=V0):
    """Inter-antenna distance between consecutive trucks at time gap h."""
    return R_STAND + h * v + TRUCK_LEN
