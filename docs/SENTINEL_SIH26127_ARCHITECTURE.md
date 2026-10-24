# SENTINEL: City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking & Urban Traffic Analytics

> **Problem Statement ID:** SIH26127 / PSC26127  
> **Organization:** Bharat Electronics Limited (BEL)  
> **Theme:** Transportation & Logistics (Smart Automation)  
> **Platform Architect:** KSHITIZ (Pinaka Studios)

---

## 1. Executive Summary & Problem Context

Urban surveillance and traffic management infrastructure deployed across Indian cities currently suffers from the **siloed sensor problem**: thousands of CCTV and Automatic Number Plate Recognition (ANPR) cameras operate as isolated checkpoints. While individual cameras read license plates, municipalities and law enforcement agencies lack an automated city-wide spatial-temporal intelligence engine to:
1. Seamlessly stitch plate sightings into contiguous, street-snapped journeys.
2. Discriminate between rational route choices (e.g. detours caused by heavy traffic) and suspicious evasive behavior.
3. Actively intervene in city traffic to box in or funnel fleeing suspect vehicles without causing accidents.

**Sentinel** is an autonomous intelligence layer operating alongside **Intelli-Light 3.0**. While Intelli-Light coordinates traffic signals using Spatio-Temporal Multi-Agent Reinforcement Learning (GAT + LSTM), Sentinel ingests distributed camera sightings, models urban vehicle movement on the underlying road network graph, scores route anomalies using live GNN congestion telemetry, and provides a closed-loop traffic intercept capability.

---

## 2. Core Architectural Pillars

```
+-----------------------------------------------------------------------------------+
|                            SENTINEL SURVEILLANCE ENGINE                           |
+-----------------------------------------------------------------------------------+
|  [ Distributed Cameras ] ---> [ ALPR Pipeline ] ---> [ Multi-Frame Voter ]        |
|                                (YOLOv8 + OCR)         (Fuzzy Substitution)        |
|                                                              |                    |
|                                                              v                    |
|  [ Flagged Registry ] <============================ [ Event Bus ]                 |
|  (SQLite / Watchlist)                                        |                    |
|           |                                                  v                    |
|           |                                       [ Tracker Manager ]             |
|           |                                                  |                    |
|           v                                                  v                    |
|  [ Intercept Engine ] <--- [ GNN Telemetry ] <--- [ Anomaly Engine ]              |
|  (Markov Escape Path)      (Intelli-Light Live)   (Congestion-Adjusted)           |
|           |                                                  |                    |
|           v                                                  v                    |
|  [ Failsafe Watchdog ]                              [ Trajectory Store ]          |
|  (Emergency Preemption)                             (O-D Matrix Analytics)        |
+-----------------------------------------------------------------------------------+
```

### Pillar 1: High-Accuracy Multi-Frame ANPR Pipeline
- **Dual Operating Modes**:
  - `sumo`: TraCI-driven synthetic camera network placed across all traffic-light junctions on the Lucknow OpenStreetMap network for reproducible simulations and hackathon evaluations.
  - `video`: High-speed YOLOv8 license plate detector coupled with PaddleOCR (PP-OCR v4).
- **Multi-Frame Consensus Voting**: Eliminates single-frame OCR camera noise by aggregating reads across rolling frames (`VOTE_WINDOW = 3`).
- **Fuzzy Character Confusion Tolerance**: Uses RapidFuzz token matching to resolve frequent Indian plate OCR confusion pairs (`0` vs `D`, `1` vs `I`, `8` vs `B`, `5` vs `S`).

### Pillar 2: Spatial-Temporal Trajectory Reconstruction & Plausibility
- **Physical Road Snapping (`RoadSnapper`)**: Rather than rendering unrealistic straight lines between camera checkpoints, Sentinel traverses the SUMO physical edge graph to extract exact polyline geometries (`GeoJSON LineString`).
- **Kinematic Plausibility Watchdog**: Verifies that transition velocity between sequential sightings does not exceed physical roadway limits ($v \le 30 \text{ m/s}$), immediately flagging cloned plates or sensor teleportation anomalies.
- **Persistent Trajectory Store**: Thread-safe SQLite backend (`traces.db`) storing sightings, active trajectories, and computing real-time Origin-Destination (O-D) mobility matrices for urban planning.

### Pillar 3: GNN Congestion-Aware Anomaly Engine (The Key Differentiator)
Traditional surveillance systems flag any deviation from a vehicle's historical path as suspicious. This results in overwhelming false positive rates during rush hours when commuters take detours to avoid gridlock.

Sentinel solves this by cross-referencing route deviations with **Intelli-Light's live GNN congestion state**:
$$\text{Detour Justification} = f(\text{Queue}_{\text{bypassed}}, \text{Pressure}_{\text{bypassed}})$$
$$\text{Adjusted Detour Score} = \text{Deviation Ratio} \times (1.0 - \text{Detour Justification})$$

- If a driver bypasses a direct intersection that had a queue of 40 vehicles, the detour is recognized as rational traffic avoidance ($\text{Score} = 0.0$).
- If a driver takes a circuitous 30-minute detour around completely empty intersections ($\text{Queue} \le 3$), Sentinel recognizes the evasion and raises an alarm ($\text{Score} > 0.65$).

### Pillar 4: Tactical Traffic Intercept Orchestrator
When a stolen vehicle or wanted suspect is detected, authorized operators can trigger a traffic intercept directive:
1. **Markov Path Predictor**: Forecasts candidate escape intersections ahead of the target based on network topology transitions and vehicle heading.
2. **Perimeter Signal Overrides**: Holds downstream approaches in RED ("Red-Wall") while timing upstream phases to generate organic, harmless vehicle queues that box in the suspect.
3. **Failsafe Watchdog & Emergency Preemption Bridge**:
   - Intercept directives are safety-capped with auto-expiring TTLs (`INTERCEPT_TTL_S = 600s`).
   - Pedestrian minimum clearance intervals ($15\text{s}$) are strictly maintained.
   - **Emergency Preemption Priority**: If an ambulance or fire vehicle is detected on an approach, the intercept override is instantly suspended for that intersection, granting green wave priority.

### Pillar 5: Tamper-Evident Cryptographic Audit Trail
All tracking activations, alerts, and intercept directives are logged to an append-only audit ledger (`audit.jsonl`) with SHA-256 cryptographic hash chaining ($H_i = \text{SHA256}(D_i \parallel H_{i-1})$), ensuring non-repudiation and legal compliance.

---

## 3. SIH26127 Compliance Matrix

| Requirement Specification | Evaluated Capability | Sentinel Implementation |
|:--------------------------|:---------------------|:------------------------|
| **Multi-Camera Trajectory** | Link distributed camera sightings into a contiguous route | `sentinel/tracker/tracker.py` & `vehicle_trace.py` |
| **GIS Road Mapping** | Visualize paths along actual roadways, not straight lines | `sentinel/tracker/road_snapper.py` |
| **High-Accuracy ANPR** | Resilient plate extraction with substitution tolerance | `sentinel/alpr/voter.py` (RapidFuzz OCR voter) |
| **Blacklist Alarms** | Sub-100ms alerting on stolen / suspicious plates | `sentinel/registry.py` & `sentinel/ingestion/event_bus.py` |
| **Traffic Analytics** | Density heatmaps and Origin-Destination (O-D) matrix | `sentinel/tracker/trajectory_store.py` (`od_matrix`) |
| **Route Anomaly Scoring** | Detect detours, circling, loops, and extended stops | `sentinel/anomaly/scorer.py` |
| **Macro State Integration** | Factor city congestion into intelligence | `sentinel/anomaly/gnn_bridge.py` (Intelli-Light GNN telemetry) |
| **Intervention Capability** | Closed-loop response to suspect evasion | `sentinel/intercept/orchestrator.py` (NTCIP 1202 override) |
| **Safety Invariants** | Prevent accidents or ambulance blocking during intercept | `sentinel/intercept/failsafe_bridge.py` |
| **Audit & Governance** | Tamper-evident logging for investigative queries | `sentinel/data/audit.jsonl` (SHA-256 hash chaining) |

---

## 4. Grand Finale Live Demonstration Protocol

A 60-second self-contained demonstration scenario is built into the system:

```bash
# Execute turnkey scenario on Lucknow road grid:
python -m sentinel --demo
```

### Demonstration Steps:
1. **Network Initialization**: Loads Lucknow OpenStreetMap network with 8 traffic-light intersections and thousands of road segments.
2. **Normal Commute**: Vehicle `DL01AB9999` travels straight through intersections, recording low anomaly score ($0.133$).
3. **GNN Congestion-Aware Anomaly Detection**: Suspect vehicle `UP32AB1234` takes an unjustified detour around clear intersections. GNN bridge reports queue $= 2$. Anomaly score spikes to $0.812$, triggering a threat alarm.
4. **Stolen Vehicle Evasion & Intercept**: Stolen vehicle `UP32XY9999` is spotted. Operator authorizes intercept. Markov predictor calculates downstream perimeter intersections and locks them in RED. Signal overrides are displayed with remaining TTL countdown.
5. **Urban Analytics Rollup**: Origin-Destination trips and duration averages are displayed from the persistent store.

To launch the real-time GIS map interface:
```bash
python -m sentinel --web
# Open browser at http://localhost:8888
```
