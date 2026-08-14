import React, { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';

export default function GNNNode({ id, name, position, liveData, isSelected, onClick, overlayMode }) {
  const meshRef = useRef();
  const ringRef = useRef();
  
  // Extract data with fallbacks
  const queue = liveData.queue || 0;
  const avgWait = liveData.avg_wait || 0;
  const controlMode = liveData.control_mode || 'GNN';
  const backpressure = liveData.backpressure || 0;
  const isEmergency = liveData.is_emergency || false;
  const hasFailsafe = liveData.active_failsafe || false;

  // Visual mapping
  // 1. Size based on queue
  const baseScale = 0.5;
  const targetScale = baseScale + (Math.min(queue, 80) / 80) * 1.5;
  
  // 2. Y-position based on backpressure (nodes float up when congested)
  const targetY = position[1] + (backpressure * 3);

  // 3. Color based on wait time
  const color = useMemo(() => {
    if (avgWait < 20) return new THREE.Color('#00f5d4'); // Green-Cyan
    if (avgWait < 45) return new THREE.Color('#ffb703'); // Amber
    if (avgWait < 90) return new THREE.Color('#fb8500'); // Orange
    return new THREE.Color('#ef233c');                   // Red
  }, [avgWait]);

  // 4. Glow ring color based on control mode
  const ringColor = useMemo(() => {
    if (hasFailsafe) return new THREE.Color('#ef233c'); // Red alert
    if (controlMode === 'GNN') return new THREE.Color('#00e5ff'); // Cyan AI
    if (controlMode === 'FIXED') return new THREE.Color('#8a9bb3'); // Gray
    if (controlMode === 'MANUAL') return new THREE.Color('#ffb703'); // Amber
    return new THREE.Color('#9d4edd'); // Purple fallback
  }, [controlMode, hasFailsafe]);

  useFrame((state, delta) => {
    if (!meshRef.current) return;
    
    // Smooth lerping for scale and position
    meshRef.current.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1);
    meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, targetY, 0.1);
    
    // Animate glow ring
    if (ringRef.current) {
      ringRef.current.position.y = meshRef.current.position.y;
      ringRef.current.rotation.x = -Math.PI / 2;
      
      // Pulse effect for emergency or failsafe
      if (isEmergency || hasFailsafe) {
        const pulse = Math.sin(state.clock.elapsedTime * 8) * 0.2 + 1;
        ringRef.current.scale.set(targetScale * 1.5 * pulse, targetScale * 1.5 * pulse, 1);
      } else {
        ringRef.current.scale.set(targetScale * 1.5, targetScale * 1.5, 1);
      }
    }
  });

  return (
    <group position={[position[0], 0, position[2]]}>
      {/* Core Node Sphere */}
      <mesh 
        ref={meshRef} 
        onClick={(e) => { e.stopPropagation(); onClick(); }}
        onPointerOver={(e) => document.body.style.cursor = 'pointer'}
        onPointerOut={(e) => document.body.style.cursor = 'auto'}
      >
        <sphereGeometry args={[1, 32, 32]} />
        <meshStandardMaterial 
          color={color} 
          emissive={color}
          emissiveIntensity={isSelected ? 0.8 : 0.4}
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>

      {/* Control Mode Glow Ring */}
      <mesh ref={ringRef}>
        <ringGeometry args={[0.9, 1.1, 32]} />
        <meshBasicMaterial 
          color={ringColor} 
          transparent 
          opacity={0.6}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Selection Highlight */}
      {isSelected && (
        <mesh position={[0, targetY, 0]}>
          <sphereGeometry args={[1.2, 16, 16]} />
          <meshBasicMaterial color="#ffffff" wireframe transparent opacity={0.3} />
        </mesh>
      )}

      {/* Label (Only show if selected or high severity to reduce clutter) */}
      {(isSelected || avgWait > 60 || hasFailsafe) && (
        <Html position={[0, targetY + targetScale + 0.5, 0]} center zIndexRange={[100, 0]}>
          <div style={{
            background: 'rgba(8, 10, 15, 0.8)',
            border: `1px solid ${isSelected ? '#00e5ff' : 'rgba(255,255,255,0.2)'}`,
            padding: '4px 8px',
            borderRadius: '4px',
            color: 'white',
            fontFamily: 'Inter, sans-serif',
            fontSize: '10px',
            whiteSpace: 'nowrap',
            backdropFilter: 'blur(4px)',
            pointerEvents: 'none',
            boxShadow: isSelected ? '0 0 10px rgba(0, 229, 255, 0.5)' : 'none'
          }}>
            <div style={{ fontWeight: 600, color: isSelected ? '#00e5ff' : 'white' }}>{name || id}</div>
            {isSelected && (
              <div style={{ fontSize: '9px', color: '#8a9bb3', marginTop: '2px' }}>
                W: {Math.round(avgWait)}s | Q: {queue}
              </div>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}
