# System Architecture, Technical Design & Workflow Diagrams

> **Platforms:** Intelli-Light 3.0 & Sentinel  
> **Platform Architect:** KSHITIZ (Pinaka Studios)  
> **Target Problem Statements:** Urban Traffic Optimization & SIH26127 / Bharat Electronics Limited (BEL)

---

## 1. High-Level System Architecture

This diagram visualizes the macroscopic interaction between the physical or simulated city network (SUMO Lucknow), the autonomous traffic signal controller (**Intelli-Light 3.0**), and the surveillance and tactical intercept layer (**Sentinel**).

```mermaid
flowchart TD
    subgraph CityGrid["City Road Network (SUMO / Physical Cabinets)"]
        OSM["OpenStreetMap Ingestion (Lucknow Metropolitan Network)"] --> NET["SUMO Net & Route Files (.net.xml, .rou.xml)"]
        NET --> DET["Inductive Loops, Radar & Camera Checkpoints"]
        SIG["Traffic Signal Heads (NTCIP 1202 Actuators)"]
    end

    subgraph IntelliLight["Intelli-Light 3.0: Adaptive Signal Control Core"]
        DET --> OBS["Dynamic Graph Topology & Queue Observations"]
        OBS --> GNN["Topology-Agnostic GNN / ST-MARL Policy (PyTorch)"]
        GNN --> PRE_ACT["Proposed Signal Action Duration"]
        PRE_ACT --> WATCHDOG["Deterministic Failsafe Watchdog (Latency, Starvation, EVP)"]
        WATCHDOG -->|Normal Mode| SIG
        WATCHDOG -->|Fallback Soft/Hard| SIG
    end

    subgraph SentinelEngine["Sentinel: City-Wide Surveillance & Intercept Engine"]
        DET --> VOTER["Multi-Frame Consensus OCR Voter (RapidFuzz Confusion Matrix)"]
        VOTER --> BUS["Asynchronous Event Bus (asyncio)"]
        BUS --> TRACKER["Tracker Manager & RoadSnapper (SUMO Graph Polyline)"]
        TRACKER --> STORE[("SQLite Trajectory Store (traces.db & O-D Matrix)")]
        TRACKER --> ANOMALY["Congestion-Aware Anomaly Engine"]
        ANOMALY --> REGISTRY[("Flagged Vehicle Registry (registry.db)")]
        REGISTRY --> INTERCEPT["Tactical Intercept Orchestrator"]
        INTERCEPT --> MARKOV["Markov Escape Path Predictor"]
        MARKOV --> TACTICAL_BRIDGE["Tactical Guidance Bridge (Progressive Metering & Choke)"]
    end

    %% Decoupled Interfaces
    WATCHDOG -.->|1. Real-Time Queue & Congestion Telemetry| ANOMALY
    TACTICAL_BRIDGE ==>|2. Controlled Phase Override Request| WATCHDOG
    INTERCEPT --> AUDIT[("Cryptographic Audit Ledger (SHA-256 Hash Chain)")]
```

---

## 2. Intelli-Light 3.0: Spatio-Temporal GNN & MARL Pipeline

This diagram shows how spatial connectivity (GCN/GAT) and temporal queue memory (LSTM) extract topology-invariant representations of complex multi-leg intersections.

```mermaid
flowchart LR
    subgraph InputTensors["Observation Space (Gymnasium spaces.Dict)"]
        NODE_FEAT["Node Features: Queues, Waits, Phases (N x 9)"]
        ADJ_MAT["Dynamic Adjacency Matrix (N x N)"]
        HIST_SEQ["Temporal Sequence T-Hops (T x N x 9)"]
    end

    subgraph SpatialLayers["Spatial Aggregation (GCN / GAT)"]
        GAT1["Graph Attention Layer 1 (Multi-Head Neighbor Attention)"]
        GAT2["Graph Attention Layer 2 (Context Aggregation)"]
    end

    subgraph TemporalLayers["Temporal Dynamics (LSTM)"]
        LSTM1["Recurrent LSTM Unit (Queue Trend Memory)"]
        FC_PROJ["Dense Projection (features_dim = 128 / 256)"]
    end

    subgraph PolicyHeads["Actor-Critic Signal Policy"]
        ACTOR["Actor Head: Continuous Phase Priority Weights"]
        CRITIC["Critic Head: State-Value Baseline V(s)"]
    end

    NODE_FEAT --> GAT1
    ADJ_MAT --> GAT1
    GAT1 --> GAT2
    ADJ_MAT --> GAT2
    HIST_SEQ --> GAT1
    GAT2 --> LSTM1
    LSTM1 --> FC_PROJ
    FC_PROJ --> ACTOR
    FC_PROJ --> CRITIC
```

---

## 3. Sentinel: High-Accuracy Multi-Frame ANPR & Tracking Pipeline

This diagram illustrates how raw camera sightings are denoised, validated, snapped to real roadways, and verified against physical vehicle dynamics.

```mermaid
flowchart TD
    RAW_CAM["Camera Sighting Read (Frame t, Plate String, Confidence)"] --> NORM["Normalize String (Uppercase, Strip Hyphens/Spaces)"]
    NORM --> VOTE_BUF["Rolling Frame Buffer (VOTE_WINDOW = 3)"]
    
    subgraph ConsensusVoter["Consensus Voting & Substitution Tolerance"]
        VOTE_BUF --> FUZZ["RapidFuzz Character Token Matching"]
        FUZZ --> SUBST["Substitute Indian Confusion Pairs (0/D, 1/I, 8/B, 5/S)"]
        SUBST --> COMMIT["Committed License Plate String"]
    end

    COMMIT --> KINEMATIC{"Kinematic Plausibility Check (v <= 30 m/s)"}
    KINEMATIC -->|Implausible Speed / Teleportation| CLONE_ALERT["Flag Sensor Teleportation / Cloned Plate"]
    KINEMATIC -->|Plausible Movement| SNAPPER["RoadSnapper: SUMO Edge Polyline Traversal"]
    
    SNAPPER --> GEOJSON["Contiguous GeoJSON LineString Trajectory"]
    GEOJSON --> DB[("SQLite Trajectory Store (traces.db)")]
    DB --> OD["Dynamic Origin-Destination (O-D) Matrix Analytics"]
```

---

## 4. GNN Congestion-Aware Route Anomaly Scoring Flow

The key innovation of Sentinel: evaluating whether a vehicle detour was rational or suspicious by querying Intelli-Light's live congestion state.

```mermaid
flowchart TD
    TRACE["Updated VehicleTrace (Junction Sequence & Sightings)"] --> DEV_CALC["Calculate Route Deviation Ratio: (Actual - Min) / Min"]
    
    DEV_CALC --> GNN_QUERY{"GNN Bridge: Bypassed Junctions Congested?"}
    
    GNN_QUERY -->|Max Bypassed Queue >= 25| JUST_FULL["Detour Justification = 1.0 (Severe Gridlock Avoidance)"]
    GNN_QUERY -->|10 <= Max Bypassed Queue < 25| JUST_HALF["Detour Justification = 0.5 (Moderate Congestion Avoidance)"]
    GNN_QUERY -->|Max Bypassed Queue < 10| JUST_ZERO["Detour Justification = 0.0 (Clear Roads Bypassed Without Reason)"]
    
    JUST_FULL --> ADJ_DEV["Adjusted Deviation Score = 0.0 (Rational Commute)"]
    JUST_HALF --> ADJ_DEV
    JUST_ZERO --> ADJ_DEV["Adjusted Deviation Score = Deviation Ratio x 1.0"]

    subgraph MultiComponentScorer["Weighted Anomaly Evaluation"]
        ADJ_DEV --> W1["Weight: 40% Route Deviation"]
        LOOP["Loop / Circling Check"] --> W2["Weight: 25% Loop Detection"]
        STOP["Extended Stop Check"] --> W3["Weight: 20% Unexplained Stop"]
        SPEED["Speed Profile Check"] --> W4["Weight: 15% Implausible Speed"]
    end

    W1 --> AGG["Aggregate Normalized Score [0.0, 1.0]"]
    W2 --> AGG
    W3 --> AGG
    W4 --> AGG

    AGG --> THRESH{"Score >= ANOMALY_DEVIATION_THRESHOLD (0.65)?"}
    THRESH -->|Yes| ALERT["Emit Anomaly Alert on Event Bus"]
    THRESH -->|No| LOG_NORM["Log Normal Vehicle Commute"]
```

---

## 5. Tactical Intercept Handshake & Queue Containment Sequence

This sequence diagram depicts the end-to-end communication lifecycle when an operator authorizes a tactical red-wall intercept on a flagged target vehicle.

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Operator (Lucknow Police ICCC)
    participant Sentinel as Sentinel Orchestrator
    participant Markov as Markov Path Predictor
    participant Bridge as Tactical Guidance Bridge
    participant Failsafe as Failsafe Watchdog & EVP Bridge
    participant Controller as Intelli-Light Adaptive Controller
    participant SUMO as SUMO Microscopic Network

    Operator->>Sentinel: Request Intercept (Plate: UP32XY9999, Mission: M-104)
    Sentinel->>Sentinel: Validate Token & Flagged Registry Entry
    Sentinel->>Markov: Predict Target Escape Corridor
    Markov-->>Sentinel: Downstream Target Junction: cluster_11823984553
    Sentinel->>Bridge: Deploy Tactical Containment Plan
    Bridge->>Failsafe: Request Signal Phase Override (ALL-RED Hold, TTL = 600s)
    
    alt Emergency Vehicle Present on Approach (EVP Active)
        Failsafe-->>Bridge: REJECT / SUSPEND (Emergency Vehicle Green Priority Clearance)
    else Safety Envelope Satisfied
        Failsafe->>Controller: Register Overridden TLS ID
        Controller->>Controller: Yield Target Junction Control to Sentinel
        Failsafe->>SUMO: Execute Traffic Light ALL-RED (Downstream Stop Line)
        Note over Controller,SUMO: Intelli-Light continues adaptive Max-Pressure on all other junctions
        SUMO->>SUMO: Lead civilian halts at stop line; civilian queue builds
        SUMO->>SUMO: Suspect decelerates behind queue via native Krauss car-following
        SUMO-->>Sentinel: Suspect velocity drops to 0.0 m/s (Halted for >= 3s)
        Sentinel->>Operator: APPREHENSION SUCCESSFUL (Suspect Boxed In)
        Sentinel->>SUMO: Remove Suspect Vehicle (Option A Apprehension)
        Sentinel->>Controller: Release TLS Override (Restore Program 0)
        Controller->>SUMO: Trigger Adaptive Green Extension (Disperse Civilian Queue)
    end
    Sentinel->>Sentinel: Append SHA-256 Hash Chained Record to audit.jsonl
```

---

## 6. Deterministic Failsafe Watchdog State Machine

This state diagram details how the hardware watchdog in [`deployment/failsafe.py`](file:///C:/Users/kshit/cs/project/Intelli-Light/deployment/failsafe.py) maintains physical safety boundaries and protects against software or communication failures.

```mermaid
stateDiagram-v2
    [*] --> NORMAL : System Boot & Initial Heartbeat

    NORMAL --> FALLBACK_SOFT : Inference Latency > 0.5s OR Max Wait > 120s
    FALLBACK_SOFT --> NORMAL : Latency Restored (< 0.5s) AND Queues Normalized

    NORMAL --> FALLBACK_HARD : Heartbeat Timeout > 2.0s OR Hardware Comms Loss
    FALLBACK_SOFT --> FALLBACK_HARD : Comms Lost During Soft Fallback

    FALLBACK_HARD --> NORMAL : Hardware Link Restored AND Manual Safety Reset

    state NORMAL {
        [*] --> ExecutingRLActions
        ExecutingRLActions --> ValidatingPedestrianClearance
        ValidatingPedestrianClearance --> ExecutingRLActions
    }

    state FALLBACK_SOFT {
        [*] --> FixedTimerSchedule
        FixedTimerSchedule --> StarvingApproachGreenCycle
    }

    state FALLBACK_HARD {
        [*] --> FlashingYellowHardwareMode
        FlashingYellowHardwareMode --> ManualOperatorIntervention
    }
```

---

## 7. Tactical Intercept Stages State Machine

This state diagram illustrates the progression of tactical stages defined in [`sentinel/intercept/tactical_bridge.py`](file:///C:/Users/kshit/cs/project/Intelli-Light/sentinel/intercept/tactical_bridge.py).

```mermaid
stateDiagram-v2
    [*] --> STANDBY : Target Flagged in Registry

    STANDBY --> METERING : Intercept Authorized & Target Distance > 250m
    METERING --> CHOKE : Target Distance 100m to 250m
    CHOKE --> CONTAINMENT : Target Halts Behind Queue (Speed < 0.2 m/s)
    
    STANDBY --> FUNNEL : Alternative Evasion Corridor Selected
    FUNNEL --> CHOKE : Suspect Guided into Choke Point

    CONTAINMENT --> STANDBY : Suspect Apprehended, Signals Restored to Green

    state METERING {
        [*] --> DownstreamGreenThrottled
        DownstreamGreenThrottled --> ControlledQueueFormation
    }

    state CHOKE {
        [*] --> SuspectApproachRed
        SuspectApproachRed --> CrossTrafficFlushed
    }

    state CONTAINMENT {
        [*] --> SuspectHaltedBehindPlatoon
        SuspectHaltedBehindPlatoon --> ApprehensionRemoval
    }
```

---

## 8. Core Component Class Structure

This class diagram represents the object-oriented structure and decoupling between Intelli-Light and Sentinel.

```mermaid
classDiagram
    class SUMOGraphTrafficEnv {
        +int n_nodes
        +ndarray adjacency
        +step(action)
        +reset()
    }

    class SimpleGCNLayer {
        +Linear linear
        +forward(x, adj) Tensor
    }

    class SpatioTemporalMARLExtractor {
        +GraphAttentionLayer gat1
        +LSTM lstm
        +forward(obs) Tensor
    }

    class EnhancedRewardCalculator {
        +RewardWeights weights
        +calculate_reward(queues, waits, arrived) float
    }

    class FailsafeWatchdog {
        +float max_inference_latency
        +float heartbeat_timeout
        +SystemState current_state
        +validate_action(duration, latency, obs) int
        +check_health() SystemState
    }

    class IntelliLightAdaptiveController {
        +int min_green
        +int max_green
        +step(traci_module, overridden_tls) list
        +get_scorecard() str
    }

    class PlateVoter {
        +str camera_id
        +int window
        +vote(plate, conf) Optional[str]
    }

    class RoadSnapper {
        +snap_route(junction_seq) list
        +to_geojson_feature(coords, props) dict
    }

    class AnomalyScorer {
        +GNNTelemetryBridge gnn_bridge
        +score(trace) float
        +explain(trace) dict
    }

    class GNNTelemetryBridge {
        +update_telemetry(junction_id, queue, pressure)
        +calculate_detour_justification(bypassed, ratio) float
    }

    class InterceptOrchestrator {
        +FlaggedVehicleRegistry registry
        +MarkovPathPredictor predictor
        +request_intercept(plate, junction, auth) InterceptMission
        +cancel_intercept(plate, by)
    }

    class SentinelFailsafeBridge {
        +FailsafeWatchdog watchdog
        +InterceptOrchestrator orchestrator
        +resolve_action(junction_id, duration, latency, evp) dict
    }

    SUMOGraphTrafficEnv --> SimpleGCNLayer
    SUMOGraphTrafficEnv --> FailsafeWatchdog
    SpatioTemporalMARLExtractor --> SimpleGCNLayer
    AnomalyScorer --> GNNTelemetryBridge
    SentinelFailsafeBridge --> FailsafeWatchdog
    SentinelFailsafeBridge --> InterceptOrchestrator
    InterceptOrchestrator --> RoadSnapper
```

---

## 9. Data Storage & Cryptographic Audit Ledger Entity-Relationship

This entity-relationship diagram shows the schemas of SQLite trace storage, the flagged vehicle registry, and the append-only SHA-256 audit ledger.

```mermaid
erDiagram
    SIGHTING {
        string sighting_id PK
        string plate FK
        string junction_id
        float timestamp
        float confidence
        float speed_mps
        float lat
        float lng
    }

    VEHICLE_TRACE {
        string plate PK
        float first_seen
        float last_seen
        float anomaly_score
        int total_sightings
        boolean is_flagged
    }

    FLAGGED_REGISTRY {
        string plate PK
        string flag_reason
        string authority
        boolean intercept_authorized
        float created_at
    }

    AUDIT_RECORD {
        string record_hash PK
        string prev_hash
        string action
        float timestamp
        string details_json
    }

    VEHICLE_TRACE ||--o{ SIGHTING : "records"
    FLAGGED_REGISTRY ||--o| VEHICLE_TRACE : "flags"
    FLAGGED_REGISTRY ||--o{ AUDIT_RECORD : "generates audit entry"
```

---

## 10. Summary of Architectural Guarantees

1. **Decoupled Autonomy**: Intelli-Light functions autonomously as a pure municipal traffic signal controller without requiring Sentinel.
2. **Context-Aware Analytics**: Sentinel never falsely classifies rush-hour traffic diversions as evasion because it consumes live GNN queue metrics.
3. **Deterministic Safety Boundary**: Hardware failsafes and emergency vehicle preemption strictly override software intercept requests.
4. **Legal Compliance**: Cryptographic SHA-256 hash chaining ensures that all surveillance tracking actions and signal overrides are non-repudiable and tamper-evident.
