# Workspace Guidelines: Intelli-Light & Sentinel (Pinaka Studios)

## Core Mission
This repository houses two complementary intelligent urban mobility systems created by **KSHITIZ**:
1. **Intelli-Light 3.0**: Universal Adaptive Traffic Signal Control using Spatio-Temporal Multi-Agent Reinforcement Learning (GAT + LSTM), SUMO microscopic simulation, and NTCIP 1202 SNMP controllers.
2. **Sentinel**: City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking, Urban Traffic Analytics, and GNN-Augmented Intercept Orchestration (Targeting SIH26127 / Bharat Electronics Limited).

---

## Architectural Invariants & Separation of Concerns

1. **Intelli-Light Independence**:
   - Intelli-Light is a standalone production signal control system.
   - Sentinel operates as an asynchronous, decoupled layer alongside it.
   - Sentinel may **read** road network graphs (`simulation/lucknow_map/*.xml`) and **read** live GNN congestion state.
   - Sentinel interacts with traffic signals **only** via authorized phase override injection channels (`deployment/failsafe.py` / `FailsafeWatchdog`), never mutating Intelli-Light internal model weights or core control loops.

2. **Strict Development Rules**:
   - Creator name is always **KSHITIZ** (uppercase with 'Z').
   - Secular and universal tone: zero religious or mythological references; no em dashes.
   - Commit message convention: strictly follow `add: xyz`, `fix: xyz`, `update: xyz`, `create: xyz`.
   - Never remove or break existing unit tests; verify all tests pass (`pytest`) before committing.
   - All file links must use valid standard formatting.

---

## Execution & Verification Commands

- **Python Virtualenv**: `.\venv\Scripts\python.exe`
- **Run Tests**: `.\venv\Scripts\python.exe -m pytest sentinel/tests/ -v`
- **Run Sentinel Demo**: `.\venv\Scripts\python.exe -m sentinel --demo`
- **Run Sentinel Web Dashboard**: `.\venv\Scripts\python.exe -m sentinel.server --port 8888`
