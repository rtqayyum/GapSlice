# Conditional certificates for the complete redesign

Status: mathematical arguments with executable numerical checks, awaiting independent
review. This is not a machine-checked proof, a measured-vehicle certificate, a new
string-stability theorem, or evidence of journal acceptance. The method is a new
**candidate systems design**, called GapSlice-Cert in this repository. Its individual
ingredients have substantial prior art; novelty of the combination remains to be
established by a systematic comparison.

The earlier Guard pilot is retained unchanged. Its blocked-channel failures and
serial-scheduling restrictions motivated this redesign. Its Gaussian sensors and
2.5 m/s³ physical follower command-jerk restriction differ from the new model;
comparing their failure percentages as a controlled improvement would be invalid.
Every new comparator uses the same new plant, bounds, reference rules and shield.

## 1. Model, sensing, and entry conditions

For each vehicle, x'=v, v'=a while v>0, and a'=(u-a)/eta. Drivetrain acceleration
a is continuous; kinematic acceleration is zero during a standstill if a<0.
There is no backward motion. eta is fixed per vehicle in [0.25,0.45] seconds.
Commands lie in [-6,2] m/s², are held for Dc=0.01 s, and successive commands
change by at most Jc Dc, Jc=8 m/s³. Nominal comfort commands use Jc=2.5;
the backup may use the physical Jc=8. Report that comfort/safety tradeoff.

The total absolute sensing errors are bounded by 0.10 m for range, 0.01 m/s
for own speed, 0.04 m/s for relative speed, and 0.02 m/s² for acceleration.
These include the mathematical model's measurement/quantization uncertainty;
a deployment must establish bounds for its actual devices and computations.
Software simulation uses bounded uniform measurement noise, not the old Gaussian
noise. A quantized 30 Hz source releases at 0,40,70 ms each 100 ms plus a
qualified 10 ms phase. This exact release clock is shared by scheduler/replay.
The radio decoder/fading remain uncalibrated synthetic surrogates.

The guarantee requires a valid initial emergency-backup certificate for every
covered link, finite supported states, the physical/sensing assumptions above,
correct execution of the shield at the declared times, and no external impact.
The proof table supports initial speeds through 40 m/s; it need not certify
all possible states. An unsupported lookup denies nominal permission. A denied
lookup does not invalidate an already stored valid backup plan.

For the predecessor jerk argument, the post-command initial actuator mismatch
must satisfy |u0-a0| <= Jc Dc/(1-exp(-Dc/eta)). This is explicitly checked in
the simulator. Between subsequent updates the mismatch decays; at an update it
increases by at most Jc Dc. Induction gives

    |a'| <= Jc Dc / [eta (1-exp(-Dc/eta))] <= 8.162 < 9 m/s³.

The last expression is maximal at eta_min. Effective acceleration may jump
upwards at a stop. Its **one-sided lower jerk** remains at least -9 m/s³.
No assumption of symmetric bounded effective jerk at that jump is made.

## 2. Predecessor acceleration memory

Let y be measured predecessor velocity, formed from own speed plus relative
speed, so |y-vp|<=Ev=0.05 m/s. On a window T,

    ap(t) >= [y(t)-y(t-T)]/T - 2Ev/T - Ja T/2,  Ja=9.

Proof: ap(t)>=ap(s)-Ja(t-s); integrate s over [t-T,t], and bound the two
endpoint velocity errors. Upward acceleration jumps preserve this inequality.
A previous lower bound propagates by subtracting Ja times elapsed time. A
received acceleration packet provides a further lower bound
`packet_acceleration - Ea - Ja*age`. The maximum of valid lower bounds and -6
remains valid. Outward rounding is applied to these lower-bound calculations.
The ESO used for nominal prediction is separate and is not assumed convergent
for this safety result. Hold, radar, and fused comparators share this bound.

## 3. Backup displacement certificate

Use envelope step De=0.02 s and guard period Dg=0.04 s. At a checkpoint form an
upper ego state (speed, acceleration, command) and a lower predecessor state
(speed, acceleration) using the sensing bounds. Round ego a,u upwards and
predecessor a downwards on the stored axes. Monotonicity of the scalar dynamics
preserves these inequalities. Initial speed is not rounded to a grid.

There are two upper ego command sequences:

* emergency: immediate maximum admissible command braking;
* nominal prefix: any physically admissible commands for Dg, then braking.

The code constructs staircase upper commands for each entire envelope interval.
During the nominal prefix the upper command grows at the maximum physical
increment; during braking it decreases by the declared increment per envelope
step. The upper command on a braking interval is deliberately no lower than
the actual early-step braking command. It is conservative at the switching time.

For a constant command upper bound U, a positive-lag comparison gives, over De,

    a_next <= U + C5*(a_upper-U)
    Dv_upper = U De + C3*(a_upper-U),

where C5 encloses exp(-De/eta) and C3 encloses its integral. Choose the upper
coefficient for a nonnegative difference and lower coefficient otherwise.
An alternating Taylor enclosure with an explicit next-term remainder bounds
these coefficients using directed binary64 arithmetic; no assumed libm exp
error bound is needed. Supported ratios De/eta<=1 ensure decreasing terms.

Set Aplus=max(a_upper,U,0). Stop/restart events satisfy

    v_next <= max(0, v_upper+Dv_upper, De*Aplus)
    displacement_increment <= De*v_upper + (De²/2)*Aplus.

Without a stop, the first velocity expression bounds the exact lag solution;
after a stop, any restarted speed is at most De*Aplus. The displacement bound
holds throughout the interval even if the vehicle stops. The scalar recurrence
has a max-plus factorization: with S_k=sum(Dv_upper),

    v_k <= S_k + max(v0, max_{j<=k}(p_j-S_j)),  p_j=De*Aplus_j.

The tables store upper S, upper maxima using lower S inside subtraction, and
upper displacement-curvature prefixes. Nonnegative prefix sums use an explicit
floating summation error bound. This factorization supports continuous initial
velocities without a large velocity-grid approximation.

For the predecessor use acceleration lower bound
`max(-6, ap_lower - Ja*t)`. On each interval use its lower endpoint value,
clamp the lower velocity at zero and integrate the minimum endpoint lower
velocity. This yields lower displacement Qp_lower(t).

For every envelope interval [tk,tk+1], nonnegative speed implies

    Qego(t)-Qp(t) <= Qego_upper(tk+1)-Qp_lower(tk).

The final 12-second envelope state is checked for every acceleration/command
axis pair and maximum initial speed: both upper acceleration and upper command
are at most -5 m/s², and upper speed is at most 1e-5 m/s. Any remaining ego
travel is bounded by v_upper²/(2*5); predecessor future travel is nonnegative.
Thus the maximum of the interval bounds and terminal bound covers **all future
time**, including times between table knots.

Let B be 2 m plus this maximum nonnegative closure. If the sensed clearance
lower bound is at least B, the associated backup sequence preserves clearance
at least 2 m under the assumptions. Table hashes are checked by workers;
corrupt/incomplete tables and out-of-domain states are rejected.

### Stored-backup induction

Initially require the emergency certificate. At each guard checkpoint:

1. If a nominal-prefix certificate is valid, permit bounded nominal commands
   for at most Dg, with maximum braking as the certified continuation.
2. If no new certificate is valid, execute that previously certified braking
   continuation from the actual current command.
3. A valid new certificate can replace the old one; failure to find a new one
   never licenses a new nominal action or discards the old safe continuation.

A nominal-prefix witness covers every admissible command sequence during its
prefix, including the actual sequence. The actual command at the prefix end
is no larger than the witness upper command, so maximum braking from it is
bounded by the witness continuation. Induction preserves the existing future
clearance guarantee. Applying this pairwise on a chain preserves covered-link
clearance; packet delivery probabilities do not enter the argument.

The implementation records certificate coverage per link. Any observed breach
while covered aborts the scientific task with a nonzero status. Initial states
that fail certification count as outcome failures. Successful finite testing
supports implementation correctness but does not prove universal correctness.

## 4. Ideal tracking dynamics and an ISS witness

Define e=d-r0-hv and edot=dv-h*a-hdot*v. For an ideal, unsaturated, continuous
computed-input controller with correct eta and exact derivatives,

    u = a + eta/h * [ahat_p -(1+2hdot)*a - hddot*v + kd*edot + kp*e]

gives e''+kd e'+kp e = ap-ahat_p. For the actual sampled, noisy, clipped plant,
define Delta as the combined residual; the ideal identity is not claimed to
remove that residual. A useful conditional robustness statement is:

    z' = A z + B Delta, A=[[0,1],[-kp,-kd]], B=[0,1]^T,
    P12=1/(2kp), P22=(kp+1)/(2kp kd),
    P11=kd/(2kp)+(kp+1)/(2kd).

For kp,kd>0, det(P)=1/(4kp)+(kp+1)^2/(4kp kd²)>0, so P is positive definite,
and direct substitution gives A^T P+PA=-I. V=z^T Pz satisfies

    V' <= -V/(2 lambda_max(P)) + 2 ||PB||² |Delta|².

If |Delta|<=D, integrate this scalar inequality for an explicit exponentially
decaying transient and ultimate bound. `risk.nominal_certificate` checks the
algebraic witness. This is an ideal error-dynamics ISS result, **not a proof of
uniform string stability of the nonlinear sampled fleet**, and not a claim
that a numerical D has been established for every deployment.

## 5. Cyclic radio feasibility and integer quality bound

A profile declares absolute source phase, serial/parallel link scheduling,
PRBs, copies and copy geometry. Every phase is a separate simulated candidate.
No unqualified time-shift invariance is assumed. Payload fitting uses the
inherited declared transport/decoder surrogate. Its standards fidelity still
needs independent external validation.

Schedules repeat every 200 slots (100 ms). Each reservation lasts less than
one superframe and every relative copy ends within its release/deadline.
Checking three neighboring epochs suffices to detect any cyclic overlap:
translate an allegedly conflicting pair so one lies in the central epoch;
the other must lie in that epoch or one of its neighbors. An independent
slot checker checks frequency capacity, vehicle half-duplex use, packet jobs,
and deadlines across those epochs. Distinct tenants have distinct vehicles;
shared spectrum is globally conflict checked.

Admission uses integer benefit microseconds (floor of a conservative LCB) and
integer risk units with total budget 16. A separate multiple-choice knapsack
DP drops all radio conflicts and solves the resulting risk-only problem in
exact integer arithmetic. It bounds every feasible catalog allocation from
above. Every returned greedy/MILP incumbent is independently checked for
one choice per tenant, integer risk, and radio feasibility. If its value
attains the DP bound it is independently optimal for this **finite qualified
catalog**. Otherwise value/DP_bound is a certified lower bound on its catalog
approximation ratio. A solver's floating optimality status is reported
separately; no unproved global physical-network oracle claim is made.

## 6. Statistical outcome qualification

Freeze design choices using design data only. For each remaining candidate
and each predeclared environment, draw n=32768 independent episode replays for
calibration, with independent held-out test streams of the same size.
The primary tracking/clearance event is evaluated at 2 ms replay checkpoints;
continuous covered-link clearance is addressed by the separate backup proof.
Candidate common random numbers do not invalidate the union bound. Mathematical
statements assume iid episodes under the declared synthetic generator.

Risk labels are delta=u/1600, u in {1,2,4,8,16}. Let M include all candidate,
environment, label tests. Accept a label only when

    P[Bin(n,delta) <= observed_failures] <= 1/(25 M).

For any true risk greater than delta, stochastic monotonicity bounds false
acceptance by this level. Bonferroni then bounds any false label among the
finite family by 0.04. Acceptance uses exact Python integer binomial numerator
recursions and integer cross-multiplication, not floating tail comparisons.
An n too small even for zero failures yields rejection, not an exemption.
A domain label requires acceptance in every environment in that domain.

The episode reward is achieved time-average headway reduction, clipped to
[0,h_initial-h_target] and zeroed on any primary failure. It therefore assigns
zero maneuver credit to a steady-gap outside option. Hoeffding lower bounds
use a separate family error allocation 0.01 across all candidate/environment
reward bounds. Code applies a conservative numerical margin, but does not
claim formally verified transcendental arithmetic for this secondary bound.
The overall ideal-statistical risk-plus-reward family error is at most 0.05.

With simultaneously valid labels, a fleet with sum(u)<=16 has probability
of any episode failure at most 0.01 by another union bound, without requiring
independent tenants. This applies to the declared domain distribution, no
within-cell interference beyond the model, and admitted policies; it is not
a worst-case safety theorem or a guarantee under arbitrary distribution shift.
No further tuning is performed using held-out outcomes. Repeatedly redesigning
after seeing final test data requires a fresh final test protocol/namespace.

## 7. Prior art and unresolved novelty

Safety filters, input-delay vehicle safety, extended-state observers,
reference governors, learning-to-test, and cyclic resource packing are existing
ideas. Relevant primary starting points include:

* Molnar et al., [Input-to-State Safety with Input Delay in Longitudinal Vehicle
  Control](https://arxiv.org/abs/2205.14567).
* Liu et al., [Cooperative Extended State Observer Based Control of Vehicle
  Platoons With Arbitrarily Small Time Headway](https://arxiv.org/abs/2004.09778).
  The implementation here is inspired by observer ideas and is not labeled a
  faithful reproduction of that paper's controller.
* [A Robust, Efficient Predictive Safety Filter](https://arxiv.org/abs/2311.08496).
* [Backup-Based Safety Filters: A Comparative Review of Backup CBF, Model Predictive Shielding, and gatekeeper](https://arxiv.org/abs/2604.02401).
* [Learn then Test: Calibrating Predictive Algorithms to Achieve Risk Control](https://arxiv.org/abs/2110.01052).

The prospective contribution is the auditable coupling of packet-independent
backup feasibility, stale-information bounds, outcome-risk labels, achieved
maneuver value, qualified phases and independently checked admission bounds.
A paper must explain how this differs from existing co-design/safety-slicing
systems and evaluate faithful published baselines. The present implementation
alone does not settle that literature or publication question.
