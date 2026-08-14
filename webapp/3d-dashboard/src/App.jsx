import React, { useState, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import NetworkGraph from './components/three/NetworkGraph';
import UIOverlay from './components/ui/UIOverlay';
import useTrafficData from './hooks/useTrafficData';
import './index.css';

function App() {
  const { networkData, liveData, isConnected } = useTrafficData();
  const [selectedNode, setSelectedNode] = useState(null);
  const [overlayMode, setOverlayMode] = useState('density'); // density, attention, emergency

  return (
    <div className="app-container" style={{ width: '100vw', height: '100vh', position: 'relative', background: '#030305' }}>
      
      {/* 3D Canvas Layer */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 1 }}>
        <Canvas camera={{ position: [0, 15, 25], fov: 45 }}>
          <color attach="background" args={['#030305']} />
          <ambientLight intensity={0.2} />
          <pointLight position={[10, 10, 10]} intensity={0.5} />
          
          <NetworkGraph 
            networkData={networkData} 
            liveData={liveData} 
            selectedNode={selectedNode}
            onNodeClick={setSelectedNode}
            overlayMode={overlayMode}
          />
          
          <OrbitControls 
            enableDamping 
            dampingFactor={0.05} 
            maxPolarAngle={Math.PI / 2 - 0.1} // Prevent going below ground
            minDistance={5}
            maxDistance={100}
          />
          
          {/* Professional Sci-Fi Bloom Effect */}
          <EffectComposer>
            <Bloom 
              luminanceThreshold={0.2} 
              luminanceSmoothing={0.9} 
              intensity={1.5} 
            />
          </EffectComposer>
        </Canvas>
      </div>

      {/* DOM UI Overlay Layer */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 10, pointerEvents: 'none' }}>
        <UIOverlay 
          networkData={networkData}
          liveData={liveData}
          isConnected={isConnected}
          selectedNode={selectedNode}
          onCloseNode={() => setSelectedNode(null)}
          overlayMode={overlayMode}
          setOverlayMode={setOverlayMode}
        />
      </div>

    </div>
  );
}

export default App;
