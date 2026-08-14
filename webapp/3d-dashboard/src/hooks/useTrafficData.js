import { useState, useEffect } from 'react';

export default function useTrafficData() {
  const [networkData, setNetworkData] = useState({ junctions: [], edges: [] });
  const [liveData, setLiveData] = useState({ nodes: [], kpis: {}, events: [] });
  const [isConnected, setIsConnected] = useState(false);

  // 1. Fetch static topology
  useEffect(() => {
    const fetchTopology = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/network');
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        setNetworkData(data);
      } catch (error) {
        console.error("Failed to load network topology, using fallback", error);
      }
    };
    fetchTopology();
  }, []);

  // 2. Connect to WebSocket for live simulation data
  useEffect(() => {
    let ws;
    let reconnectTimer;
    
    const connect = () => {
      ws = new WebSocket('ws://localhost:8000/ws/live');
      
      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Only update if it's a valid snapshot
          if (data && data.nodes) {
            setLiveData(data);
          }
        } catch (e) {
          console.error("Failed to parse websocket message", e);
        }
      };
      
      ws.onclose = () => {
        console.log('WebSocket disconnected. Attempting to reconnect...');
        setIsConnected(false);
        reconnectTimer = setTimeout(connect, 3000);
      };
      
      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, []);

  return { networkData, liveData, isConnected };
}
