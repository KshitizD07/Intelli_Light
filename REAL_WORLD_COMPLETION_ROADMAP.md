# Intelli-Light: Real-World Completion Roadmap (Surtrac-Class Challenge)

This document is a practical, enterprise-style “do this in order” checklist to take this repo from a SUMO+RL research prototype to a real-world traffic-signal control product that can be benchmarked against systems like Surtrac and deployed safely.

It is based on what exists in the repo today, and what is clearly incomplete (empty modules, placeholders, and un-wired “hooks”).

Last reviewed: 2026-05-27

---

## 0) Current State (What You Have)

Working in-sim (SUMO) components:
- ILPS environment and training/eval entrypoints:
  - `rl/per_phase_env.py` (ILPS env)
  - `training/train_ilps.py`, `training/evaluate_ilps.py`
  - `main.py` (CLI wrapper)
- Centralized/legacy path still present:
  - `rl/multi_agent_env.py`, `training/train_rl.py`, `training/train_rl_4phase.py`, `training/evaluate_model.py`
- SUMO lifecycle wrapper:
  - `simulation/sumo_env.py`, `simulation/route_generator.py`, `simulation/realistic_traffic.py`
- Some evaluation machinery and baselines exist, but not Surtrac:
  - `training/baseline_controllers.py`, `training/evaluation_engine.py`, `training/metrics_calculator.py`
- Web backend skeleton exists (FastAPI + Redis), but it is not wired to ILPS runtime:
  - `webapp/main.py` (+ static HTML pages)

Known incomplete pieces (blocking “real-world”):
- Real-world sensing stack is missing: `perception/*` is empty.
- Real-world forecasting stack is missing: `prediction/*` is empty.
- Real-world controller integration + failsafe is missing: `deployment/*` is empty.
- RL “runtime” integration modules are missing: multiple empty files under `rl/`.
- Emergency vehicle handling is a placeholder in the ILPS env (it is always False today).
- The “override” (human-in-the-loop) concept exists only as a local decision log; it is not actually applied.
- Benchmarking against Surtrac is not implemented (no Surtrac controller, no apples-to-apples harness).

---

## 1) Define the Product Spec and “Surtrac Challenge” Benchmark (Before More Code)

Role in your goal:
You cannot “beat Surtrac” or sell deployments without a rigorous, repeatable definition of success, constraints, and operational boundaries.

Deliverables (add these files):
- `docs/PRODUCT_REQUIREMENTS.md`
  - Define intersections supported (4-phase only vs general NEMA/TS2), detectors available, pedestrian phases, emergency preemption policy, coordination scope, latency budget, and minimum safety invariants.
- `docs/BENCHMARK_PROTOCOL.md`
  - Define scenarios, networks, demand profiles, randomness control (seeds), metrics, statistical testing, and fairness rules.
- `docs/SAFETY_CASE.md`
  - Define required safety constraints, failure modes, and evidence required to claim “safe to pilot”.

Expected completion criteria:
- “Definition of Done” for a benchmark run: fixed network(s) + fixed scenario set + fixed metrics + reproducible results artifact.

Repo touchpoints:
- Use config surfaces in `configs/parameters.py` (and extend as needed) rather than hardcoding.

---

## 2) Implement a Surtrac-Class Baseline (Simulation First)

Role in your goal:
If you can’t run a credible baseline “like Surtrac” in the same simulator, you can’t make a defensible claim that Intelli-Light competes.

What’s incomplete:
- There is no Surtrac baseline controller in the repo today. Existing baselines are more generic (e.g., Max-Pressure / Fixed-Timer) and evaluation for ILPS does not compare against baselines.

Files to implement/extend (in order):
1. `training/baseline_controllers.py`
   - Add a `SurtracLikeController` (or `ScheduleDrivenController`) implementation.
   - Expected behavior (minimum):
     - Per-phase, rolling-horizon scheduling using predicted arrivals (or measured queues if you defer prediction).
     - Decision objective aligned to Surtrac-style delay minimization and coordination.
     - Deterministic mode for repeatability (given same inputs).
2. `training/evaluation_engine.py`
   - Ensure it can evaluate:
     - ILPS env + ILPS model (Discrete action) AND
     - baseline controller(s) on the same episode/scenario/network.
   - Today, ILPS evaluation is separated (`training/evaluate_ilps.py`) and doesn’t do baseline comparisons.
3. `training/evaluate_ilps.py`
   - Extend to run: `SurtracLikeController`, `MaxPressureController`, `FixedTimerController` beside ILPS.
   - Output a single JSON artifact with all controllers and metrics for each scenario.
4. `training/metrics_calculator.py`
   - Complete the emergency-related metric TODO if emergency priority is part of your claim:
     - TODO exists: “Calculate emergency clearance time…”.

Expected completion criteria:
- A single command produces a benchmark report comparing ILPS vs Surtrac-like vs Max-Pressure vs Fixed-Timer on:
  - mean delay / mean wait, throughput, max wait, fairness/imbalance, stops, and (if enabled) emergency clearance time.

---

## 3) Fix the ILPS Environment Gaps That Block “Production Claims”

Role in your goal:
Your ILPS architecture can be a good scaling story, but right now key features are described in README yet not actually present in the env’s state/reward plumbing.

### 3.1 Emergency Vehicle Prioritization Is Not Implemented in ILPS

What’s incomplete (today):
- `rl/per_phase_env.py`:
  - Observation `[12] emergency_flag` is explicitly a “placeholder”.
  - Rewards are computed with `emergency_active=False` and `emergency_direction=None`.
  - Dashboard snapshot always sets `"emergency_flag": False`.

What to implement:
- `rl/per_phase_env.py`
  - Implement emergency detection in-sim (TraCI-based) for training/eval:
    - Identify emergency vehicles by ID prefix or vehicle type.
    - Determine direction/approach (N/S/E/W) to set `emergency_direction`.
    - Populate obs emergency flag for the active junction.
  - Feed emergency info into `reward_calcs[i].calculate_reward(...)`.
- `rl/reward_function.py`
  - Ensure emergency bonus/penalty actually triggers when emergency is present and waiting.

Expected completion criteria:
- Unit/integration test that inserts an emergency vehicle into a route and verifies:
  - obs flag toggles,
  - reward changes as expected,
  - controller responds (phase durations adjust) under a deterministic policy.

### 3.2 “Override Interface” Exists Only as Logging, Not Control

What’s incomplete (today):
- `rl/per_phase_env.py` logs decisions to `self.decision_log`, but there is no mechanism to accept overrides and apply them.

What to implement:
- Decide the real override contract (where commands arrive from):
  - For sim: Redis queue used by `webapp/main.py` (`intellilight_commands`) is an existing candidate.
- Implement in `rl/per_phase_env.py`:
  - A method to poll override commands (or accept injected overrides) and apply them to `_phase_actions` before `_execute_phase_parallel`.
  - Audit trail fields in decision events: deadline, applied, final duration.

Expected completion criteria:
- End-to-end demo: dashboard sends an override for next decision window and you can see it applied in sim + recorded in logs.

---

## 4) Build the Real-World Runtime Layer (This Repo Is Missing It)

Role in your goal:
Simulation code is not a field controller. Real deployment needs a runtime that:
1) reads detectors/cameras,
2) estimates state,
3) runs inference,
4) issues safe commands to the signal controller,
5) fails safe.

### 4.1 Deployment Modules (EMPTY, Must Be Implemented)

Files that are currently empty (0 bytes):
- `deployment/controller.py`
- `deployment/failsafe.py`

What they should become:
- `deployment/controller.py`
  - A hardware-agnostic control API + one or more concrete adapters:
    - “ControllerAdapter” interface: set phase, set splits/durations, hold, release, etc.
    - Implementation targets (choose based on your market):
      - NTCIP-over-SNMP/UDP/TCP gateway
      - Vendor SDK integration
      - A “shadow mode” adapter that logs commands but does not actuate (for pilots)
  - Strict validation: never issue illegal phase transitions; enforce min green/all-red.
- `deployment/failsafe.py`
  - A state machine that triggers fallback when invariants are violated:
    - comms loss, inference timeout, detector faults, queue explosion, max-wait breach
  - Fallback behaviors:
    - revert to fixed-time plan,
    - or revert to actuated control,
    - or “flash” mode depending on jurisdiction (often not something you can unilaterally choose).

Expected completion criteria:
- “Shadow mode” run on live feeds for N days with no control output, producing:
  - latency stats, missing data rates, predicted vs observed queues, and safe/no-crash operation.
- A gated transition from shadow → advisory → limited control.

### 4.2 RL Runtime Hooks (EMPTY, Must Be Implemented or Deleted)

Files that are currently empty (0 bytes):
- `rl/action_handler.py`
- `rl/agent_communication.py`
- `rl/edge_case_handler.py`
- `rl/genetic_optimizer.py`

What’s incomplete / what role they play:
- `rl/action_handler.py`
  - Role: translate model outputs (duration index) into a controller command, applying safety envelopes and local policy.
  - Expected: clamp durations, enforce min/max, handle “hold” semantics, handle ped calls, handle coordination rules.
- `rl/agent_communication.py`
  - Role: multi-intersection coordination channel (message bus / neighbor state exchange) for real world.
  - Expected: define the data contract and transport (Redis, NATS, gRPC, etc.) and version it.
- `rl/edge_case_handler.py`
  - Role: deterministic handling of “unknown unknowns”: detector dropout, conflicting inputs, stale phase state, cabinet rejects command.
  - Expected: explicit rules that override ML outputs in unsafe/invalid states; comprehensive logging.
- `rl/genetic_optimizer.py`
  - Role: optional offline optimizer for fixed-time plans or hyperparameters; not required for first field pilot.
  - Expected: either implement for plan generation, or remove to reduce surface area.

Expected completion criteria:
- A runnable “runtime loop” that can operate without SUMO:
  - `Sense -> Estimate -> Decide -> Actuate -> Monitor -> Log`
  - With unit tests for action validation and failsafe triggers.

---

## 5) Build the Real-World Sensing Stack (Currently Missing)

Role in your goal:
Surtrac-class systems live or die on detection quality. Right now the repo has no implemented perception.

Files that are currently empty (0 bytes):
- `perception/vehicle_detector.py`
- `perception/data_augmentation.py`

What’s expected:
- `perception/vehicle_detector.py`
  - Pick the supported sensor modalities (don’t try all at once):
    - loop detectors / radar feeds (simpler, common)
    - video detection (harder, more flexible)
  - Provide a stable output contract:
    - per-approach counts, occupancy/queue length estimate, speed, classification (optional), timestamps, confidence.
  - Include calibration hooks (camera homography, lane mapping) if video is used.
- `perception/data_augmentation.py`
  - Only needed if you train/finetune detection models; otherwise delete and use off-the-shelf detectors with calibration.

Expected completion criteria:
- A replayable ingestion pipeline from recorded sensor data that produces the same state vectors used by control.

---

## 6) Add Short-Horizon Prediction (Optional for First Pilot, Required for “Surtrac-Like” Claims)

Role in your goal:
Surtrac relies on near-term arrival prediction/scheduling. If you want a direct head-to-head, you need comparable forecasting quality (even if crude initially).

Files that are currently empty (0 bytes):
- `prediction/traffic_prediction.py`

What’s expected:
- Implement at least one predictor:
  - naive: extrapolate from current flows/queues,
  - or time-series: ARIMA/ETS,
  - or learned: lightweight sequence model.
- Output contract: expected arrivals per approach over a horizon (e.g., 30–120s), with uncertainty.

Expected completion criteria:
- Predictor is used by `SurtracLikeController` (baseline) and optionally by Intelli-Light for lookahead features.

---

## 7) Network/Intersection Modeling for the Real World (Missing)

Role in your goal:
SUMO network files are not a city’s intersection inventory. You need a canonical intersection model mapping lanes, phases, ped calls, detector IDs, and controller channels.

File that is currently empty (0 bytes):
- `simulation/traffic_network.py`

What it should become:
- A “network model” module (not necessarily SUMO-specific) that defines:
  - approaches, lanes, movements, permitted phases, min greens, clearance times,
  - mapping from sensors to movements,
  - mapping from controller outputs to phases/groups.

Expected completion criteria:
- Same intersection model can be used in:
  - SUMO adapter (for simulation),
  - real controller adapter (for deployment),
  - dashboard visualization (for ops).

---

## 8) Make the Webapp an Ops Console (Currently a Skeleton)

Role in your goal:
Enterprise deployment needs observability, audit logs, versioning, and safe control surfaces. Current webapp is a demo scaffold and does not yet operate ILPS or deployment.

Known incomplete parts:
- `webapp/dashboard.py` is empty (0 bytes).
- `webapp/main.py` has placeholders and legacy wiring:
  - Scenario mapping is `pass`.
  - Training command calls `training/train_rl.py` (legacy), not ILPS.
  - Inference latency is a placeholder value.

What to implement (minimum):
1. `webapp/dashboard.py`
   - Define backend services/helpers:
     - auth (even basic), role-based access (view vs control),
     - audit logging,
     - model registry (which model is active where).
2. `webapp/main.py`
   - Add ILPS endpoints:
     - start/stop ILPS training: call `main.py train-ilps ...` or import `training/train_ilps.py`.
     - run ILPS eval and store results artifacts.
   - Implement scenario mapping (WEEKEND/EVENING_RUSH/MORNING_RUSH) to env settings consistently with `configs/parameters.py`.
   - Implement a real telemetry schema:
     - environment snapshot, decisions, overrides, failsafe state, detector health.
   - Replace placeholder “latency” with measured inference timing (p50/p95/p99).

Expected completion criteria:
- A deployable ops console that supports:
  - selecting active model,
  - shadow mode vs control mode,
  - per-intersection status,
  - override with audit trail,
  - exportable reports for stakeholders.

---

## 9) Testing, Safety Gates, and Release Engineering (Missing as a Program)

Role in your goal:
Selling and deploying requires reliability evidence. Right now there is no visible test suite or CI pipeline in this repo.

What to add:
- `tests/` (new):
  - unit tests for action validation, failsafe triggers, emergency handling, and deterministic replay.
  - integration tests that run a short SUMO episode headless.
- CI configuration (choose one):
  - GitHub Actions workflow, or equivalent internal CI.
- Packaging:
  - `pyproject.toml` (or tighten `requirements.txt`) and pinned dependency sets.

Expected completion criteria:
- “One command” to run:
  - linters, unit tests, and a smoke simulation.

---

## 10) Practical Next Actions (Concrete Order You Can Follow)

1. Write `docs/PRODUCT_REQUIREMENTS.md` + `docs/BENCHMARK_PROTOCOL.md`.
2. Implement `SurtracLikeController` in `training/baseline_controllers.py`.
3. Extend `training/evaluate_ilps.py` to run baselines side-by-side.
4. Implement emergency handling end-to-end in `rl/per_phase_env.py` + `rl/reward_function.py` and add a test.
5. Decide and implement override plumbing (Redis queue) into `rl/per_phase_env.py`.
6. Implement `simulation/traffic_network.py` (intersection model) so sim and real can share structure.
7. Implement `deployment/controller.py` (shadow-mode first) + `deployment/failsafe.py`.
8. Implement `rl/action_handler.py` + `rl/edge_case_handler.py` for runtime safety envelopes.
9. Upgrade webapp to an ops console (`webapp/dashboard.py`, fix `webapp/main.py` to support ILPS and runtime telemetry).
10. Add `tests/` + CI + release packaging.

---

## Appendix: Incomplete/Empty Files (Audit List)

Empty (0 bytes) today:
- `deployment/controller.py` (must implement hardware adapter and actuation API)
- `deployment/failsafe.py` (must implement failsafe state machine + fallback)
- `perception/vehicle_detector.py` (must implement sensor ingestion + detection contract)
- `perception/data_augmentation.py` (optional; implement or remove)
- `prediction/traffic_prediction.py` (must implement arrivals forecasting for Surtrac-like baseline)
- `rl/action_handler.py` (must implement action-to-command translation + constraints)
- `rl/agent_communication.py` (must implement coordination messaging contract/transport or remove)
- `rl/edge_case_handler.py` (must implement rule-based overrides for invalid states)
- `rl/genetic_optimizer.py` (optional; implement for plan optimization or remove)
- `simulation/traffic_network.py` (must implement intersection/network model for sim+real)
- `webapp/dashboard.py` (must implement ops-console backend services)

Non-empty but explicitly placeholder/incomplete behavior:
- `rl/per_phase_env.py`:
  - emergency flag is a placeholder, emergency is always False, override is logging-only.
- `webapp/main.py`:
  - scenario mapping placeholder, uses legacy training entry, inference latency placeholder.
- `training/metrics_calculator.py`:
  - emergency clearance time metric TODO.

