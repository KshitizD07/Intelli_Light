import React from 'react';
import { Activity, Radio, AlertTriangle, Layers, Cpu, Zap, X } from 'lucide-react';

export default function UIOverlay({ 
  networkData, liveData, isConnected, 
  selectedNode, onCloseNode, 
  overlayMode, setOverlayMode 
}) {
  const kpis = liveData?.kpis || {};
  
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', pointerEvents: 'none' }}>
      
      {/* HEADER */}
      <header className="glass-panel" style={{ 
        margin: '16px', padding: '12px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        pointerEvents: 'auto'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <Activity color="#00e5ff" size={28} />
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 600, color: 'white', margin: 0, fontFamily: 'var(--font-heading)' }}>
              IntelliLight <span style={{ color: '#00e5ff' }}>Neural Core</span>
            </h1>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              ST-MARL v3.0 | {networkData?.junctions?.length || 0} Nodes Online
            </div>
          </div>
        </div>

        {/* Global KPIs */}
        <div style={{ display: 'flex', gap: '32px' }}>
          <KPICard label="Active Vehicles" value={kpis.total_vehicles || 0} color="#00e5ff" />
          <KPICard label="Avg Wait" value={`${kpis.avg_wait || 0}s`} color={kpis.avg_wait > 40 ? '#fb8500' : '#00f5d4'} />
          <KPICard label="Throughput" value={kpis.throughput || 0} color="#9d4edd" />
          <KPICard label="Failsafes Active" value={kpis.active_failsafes || 0} color={kpis.active_failsafes > 0 ? '#ef233c' : '#8a9bb3'} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ 
            width: '8px', height: '8px', borderRadius: '50%', 
            background: isConnected ? '#00f5d4' : '#ef233c',
            boxShadow: `0 0 10px ${isConnected ? '#00f5d4' : '#ef233c'}`
          }} />
          <span style={{ fontSize: '12px', color: isConnected ? '#00f5d4' : '#ef233c', fontFamily: 'var(--font-heading)' }}>
            {isConnected ? 'LIVE SYNC' : 'OFFLINE'}
          </span>
        </div>
      </header>

      {/* SIDEBAR & MAIN AREA */}
      <div style={{ flex: 1, display: 'flex', position: 'relative' }}>
        
        {/* LEFT SIDEBAR - Controls */}
        <div className="glass-panel" style={{ 
          margin: '0 16px 16px', width: '280px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '24px',
          pointerEvents: 'auto'
        }}>
          <div>
            <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={16} /> NEURAL OVERLAYS
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <OverlayBtn active={overlayMode === 'density'} onClick={() => setOverlayMode('density')} label="Traffic Density" icon={<Activity size={14}/>} />
              <OverlayBtn active={overlayMode === 'attention'} onClick={() => setOverlayMode('attention')} label="GNN Attention" icon={<Cpu size={14}/>} />
              <OverlayBtn active={overlayMode === 'emergency'} onClick={() => setOverlayMode('emergency')} label="Emergency Flow" icon={<AlertTriangle size={14}/>} />
            </div>
          </div>
          
          <div style={{ marginTop: 'auto', borderTop: '1px solid var(--panel-border)', paddingTop: '16px' }}>
            <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={16} /> RECENT EVENTS
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '200px', overflowY: 'auto' }}>
              {(liveData?.events || []).slice(-5).reverse().map((ev, i) => (
                <div key={i} style={{ fontSize: '12px', background: 'rgba(0,0,0,0.3)', padding: '8px', borderRadius: '4px', borderLeft: `2px solid ${ev.type === 'FAILSAFE' ? '#ef233c' : '#00e5ff'}` }}>
                  <div style={{ color: ev.type === 'FAILSAFE' ? '#ef233c' : '#00e5ff', fontWeight: 600, marginBottom: '4px' }}>[{ev.type}] {ev.junction}</div>
                  <div style={{ color: 'var(--text-secondary)' }}>{ev.message}</div>
                </div>
              ))}
              {(!liveData?.events || liveData.events.length === 0) && (
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>No recent events...</div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT PANEL - Node Details (if selected) */}
        {selectedNode && (
          <div className="glass-panel" style={{ 
            position: 'absolute', right: '16px', top: '0', width: '320px', padding: '24px',
            pointerEvents: 'auto', borderRight: '4px solid #00e5ff'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
              <div>
                <div style={{ fontSize: '12px', color: '#00e5ff', fontFamily: 'var(--font-heading)', letterSpacing: '1px' }}>JUNCTION NODE</div>
                <h2 style={{ fontSize: '24px', margin: '4px 0 0 0' }}>{selectedNode}</h2>
              </div>
              <button onClick={onCloseNode} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>
            
            {/* Find live data for this node */}
            {(() => {
              const nData = (liveData?.nodes || []).find(n => n.id === selectedNode);
              if (!nData) return <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Awaiting telemetry...</div>;
              
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Control Mode</span>
                      <span style={{ 
                        color: nData.control_mode === 'GNN' ? '#00e5ff' : '#ef233c', 
                        fontWeight: 600, fontFamily: 'var(--font-heading)' 
                      }}>
                        {nData.control_mode}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Active Phase</span>
                      <span style={{ color: 'white', fontWeight: 600 }}>{nData.phase_name}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Phase Timer</span>
                      <span style={{ color: '#ffb703', fontFamily: 'var(--font-heading)' }}>{nData.time_in_phase}s</span>
                    </div>
                  </div>

                  <div>
                    <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px' }}>TRAFFIC LOAD</h3>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '14px' }}>Avg Wait Time</span>
                      <span style={{ color: nData.avg_wait > 40 ? '#ef233c' : '#00f5d4' }}>{nData.avg_wait}s</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '14px' }}>Max Wait</span>
                      <span style={{ color: nData.max_wait > 90 ? '#ef233c' : 'white' }}>{nData.max_wait}s</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '14px' }}>Queue Length</span>
                      <span>{nData.queue} veh</span>
                    </div>
                  </div>
                  
                  <div>
                    <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px' }}>AI STRESS LEVEL</h3>
                    <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ 
                        width: `${Math.min(100, nData.backpressure * 100)}%`, 
                        height: '100%', 
                        background: `linear-gradient(90deg, #00e5ff, ${nData.backpressure > 0.7 ? '#ef233c' : '#ffb703'})`,
                        transition: 'width 0.5s ease'
                      }} />
                    </div>
                  </div>

                  <button style={{
                    marginTop: '10px', width: '100%', padding: '12px', background: 'transparent',
                    border: '1px solid var(--panel-border)', borderRadius: '4px', color: '#00e5ff',
                    cursor: 'pointer', fontFamily: 'var(--font-heading)', textTransform: 'uppercase', fontSize: '12px',
                    transition: 'all 0.2s'
                  }} onMouseOver={e => { e.currentTarget.style.background = 'rgba(0, 229, 255, 0.1)' }} onMouseOut={e => { e.currentTarget.style.background = 'transparent' }}>
                    MANUAL OVERRIDE
                  </button>
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

// Subcomponents

function KPICard({ label, value, color }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '1px' }}>{label}</div>
      <div style={{ fontSize: '24px', fontWeight: 600, color: color, fontFamily: 'var(--font-heading)' }}>{value}</div>
    </div>
  );
}

function OverlayBtn({ active, onClick, label, icon }) {
  return (
    <button 
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        width: '100%', padding: '12px',
        background: active ? 'rgba(0, 229, 255, 0.1)' : 'transparent',
        border: `1px solid ${active ? '#00e5ff' : 'rgba(255,255,255,0.1)'}`,
        borderRadius: '6px',
        color: active ? '#00e5ff' : 'var(--text-secondary)',
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: 'var(--font-body)',
        fontSize: '14px',
        transition: 'all 0.2s'
      }}
    >
      {icon} {label}
    </button>
  );
}
