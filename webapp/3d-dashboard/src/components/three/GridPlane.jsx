import React from 'react';
import { Grid } from '@react-three/drei';

export default function GridPlane({ size = 100, divisions = 50 }) {
  return (
    <group position={[0, -2, 0]}> {/* Place slightly below the nodes */}
      <Grid 
        args={[size, size]} 
        cellSize={size / divisions} 
        cellThickness={0.5} 
        cellColor="#004e59" // Dark cyan
        sectionSize={size / (divisions / 5)} 
        sectionThickness={1} 
        sectionColor="#00e5ff" // Bright cyan for major grid lines
        fadeDistance={40} 
        fadeStrength={1.5}
        infiniteGrid
      />
    </group>
  );
}
