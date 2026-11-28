from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    controller: str = 'hold'
    kp: float = .8
    kd: float = 1.8
    observer_bandwidth: float = 8.
    reference_rate: float = .15
    reference_acceleration: float = .08
    comfort_jerk: float = 2.5
    shield: bool = True
    idm_a: float = 1.4
    idm_b: float = 2.
    ccc_A: float = .4
    ccc_B: float = .6
    ccc_C: float = .5

    def check(self):
        if self.controller not in {'fused','hold','radar','idm','ccc','ccc_cbf'}:
            raise ValueError('Unknown registered controller')
        if min(self.kp,self.kd,self.observer_bandwidth,self.idm_a,self.idm_b,
               self.reference_rate,self.reference_acceleration,self.comfort_jerk)<=0:
            raise ValueError('Positive policy parameters required')
        if self.comfort_jerk>8: raise ValueError('Physical command jerk exceeded')


@dataclass(frozen=True)
class Model:
    horizon_s: float = 40.
    dt_s: float = .002
    control_s: float = .01
    ramp_start_s: float = 2.
    tracking_limit_m: float = 5.
    target_tolerance_m: float = 1.
    target_hold_s: float = 2.
    standstill_m: float = 2.
    truck_length_m: float = 16.5
    initial_speed_mps: float = 80/3.6
    speed_mode: str = 'mixture'
    eta_nominal: float = .35
    eta_mode: str = 'mixture'
    brake_mode: str = 'mixture'
    radio_mode: str = 'coded_lookup'
    rician_k_db: float = 3.
    data_namespace: str = 'contract-development-v1'


CONTEXTS = {
    'nominal': dict(radio='nominal', k_db=3., range_error_m=.10,
                    own_speed_error_mps=.01, relative_speed_error_mps=.04, own_acceleration_error_mps2=.02),
    'blocked': dict(radio='blocked', k_db=0., range_error_m=.10,
                    own_speed_error_mps=.01, relative_speed_error_mps=.04, own_acceleration_error_mps2=.02),
    'sensor_uncertain': dict(radio='correlated', k_db=6., range_error_m=.30,
                    own_speed_error_mps=.05, relative_speed_error_mps=.15, own_acceleration_error_mps2=.10),
}
# These are declared synthetic sensitivity regimes, not measured device bounds.
CONTROLLERS = ('hold','radar','fused','idm','ccc','ccc_cbf')
