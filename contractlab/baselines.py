"""Published equations with explicit native-model and adaptation boundaries.

IDM: Treiber, Hennecke & Helbing, PRE 62 (2000), Eq. (6)-(7),
https://arxiv.org/abs/cond-mat/0002177 .
CCC and time-headway CBF: Molnar, Orosz & Ames, CDC 2023,
https://arxiv.org/abs/2309.00074 , Eq. (2)-(3), (28)-(30).
The lagged, jerk-limited, changing-reference primary experiment is an adaptation;
the original paper's guarantee is NOT transferred to that plant.
"""
import numpy as np


def idm(distance, velocity, leader_velocity, headway, desired_speed, a=1.4, b=2., standstill=2.):
    distance = np.maximum(np.asarray(distance), 1e-3)
    v = np.maximum(velocity, 0.)
    approaching = v - leader_velocity
    desired_gap = standstill + np.maximum(0., v*headway + v*approaching/(2*np.sqrt(a*b)))
    return a*(1-(v/np.maximum(desired_speed,1.))**4-(desired_gap/distance)**2)


def ccc(distance, velocity, leader_velocity, leader_acceleration, kappa,
        A=.4, B=.6, C=.5, standstill=2., speed_limit=35.):
    desired = np.minimum(kappa*(distance-standstill), speed_limit)
    leader = np.minimum(leader_velocity, speed_limit)
    return A*(desired-velocity)+B*(leader-velocity)+C*leader_acceleration


def ccc_time_headway_filter(desired, distance, velocity, leader_velocity,
                            safe_headway=1.67, safe_distance=1., alpha=1., resistance=0.):
    # Native second-order model: h=(D-Dsf)/Th-v; hdot=(vL-v)/Th-u+p(v).
    h = (distance-safe_distance)/safe_headway-velocity
    upper = (leader_velocity-velocity)/safe_headway + resistance + alpha*h
    return np.minimum(desired, upper)


def adapted_nominal(policy, distance, velocity, leader_velocity, own_a, estimate,
                    lower_a, headway, desired_speed, standstill, eta, headway_rate=0., headway_acceleration=0.):
    if policy.controller=='idm':
        return idm(distance,velocity,leader_velocity,headway,desired_speed,
                   policy.idm_a,policy.idm_b,standstill)
    desired = ccc(distance,velocity,leader_velocity,estimate,1/headway,
                  policy.ccc_A,policy.ccc_B,policy.ccc_C,standstill)
    if policy.controller=='ccc_cbf':
        # Relative-degree-two extension for the lagged primary plant:
        # h=D-s0-Th*v, h''+2*w*h'+w^2*h>=0. This extension is OUR adaptation.
        h=distance-standstill-headway*velocity
        hd=leader_velocity-velocity-headway*own_a-headway_rate*velocity
        upper=own_a+eta/headway*(lower_a-(1+2*headway_rate)*own_a-
                                  headway_acceleration*velocity+2*hd+h)
        desired=np.minimum(desired,upper)
    return desired
