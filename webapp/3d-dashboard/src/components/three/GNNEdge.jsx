import React, { useMemo } from 'react';
import * as THREE from 'three';
import { Line } from '@react-three/drei';

export default function GNNEdge({ id, start, end, lanes, overlayMode }) {
  // A glowing tube connecting intersections
  const points = useMemo(() => [
    new THREE.Vector3(start[0], 0, start[2]),
    new THREE.Vector3(end[0], 0, end[2])
  ], [start, end]);

  // Visuals
  // More lanes = thicker line
  const lineWidth = Math.max(1, lanes * 0.8);
  
  // Color depends on overlay mode. For now, a subtle cyan/purple mix.
  const color = overlayMode === 'attention' ? '#9d4edd' : '#00e5ff';
  
  // Opacity: if in attention mode, dashed lines. Otherwise solid glowing.
  const dashed = overlayMode === 'attention';

  return (
    <group>
      <Line 
        points={points}
        color={color}
        lineWidth={lineWidth}
        dashed={dashed}
        dashSize={1}
        gapSize={0.5}
        transparent
        opacity={0.3}
      />
      {/* Inner bright core */}
      <Line 
        points={points}
        color="#ffffff"
        lineWidth={lineWidth * 0.3}
        transparent
        opacity={0.5}
      />
    </group>
  );
}
