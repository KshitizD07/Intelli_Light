"""
Sentinel
========
City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking.

Runs as an independent process alongside Intelli-Light.
Reads from Intelli-Light's road graph and (optionally) its live GNN
congestion state, but NEVER modifies any Intelli-Light source file.

Entry point:
    python -m sentinel          # full pipeline (SUMO demo mode)
    python sentinel/main.py     # same
"""
