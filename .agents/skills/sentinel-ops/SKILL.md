---
name: sentinel-ops
description: >-
  Operations, testing, and execution workflows for Sentinel ANPR trajectory tracking,
  GNN congestion anomaly detection, and traffic intercept orchestration in Intelli-Light.
---

# Sentinel Operations & Execution Playbook

Use this skill when running simulations, executing unit tests, training trajectory models,
or starting the real-time web surveillance dashboard for Sentinel.

## 1. Environment & Setup

Ensure the active virtual environment at `.\venv` is used:
```powershell
& ".\venv\Scripts\python.exe" -m pip list
```

## 2. Running Test Suite
Execute the pytest suite covering registry, ALPR voter, trajectory tracking, anomaly scorer,
and intercept orchestration:
```powershell
cd "C:\Users\kshit\cs\project\Intelli-Light"
& ".\venv\Scripts\python.exe" -m pytest sentinel/tests/ -v
```

## 3. Running Live Demo
To launch the full synthetic camera multi-agent trajectory tracking demo on the Lucknow grid:
```powershell
& ".\venv\Scripts\python.exe" -m sentinel --demo
```

## 4. Starting Web Intelligence Dashboard
To launch the real-time GIS & 3D surveillance server:
```powershell
& ".\venv\Scripts\python.exe" -m sentinel.server --port 8888
```
