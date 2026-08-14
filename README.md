# 🚦 Intelli-Light 3.0: Universal Adaptive Traffic Signal Control

> **Graph-Based Reinforcement Learning, Generative Traffic Modeling, and Deterministic Failsafes for Complex, Chaotic Urban Grids.**

---

## 🌟 Executive Summary

**Intelli-Light** is a state-of-the-art multi-agent adaptive traffic signal control system designed to solve heavy congestion, emergency vehicle delay, and unfair starvation in chaotic urban traffic environments (such as Indian metro networks like Lucknow).

By replacing rigid grid-based observation arrays with **Graph Neural Networks (GNN)**, **Spatio-Temporal MARL (GAT + LSTM)**, and **GAN-driven Generative Traffic Synthesis**, Intelli-Light achieves topology-agnostic control capable of managing 3-way, 4-way, 5-way, or 6-way non-standard intersections while coordinating city-wide green waves. 

To bridge the gap between AI research and physical road deployment, Intelli-Light embeds a **Deterministic Failsafe Watchdog Engine** and standard **NTCIP 1202 SNMP Hardware Controllers** for direct plug-and-play installation into municipal traffic cabinets.

---

## 🔥 Key Features & Capabilities

### 🧠 1. Graph Neural Networks (GNN) & ST-MARL Core
* **Topology-Agnostic GCN (`models/gnn_extractor.py`)**: PyTorch-based Graph Convolutional Network feature extractor that dynamically aggregates $N$-hop neighborhood states across variable-degree road networks.
* **Spatio-Temporal Graph Attention (`models/st_marl_model.py`)**: Combines Graph Attention Networks (GAT) with LSTM temporal encoders to capture both spatial neighbor interaction and historical queue trends over past timesteps.
* **Multi-Agent Parameter Sharing (ILPS)**: Scalable Multi-Agent Reinforcement Learning (MARL) enabling coordinated signal control across arbitrary city topologies without exploding observation spaces.

### 🎲 2. GAN & Generative Traffic Demand Pipeline
* **Generative Scenario & Flow Modeling**: Architecture supporting Generative Adversarial Networks (GANs) and domain randomization to synthesize realistic, non-stationary traffic demand patterns, peak rush-hour bursts, and vehicle flow distributions.
* **Stochastic Real-World Demand Generator (`simulation/realistic_traffic.py`)**: Simulates time-of-day demand curves (morning/evening rush hours, midday, night), random events (accidents, rain, road work, concert surges), directional imbalances, and $30\%$ stochastic volatility.
* **Automated Map Ingestion (`simulation/generate_lucknow.py`)**: Automated Overpass API pipeline downloading OpenStreetMap (OSM) spatial data for cities (e.g., Lucknow), converting via SUMO `netconvert`, and building dynamic route files via `randomTrips`.

### ⚖️ 3. Multi-Factor Production Reward Calculator (`rl/reward_function.py`)
* **Exponential Anti-Starvation Penalty**: Penalizes wait times exceeding 60 seconds exponentially ($-8.0 \times \text{excess}^{1.3}$), ensuring no vehicle is stranded indefinitely.
* **Emergency Vehicle Preemption**: $+100$ bonus for immediate emergency vehicle clearance and $-200$ penalty if emergency vehicles are delayed.
* **Surtrac-Class Green-Wave Coordination**: $+3.0$ arterial alignment bonus when adjacent junctions synchronize green phases along major corridors.
* **Pressure & Queue Stabilization**: Integrates Max-Pressure queue differentials to stabilize PPO learning convergence.

### 🛡️ 4. Deterministic Failsafe Engine & Hardware Integration
* **NTCIP 1202 Standard Controller (`deployment/controller.py`)**: Native SNMP communication implementing NTCIP 1202 OIDs (`phaseControlGroupHold`, `phaseControlGroupForceOff`, `phaseStatusGroupGreen`) for direct hardware interfacing with Siemens, Econolite, and Yunex traffic signal cabinets.
* **Shadow Mode Operations**: Run AI predictions in passive observation mode to build municipal trust prior to live actuation.
* **Deterministic Watchdog (`deployment/failsafe.py`)**: Hardware safety layer evaluating inference latency ($<0.5\text{s}$), queue capacity, max wait thresholds ($>120\text{s}$), and heartbeat timeouts ($2.0\text{s}$) to transition between `NORMAL`, `FALLBACK_SOFT` (fixed-timer), and `FALLBACK_HARD` (flashing hardware mode).

### 🔍 5. Explainable AI (XAI) Engine (`training/xai_engine.py`)
* **Natural Language Feature Attribution**: Converts high-dimensional observation tensors into readable explanations (e.g., *"Starvation risk: Vehicles on West approach waiting > 102s"*).
* **Liability & Audit Reports**: Generates priority-level summaries (`NORMAL`, `HIGH`, `CRITICAL`) for municipal engineers and safety compliance audits.

### 📊 6. Web Dashboards & 3D Network Visualizer (`webapp/`)
* **FastAPI + Async Redis Backend (`webapp/main.py`, `webapp/dashboard_backend.py`)**: Asynchronous WebSocket streaming (`/ws/live`, `/ws/telemetry`) broadcasting live simulation tick metrics.
* **Interactive 2D Monitoring Dashboard**: View live KPI meters, queue states, active failsafe events, and manually override intersection signal phases.
* **3D React + Three.js Graph Dashboard (`webapp/3d-dashboard/`)**: Interactive 3D visualization rendering GNN graph nodes, dynamic traffic edges, signal states, and particle effect flows.

---

## 🏗️ System Architecture

```
               +----------------------------------+
               |  OpenStreetMap / Overpass API   |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |   SUMO Network & Simulation      |
               |  (Lucknow / Random Grid Networks)|
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               | Generative Traffic Generator     |
               | (GAN / Stochastic Demand Curves) |
               +----------------------------------+
                                |
                                v
    +--------------------------------------------------------+
    |               Perception & Prediction                  |
    |      (Vehicle Detection, Queue & Flow Forecasting)     |
    +--------------------------------------------------------+
                                |
                                v
    +--------------------------------------------------------+
    |             GNN & ST-MARL Policy Engine                |
    |      (PyTorch GCN / Graph Attention + LSTM Memory)     |
    +--------------------------------------------------------+
                                |
                                v
    +--------------------------------------------------------+
    |           Deterministic Failsafe Watchdog             |
    |   (Latency, Starvation & Latency Hard-Boundary Checks) |
    +--------------------------------------------------------+
            |                                    |
            v                                    v
+-----------------------+            +-----------------------+
|  NTCIP 1202 Cabinet   |            | Live Web Dashboards   |
| (SNMP Physical TLC)   |            | (2D & 3D Three.js WS) |
+-----------------------+            +-----------------------+
```

---

## 📂 Repository Structure

```text
Intelli-Light/
├── main.py                     # Primary CLI entrypoint for GNN & ST-MARL tasks
├── configs/                    # System configurations, signal timings, and parameters
├── deployment/                 # Physical hardware deployment and safety guardrails
│   ├── controller.py           # NTCIP 1202 SNMP hardware bridge & Shadow Mode
│   └── failsafe.py             # Watchdog state machine (NORMAL / SOFT / HARD fallback)
├── docs/                       # Architectural specs and GNN manifesto
│   └── INTELLI_LIGHT_3_GNN_MANIFESTO.md
├── models/                     # Deep Learning neural feature extractors
│   ├── gnn_extractor.py        # PyTorch SimpleGCNLayer & BaseFeaturesExtractor
│   ├── st_marl_model.py        # Spatio-Temporal GAT + LSTM Feature Extractor
│   └── override_log.py         # Logging and model override utilities
├── perception/                 # Computer vision & vehicle detection pipeline
├── prediction/                 # Traffic prediction and flow forecasting
├── rl/                         # Gymnasium Environments & Reward logic
│   ├── sumo_gnn_env.py         # SUMO Graph-based multi-agent environment
│   ├── multi_agent_env.py      # Multi-agent traffic corridor environment
│   ├── reward_function.py      # Multi-factor production reward calculator
│   ├── gnn_env.py              # Architecture prototype Gym env
│   ├── real_world_env.py       # Real-world benchmark environment
│   ├── sumo_gnn_randomized_env.py # Environment with domain randomization
│   └── sumo_gnn_realistic_env.py  # Realistic traffic SUMO environment
├── routes/                     # Generated route definitions
├── simulation/                 # SUMO lifecycle, traffic & map generators
│   ├── generate_lucknow.py     # Real Lucknow OpenStreetMap downloader & compiler
│   ├── generate_random_map.py  # Synthetic network generator
│   ├── generate_single_intersection.py
│   ├── realistic_traffic.py    # Time-of-day demand & random traffic event generator
│   ├── route_generator.py      # Vehicle trip & demand matrix builder
│   └── sumo_env.py             # Core SUMO TraCI interface wrapper
├── training/                   # Model training, evaluation & explainability
│   ├── baseline_controllers.py # Max-Pressure, Surtrac-Like & Fixed-Timer baselines
│   ├── evaluation_engine.py    # Benchmark evaluation runner
│   ├── metrics_calculator.py   # Traffic & environmental metrics calculator
│   ├── train_gnn.py            # GNN model training script
│   ├── train_gnn_randomized.py # Domain-randomized GNN training script
│   ├── train_st_marl.py        # Spatio-Temporal MARL training script
│   ├── run_gnn_gui.py          # SUMO GUI demonstration launcher
│   └── xai_engine.py           # Explainable AI decision reasoning engine
└── webapp/                     # Web dashboards & visualization tools
    ├── main.py                 # FastAPI WebApp backend with WebSocket telemetry
    ├── dashboard_backend.py    # Live SUMO simulation backend service
    ├── static/                 # 2D Web Dashboard static assets
    └── 3d-dashboard/           # Modern 3D React + Three.js Graph Visualizer
```

---

## ⚡ Quick Start

### Prerequisites
* **Python 3.10+**
* **SUMO (Simulation of Urban MObility)**: Ensure `SUMO_HOME` environment variable is set.
* **Redis**: Required for FastAPI async WebSocket pub/sub telemetry.
* **Node.js & npm** (Optional, for 3D React Dashboard).

### 1. Installation
Clone the repository and install the dependencies:

```bash
git clone https://github.com/KshitizD07/demo_intellilight.git
cd demo_intellilight
pip install -r requirements.txt
```

---

## 💻 Usage & Commands

### 1. Unified CLI (`main.py`)

Run training, testing, and GUI demonstration workflows:

```bash
# Smoke test the SUMO GNN environment with random actions
python main.py test-sumo-gnn

# Train the Graph Neural Network (GNN) model on randomized maps
python main.py train-gnn

# Train the Spatio-Temporal MARL (GAT + LSTM) model
python main.py train-st-marl

# Launch the SUMO GUI GNN demonstration
python main.py gnn-gui
```

### 2. Launch the Web App & Real-Time Dashboards

Start the FastAPI telemetry server and SUMO backend:

```bash
# Launch FastAPI telemetry backend
uvicorn webapp.main:app --reload --port 8000
```

Access the **2D Interactive Dashboard** at:
`http://localhost:8000`

To launch the **3D React + Three.js Dashboard**:

```bash
cd webapp/3d-dashboard
npm install
npm run dev
```

### 3. Generate Real City Maps (Lucknow OSM)

Download and compile OpenStreetMap data for Lucknow:

```bash
python simulation/generate_lucknow.py
```

---

## 📊 Baseline Benchmarks & Evaluation

Intelli-Light includes built-in implementations of standard adaptive traffic control algorithms for rigorous benchmarking:

1. **Max-Pressure Controller (`MaxPressureController`)**:
   * Industry-standard Varaiya (2013) algorithm.
   * Dynamically serves approaches with maximum queue differential pressure.
2. **Surtrac-Like Controller (`SurtracLikeController`)**:
   * Schedule-driven cluster discharge algorithm.
   * Allocates green duration based on approaching vehicle cluster estimates.
3. **Fixed-Timer Controller (`FixedTimerController`)**:
   * Traditional static green schedule baseline.

To evaluate models and compare against baselines:

```bash
python -m training.evaluate_gnn
```

---

## 🛡️ Physical Deployment & Safety Testing

### Testing NTCIP 1202 SNMP Hardware Bridge

Test physical signal cabinet communication in **Shadow Mode** (non-actuating log mode):

```python
from deployment.controller import ShadowController

# Initialize shadow bridge to cabinet IP
controller = ShadowController(ip_address="192.168.1.100")

# Simulate RL action execution (Phase 1 for 15 seconds)
controller.apply_rl_decision(phase_idx=0, duration=15)
```

### Failsafe Watchdog Verification

```python
from deployment.failsafe import FailsafeWatchdog

watchdog = FailsafeWatchdog(max_inference_latency=0.5, max_wait_threshold=120)

# Validate action duration prior to hardware execution
safe_duration = watchdog.validate_action(
    duration=20, 
    inference_latency=0.08, 
    obs_snapshot={"queues": [10, 12, 8, 15], "waits": [30, 25, 40, 105]}
)
```

---

## 📜 License

This project is licensed under the terms of the [`LICENSE`](LICENSE) file.
