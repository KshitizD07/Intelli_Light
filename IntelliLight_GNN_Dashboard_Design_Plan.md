# IntelliLight GNN Dashboard Design Plan

## Vision

The dashboard should not merely *look* futuristic---it should make a
city-scale traffic AI understandable, observable, and trustworthy.

The interface is designed around a simple principle:

> **The graph shown on screen is the city's road network.**

Every node represents an intersection. Every edge represents a road
connecting intersections.

This is an operational dashboard intended for traffic operators,
engineers, researchers, and city administrators.

------------------------------------------------------------------------

# Primary Goals

-   Visualize the entire deployed road network.
-   Display live traffic conditions.
-   Communicate that optimization is happening globally rather than
    independently.
-   Make decisions understandable (XAI).
-   Provide operational controls & deterministic failsafe indicators.
-   Remain clean and professional rather than "sci-fi".

------------------------------------------------------------------------

# Layout

     ---------------------------------------------------------
    | Header                                                  |
    -----------------------------------------------------------
    | Left Sidebar |              Graph View      | Right Pane |
    |              |                              |            |
    |              |                              |            |
    |              |                              |            |
    -----------------------------------------------------------
    | Bottom Timeline / Events / Playback                    |
    -----------------------------------------------------------

------------------------------------------------------------------------

# Header

Contains:

-   Deployment name
-   Current simulation/live mode
-   Current model version (e.g. GNN vs ILPS)
-   Last inference timestamp
-   System health & Sensor Quality Index (SQI)
-   Emergency alert indicator & Active Failsafe count

------------------------------------------------------------------------

# Left Sidebar

Navigation

-   Overview
-   City Graph
-   Analytics
-   Events
-   Incidents
-   Intersections
-   Performance
-   Settings

Filters

-   Congestion
-   Emergency Vehicles
-   Closed Roads
-   Active Overrides & Failsafes
-   Construction
-   Predicted Congestion (N-Hop)

Search

-   Jump directly to an intersection.

------------------------------------------------------------------------

# Central Graph Canvas

This is the heart of the application.

## Graph

Nodes = intersections

Edges = roads

The layout must match the actual deployed city topology (supporting arbitrary topologies, e.g. 5-way intersections).

Pan

Zoom

Mini-map

Selection rectangle

------------------------------------------------------------------------

# Node States

Each node shows:

-   Current signal state & stream weights
-   Queue level
-   Average waiting time
-   Current throughput
-   Emergency status
-   Failsafe / Reflex state (Active vs Global AI Mode)
-   Sensor reliability status (e.g., package loss or glare)

Color

Green

Healthy

Yellow

Moderate congestion

Orange

Heavy congestion

Red

Critical congestion

Grey

Offline

Node Border Highlights

Red / Pulse Border

Deterministic Failsafe "Reflex" Triggered (Starvation preemption active)

Blue / Glow Border

Emergency Vehicle Preemption active

------------------------------------------------------------------------

# Edge States

Roads visualize

Traffic density

Average speed

Vehicle flow

Predicted load (N-Hop influence)

Road closure / incident

Edge thickness

Represents traffic volume.

Edge Style

Solid

Standard connection

Dashed/Flashing

GNN Message/Attention Propagation path

------------------------------------------------------------------------

# Live Animations

Animations should represent real events only.

Examples

-   Traffic flow moving along edges.
-   Small message pulses after inference (showing GNN aggregation).
-   Congestion spreading (Attention / N-Hop influence propagation).
-   Signal phase transitions.
-   Emergency vehicle propagation.

Avoid decorative particles.

------------------------------------------------------------------------

# Graph Intelligence Layer

The graph should feel alive and represent GNN mechanics.

Examples

N-Hop Message Passing

After every inference, show visual pulses propagating *N* hops outwards to represent GNN spatial message passing and prediction influence.

Influence / Attention propagation

Select an intersection to overlay the "GNN Attention Sphere" showing which nearby edges/nodes have the highest weights in its current decision.

------------------------------------------------------------------------

# Right Information Panel

Selecting an intersection opens details.

Contents

Intersection ID & Type (3-way, 4-way, 5-way)

Control State (GNN Optimization Mode / Safety Reflex Active / Manual Override)

Dynamic Stream Weights (AI confidence for non-conflicting traffic streams)

Remaining green/override time

Current queue & Starvation wait times (by lane)

Incoming/Outgoing roads & Sensor Reliability (SQI)

Emergency vehicles in neighborhood

Last decision time

Historical trend

Override controls (Force Safe-Green, Toggle Failsafe Thresholds)

------------------------------------------------------------------------

# Analytics Views

Network statistics

-   Average wait
-   Throughput
-   Queue distribution
-   Vehicles processed
-   Network utilization
-   Reflex Intervention Rate (How often failsafe overrides GNN)

Charts

-   Hourly traffic
-   Queue history
-   Congestion map
-   Decision frequency & Failsafe activation timelines

------------------------------------------------------------------------

# Timeline

Interactive playback.

Features

Pause

Replay

Speed control

Jump to timestamp

Compare two moments.

Useful for demonstrations and debugging.

------------------------------------------------------------------------

# Event Feed

Chronological events.

Examples

-   Congestion detected
-   Emergency vehicle detected
-   Safety Reflex Triggered (Lanes starved $\ge 90$s)
-   Manual override
-   Road closure
-   Traffic restored

Each event links directly to the corresponding intersection.

------------------------------------------------------------------------

# Operational Controls

Operators can

-   Pause simulation
-   Resume
-   Toggle overlays
-   Change visualization mode (Density vs GNN Attention vs Queue)
-   Enable diagnostics
-   Export snapshots

------------------------------------------------------------------------

# Overlay Modes

Traffic Density

Queue Length

Average Waiting Time

Predicted Congestion (GNN N-Hop Forecast)

Signal Phase & Stream Weights

Emergency Vehicles

Failsafe / Reflex Active Zones

Road Closures

Infrastructure Status & Sensor Quality Index

Only one heavy overlay should be active at once.

------------------------------------------------------------------------

# Performance Indicators

Top panel cards

-   Active Intersections
-   Vehicles in Network
-   Average Delay
-   Average Speed
-   Throughput
-   Inference Time
-   Active Emergencies
-   Failsafe Overrides Active

------------------------------------------------------------------------

# Visual Language

Dark theme

Minimal glow

Professional typography

Subtle motion

Consistent spacing

Avoid excessive neon effects.

------------------------------------------------------------------------

# Suggested Technology

Frontend

-   React
-   TypeScript
-   React Flow (or Cytoscape.js)
-   D3 (analytics)
-   Framer Motion
-   Three.js only where it adds value

Realtime

-   WebSockets

Maps

-   OpenStreetMap
-   MapLibre

Charts

-   Apache ECharts

------------------------------------------------------------------------

# Future Expansion

Without changing the backend model, the dashboard should already
anticipate:

-   Multiple cities
-   Regional clustering
-   Hierarchical graph visualization
-   Graph Attention overlays
-   Historical comparison
-   Digital twin mode
-   Incident replay
-   Multi-user operators
-   Role-based access
-   AI explanation panels

------------------------------------------------------------------------

# Design Philosophy

The dashboard should answer three questions immediately:

1.  What is happening now?
2.  Why is it happening? (XAI / GNN Attention)
3.  What is the system doing about it? (GNN decisions vs Deterministic Safety Reflex overrides)

Every animation, color, and interaction should reinforce those answers
rather than simply making the interface appear futuristic.

The goal is to create a dashboard that feels like the operational
control center of an intelligent city while remaining grounded in real
traffic data and meaningful visualizations.

