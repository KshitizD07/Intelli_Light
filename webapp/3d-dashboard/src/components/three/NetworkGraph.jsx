import React, { useMemo } from 'react';
import { Group } from 'three';
import GNNNode from './GNNNode';
import GNNEdge from './GNNEdge';
import ParticleBackground from './ParticleBackground';
import GridPlane from './GridPlane';

export default function NetworkGraph({ networkData, liveData, selectedNode, onNodeClick, overlayMode }) {
  
  // Transform geographical coordinates into 3D space coordinates
  const { positions, nodes, edges } = useMemo(() => {
    if (!networkData || !networkData.junctions || networkData.junctions.length === 0) {
      return { positions: {}, nodes: [], edges: [] };
    }

    const { junctions, edges: netEdges } = networkData;
    
    // Calculate bounding box to center and scale the graph
    let minLat = Infinity, maxLat = -Infinity;
    let minLng = Infinity, maxLng = -Infinity;
    
    junctions.forEach(j => {
      if (j.lat < minLat) minLat = j.lat;
      if (j.lat > maxLat) maxLat = j.lat;
      if (j.lng < minLng) minLng = j.lng;
      if (j.lng > maxLng) maxLng = j.lng;
    });

    const latRange = maxLat - minLat || 1;
    const lngRange = maxLng - minLng || 1;
    
    // Scale factors to map to a nice 3D scene size (e.g. 40x40 units)
    const SCALE = 40;
    
    const posMap = {};
    
    junctions.forEach(j => {
      // Map lat/lng to X/Z plane centered around 0,0
      const x = ((j.lng - minLng) / lngRange - 0.5) * SCALE;
      const z = -((j.lat - minLat) / latRange - 0.5) * SCALE; // Invert lat for Z axis
      posMap[j.id] = [x, 0, z];
    });

    return { positions: posMap, nodes: junctions, edges: netEdges };
  }, [networkData]);

  // Map live data into a quick lookup dictionary
  const liveNodesMap = useMemo(() => {
    const map = {};
    if (liveData && liveData.nodes) {
      liveData.nodes.forEach(n => {
        map[n.id] = n;
      });
    }
    return map;
  }, [liveData]);

  if (nodes.length === 0) return null;

  return (
    <group>
      {/* Visual Context */}
      <ParticleBackground count={1500} />
      <GridPlane size={100} divisions={50} />

      {/* Render Edges (Roads) */}
      {edges.map((edge) => {
        const fromPos = positions[edge.from_junction];
        const toPos = positions[edge.to_junction];
        if (!fromPos || !toPos) return null;
        
        return (
          <GNNEdge 
            key={edge.id}
            id={edge.id}
            start={fromPos}
            end={toPos}
            lanes={edge.lanes || 2}
            overlayMode={overlayMode}
          />
        );
      })}

      {/* Render Nodes (Intersections) */}
      {nodes.map((node) => {
        const pos = positions[node.id];
        const lData = liveNodesMap[node.id] || {}; // Fallback if no live data yet
        
        return (
          <GNNNode
            key={node.id}
            id={node.id}
            name={node.name}
            position={pos}
            liveData={lData}
            isSelected={selectedNode === node.id}
            onClick={() => onNodeClick(selectedNode === node.id ? null : node.id)}
            overlayMode={overlayMode}
          />
        );
      })}
    </group>
  );
}
