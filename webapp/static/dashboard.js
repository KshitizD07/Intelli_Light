/* ============================================================
   IntelliLight 3.0 — Dashboard JavaScript
   Connects to the backend WebSocket, renders junctions on 
   MapLibre GL, and manages operator/public mode.
   ============================================================ */

// ── State ──
let map = null;
let ws = null;
let junctions = {};      // id -> { marker, data, popup }
let networkData = null;   // static topology from /api/network
let selectedJunction = null;
let currentMode = 'operator'; // 'operator' | 'public'
let currentOverlay = 'density';
let events = [];
let reconnectAttempts = 0;

// Lucknow center coordinates
const LUCKNOW_CENTER = [80.9462, 26.8467];
const LUCKNOW_ZOOM = 13;

// ── Initialize ──
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    fetchNetwork();
    connectWebSocket();
});

// ── Map ──
function initMap() {
    map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {
                'osm-tiles': {
                    type: 'raster',
                    tiles: [
                        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'
                    ],
                    tileSize: 256,
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
                }
            },
            layers: [{
                id: 'osm-tiles',
                type: 'raster',
                source: 'osm-tiles',
                minzoom: 0,
                maxzoom: 19
            }]
        },
        center: LUCKNOW_CENTER,
        zoom: LUCKNOW_ZOOM,
        maxZoom: 18,
        minZoom: 10
    });

    map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
}

function zoomIn() { map.zoomIn(); }
function zoomOut() { map.zoomOut(); }
function resetView() { map.flyTo({ center: LUCKNOW_CENTER, zoom: LUCKNOW_ZOOM }); }

// ── Fetch Static Network Topology ──
async function fetchNetwork() {
    try {
        const resp = await fetch('/api/network');
        networkData = await resp.json();
        renderJunctions(networkData.junctions);
        document.getElementById('junction-count').textContent = networkData.junctions.length;
        renderJunctionList(networkData.junctions);
    } catch (e) {
        console.error('Failed to fetch network:', e);
        // Generate mock junctions for demo
        generateMockNetwork();
    }
}

function generateMockNetwork() {
    const names = [
        'Hazratganj', 'Aminabad', 'Charbagh', 'Gomti Nagar', 'Alambagh',
        'Aliganj', 'Indira Nagar', 'Mahanagar', 'Rajajipuram', 'Vikas Nagar',
        'Husainabad', 'Kaiserbagh', 'Lalbagh', 'Daliganj', 'Cantt',
        'Ashiana', 'Jankipuram', 'Telibagh', 'Chinhat', 'Sushant Golf City',
        'Vasant Kunj', 'Faizabad Road', 'Kanpur Road', 'Sitapur Road', 'Ring Road Jn1',
        'Ring Road Jn2', 'Polytechnic', 'Engineering College', 'IT College', 'Saharaganj',
        'Wave City', 'Awadh Hospital', 'Medanta Jn', 'Lucknow Univ', 'KD Singh',
        'Sikandar Bagh', 'Residency', 'GPO', 'Naka Hindola', 'Parivartan Chowk',
        'Lekhraj Market'
    ];
    
    const mockJunctions = names.map((name, i) => ({
        id: `j_${i}`,
        name: name,
        lng: LUCKNOW_CENTER[0] + (Math.random() - 0.5) * 0.08,
        lat: LUCKNOW_CENTER[1] + (Math.random() - 0.5) * 0.06,
        type: Math.random() > 0.3 ? 'traffic_light' : 'priority',
        has_tls: Math.random() > 0.3
    }));
    
    networkData = { junctions: mockJunctions, edges: [] };
    renderJunctions(mockJunctions);
    document.getElementById('junction-count').textContent = mockJunctions.length;
    renderJunctionList(mockJunctions);
}

// ── Render Junctions on Map ──
function renderJunctions(junctionList) {
    junctionList.forEach(j => {
        const el = document.createElement('div');
        el.className = 'junction-marker status-healthy';
        el.id = `marker-${j.id}`;
        
        const tooltip = document.createElement('div');
        tooltip.className = 'junction-tooltip';
        tooltip.innerHTML = `
            <div class="tt-name">${j.name || j.id}</div>
            <div class="tt-info">Queue: <span class="tt-queue">0</span> | Wait: <span class="tt-wait">0s</span></div>
        `;
        el.appendChild(tooltip);
        
        el.addEventListener('click', () => selectJunction(j.id));
        
        const marker = new maplibregl.Marker({ element: el })
            .setLngLat([j.lng, j.lat])
            .addTo(map);
        
        junctions[j.id] = {
            marker,
            element: el,
            data: j,
            state: { queue: 0, avg_wait: 0, max_wait: 0, current_phase: 0, control_mode: 'GNN', backpressure: 0 }
        };
    });
}

// ── Junction List (Sidebar) ──
function renderJunctionList(junctionList) {
    const container = document.getElementById('junction-list');
    container.innerHTML = '';
    
    junctionList.forEach(j => {
        const item = document.createElement('div');
        item.className = 'nav-item';
        item.id = `list-${j.id}`;
        item.innerHTML = `<span class="nav-icon" style="font-size:10px;">●</span> ${j.name || j.id}`;
        item.addEventListener('click', () => {
            selectJunction(j.id);
            map.flyTo({ center: [j.lng, j.lat], zoom: 16 });
        });
        container.appendChild(item);
    });
}

// ── Search ──
function searchJunction(query) {
    const q = query.toLowerCase();
    const container = document.getElementById('junction-list');
    const items = container.querySelectorAll('.nav-item');
    
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(q) ? 'flex' : 'none';
    });
}

// ── WebSocket ──
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/live`);
    
    ws.onopen = () => {
        console.log('[WS] Connected');
        reconnectAttempts = 0;
        document.getElementById('status-badge').textContent = '● LIVE';
        document.getElementById('status-badge').className = 'header-badge badge-live';
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleTick(data);
        } catch (e) {
            console.error('[WS] Parse error:', e);
        }
    };
    
    ws.onclose = () => {
        console.log('[WS] Disconnected');
        document.getElementById('status-badge').textContent = '● OFFLINE';
        document.getElementById('status-badge').className = 'header-badge';
        document.getElementById('status-badge').style.cssText = 'background:var(--red-glow);color:var(--red);border:1px solid rgba(239,68,68,0.3)';
        
        // Reconnect with backoff
        reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        setTimeout(connectWebSocket, delay);
    };
    
    ws.onerror = (err) => {
        console.error('[WS] Error:', err);
    };
}

// ── Handle Live Tick ──
function handleTick(data) {
    // Update sim time
    if (data.sim_time !== undefined) {
        const totalSec = Math.floor(data.sim_time);
        const h = String(Math.floor(totalSec / 3600)).padStart(2, '0');
        const m = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
        const s = String(totalSec % 60).padStart(2, '0');
        document.getElementById('sim-time').textContent = `T+${h}:${m}:${s}`;
    }
    
    // Update KPIs
    if (data.kpis) {
        document.getElementById('kpi-vehicles').textContent = data.kpis.total_vehicles || 0;
        document.getElementById('kpi-avgwait').textContent = (data.kpis.avg_wait || 0).toFixed(1) + 's';
        document.getElementById('kpi-throughput').textContent = data.kpis.throughput || 0;
        document.getElementById('kpi-failsafes').textContent = data.kpis.active_failsafes || 0;
        document.getElementById('kpi-ev').textContent = data.kpis.active_ev_preemptions || 0;
    }
    
    // Update junction states
    if (data.nodes) {
        data.nodes.forEach(node => {
            const junction = junctions[node.id];
            if (!junction) return;
            
            junction.state = { ...junction.state, ...node };
            
            // Update marker color based on overlay (use classList, not className)
            const status = getStatus(node, currentOverlay);
            junction.element.classList.remove('status-healthy', 'status-moderate', 'status-heavy', 'status-critical', 'status-offline', 'failsafe-active', 'ev-active');
            junction.element.classList.add(`status-${status}`);
            
            // Failsafe / EV pulse
            if (node.control_mode === 'FAILSAFE') {
                junction.element.classList.add('failsafe-active');
            } else if (node.control_mode === 'EV_PREEMPTION') {
                junction.element.classList.add('ev-active');
            }
            
            // Update tooltip
            const ttQueue = junction.element.querySelector('.tt-queue');
            const ttWait = junction.element.querySelector('.tt-wait');
            if (ttQueue) ttQueue.textContent = node.queue || 0;
            if (ttWait) ttWait.textContent = (node.avg_wait || 0).toFixed(0) + 's';
        });
        
        // Update selected panel
        if (selectedJunction && junctions[selectedJunction]) {
            updatePanel(selectedJunction);
        }
    }
    
    // Process events
    if (data.events && data.events.length > 0) {
        data.events.forEach(ev => addEvent(ev));
    }
}

function getStatus(node, overlay) {
    let value = 0;
    switch (overlay) {
        case 'density':
        case 'queue':
            value = node.queue || 0;
            if (value > 40) return 'critical';
            if (value > 25) return 'heavy';
            if (value > 10) return 'moderate';
            return 'healthy';
        case 'wait':
            value = node.avg_wait || 0;
            if (value > 60) return 'critical';
            if (value > 35) return 'heavy';
            if (value > 15) return 'moderate';
            return 'healthy';
        case 'backpressure':
            value = node.backpressure || 0;
            if (value > 0.8) return 'critical';
            if (value > 0.5) return 'heavy';
            if (value > 0.2) return 'moderate';
            return 'healthy';
        case 'phase':
            return 'healthy'; // Phase view uses different coloring
        default:
            return 'healthy';
    }
}

// ── Events ──
function addEvent(ev) {
    events.unshift(ev);
    if (events.length > 50) events.pop();
    
    const feed = document.getElementById('event-feed');
    const chip = document.createElement('div');
    
    let chipClass = 'info';
    let icon = '●';
    if (ev.type === 'FAILSAFE') { chipClass = 'failsafe'; icon = '⚠'; }
    else if (ev.type === 'EV_PREEMPTION') { chipClass = 'ev'; icon = '🚑'; }
    else if (ev.type === 'CONGESTION') { chipClass = 'congestion'; icon = '🔶'; }
    
    chip.className = `event-chip ${chipClass}`;
    chip.innerHTML = `<span class="event-dot"></span>${icon} ${ev.message || ev.type}`;
    chip.addEventListener('click', () => {
        if (ev.junction && junctions[ev.junction]) {
            selectJunction(ev.junction);
            map.flyTo({ center: [junctions[ev.junction].data.lng, junctions[ev.junction].data.lat], zoom: 16 });
        }
    });
    
    feed.insertBefore(chip, feed.firstChild);
    
    // Keep feed size manageable
    while (feed.children.length > 20) {
        feed.removeChild(feed.lastChild);
    }
    
    // Update alert count
    document.getElementById('alert-count').textContent = Math.min(events.length, 99);
}

// ── Select Junction ──
function selectJunction(id) {
    // Deselect previous
    if (selectedJunction && junctions[selectedJunction]) {
        const prevEl = junctions[selectedJunction].element;
        prevEl.style.outline = 'none';
        const prevList = document.getElementById(`list-${selectedJunction}`);
        if (prevList) prevList.classList.remove('active');
    }
    
    selectedJunction = id;
    const junction = junctions[id];
    if (!junction) return;
    
    // Highlight
    junction.element.style.outline = '3px solid var(--text-accent)';
    junction.element.style.outlineOffset = '3px';
    const listItem = document.getElementById(`list-${id}`);
    if (listItem) listItem.classList.add('active');
    
    updatePanel(id);
}

function updatePanel(id) {
    const junction = junctions[id];
    if (!junction) return;
    
    const state = junction.state;
    const data = junction.data;
    
    document.getElementById('panel-junction-name').textContent = data.name || id;
    
    // Control mode badge
    let modeBadge = '';
    switch (state.control_mode) {
        case 'GNN': modeBadge = '<span class="control-badge gnn">🧠 GNN Optimizing</span>'; break;
        case 'FAILSAFE': modeBadge = '<span class="control-badge failsafe">⚠ Starvation Failsafe</span>'; break;
        case 'EV_PREEMPTION': modeBadge = '<span class="control-badge ev">🚑 EV Priority</span>'; break;
        case 'MIN_GREEN_LOCK': modeBadge = '<span class="control-badge locked">🔒 Min Green Lock</span>'; break;
        default: modeBadge = '<span class="control-badge gnn">🧠 GNN</span>';
    }
    
    // Stream weights (mock for display)
    const streams = ['N', 'E', 'S', 'W'];
    let streamBars = '';
    streams.forEach((dir, i) => {
        const weight = (state.backpressure ? (Math.random() * 0.4 + state.backpressure * 0.6) : Math.random()).toFixed(2);
        const width = Math.min(parseFloat(weight) * 100, 100);
        streamBars += `
            <div class="stream-bar">
                <span class="stream-label">${dir}</span>
                <div class="stream-track"><div class="stream-fill" style="width:${width}%"></div></div>
                <span class="stream-value">${weight}</span>
            </div>
        `;
    });
    
    document.getElementById('panel-content').innerHTML = `
        <div class="panel-section">
            <div class="panel-section-title">Control State</div>
            <div style="margin-bottom:10px">${modeBadge}</div>
            <div class="detail-row">
                <span class="detail-label">Junction Type</span>
                <span class="detail-value">${data.type || '4-way'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Current Phase</span>
                <span class="detail-value" style="color:var(--green)">${state.phase_name || 'GGGGrrrr'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Time in Phase</span>
                <span class="detail-value">${(state.time_in_phase || 0).toFixed(0)}s</span>
            </div>
        </div>
        
        <div class="panel-section">
            <div class="panel-section-title">Traffic State</div>
            <div class="detail-row">
                <span class="detail-label">Queue Length</span>
                <span class="detail-value" style="color:${state.queue > 30 ? 'var(--red)' : 'var(--green)'}">${state.queue || 0}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Avg Wait</span>
                <span class="detail-value">${(state.avg_wait || 0).toFixed(1)}s</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Max Wait</span>
                <span class="detail-value" style="color:${(state.max_wait || 0) > 80 ? 'var(--red)' : 'var(--text-primary)'}">${(state.max_wait || 0).toFixed(0)}s</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Backpressure</span>
                <span class="detail-value">${(state.backpressure || 0).toFixed(2)}</span>
            </div>
        </div>
        
        <div class="panel-section">
            <div class="panel-section-title">GNN Stream Weights</div>
            ${streamBars}
        </div>
        
        <div class="panel-section">
            <button class="override-btn" onclick="manualOverride('${id}')">
                ⚡ Force Manual Override
            </button>
        </div>
    `;
}

function closePanel() {
    if (selectedJunction && junctions[selectedJunction]) {
        junctions[selectedJunction].element.style.outline = 'none';
        const listItem = document.getElementById(`list-${selectedJunction}`);
        if (listItem) listItem.classList.remove('active');
    }
    selectedJunction = null;
    document.getElementById('panel-junction-name').textContent = 'Select a Junction';
    document.getElementById('panel-content').innerHTML = `
        <div class="panel-section" style="text-align:center; padding:40px 16px;">
            <div style="font-size:32px; margin-bottom:12px;">🗺️</div>
            <div style="color:var(--text-muted); font-size:13px;">
                Click on a junction on the map<br>to view its details
            </div>
        </div>
    `;
}

// ── Commands ──
async function manualOverride(junctionId) {
    try {
        await fetch('/api/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: 'OVERRIDE', junction: junctionId, phase: 0 })
        });
        addEvent({ type: 'MANUAL', junction: junctionId, message: `Manual override on ${junctions[junctionId]?.data?.name || junctionId}` });
    } catch (e) {
        console.error('Override failed:', e);
    }
}

// ── Mode Toggle ──
function setMode(mode) {
    currentMode = mode;
    const app = document.getElementById('app');
    
    document.getElementById('btn-operator').classList.toggle('active', mode === 'operator');
    document.getElementById('btn-public').classList.toggle('active', mode === 'public');
    
    if (mode === 'public') {
        app.classList.add('public-mode');
        document.getElementById('public-legend').style.display = 'flex';
    } else {
        app.classList.remove('public-mode');
        document.getElementById('public-legend').style.display = 'none';
    }
}

// ── Overlay ──
function setOverlay(overlay, btn) {
    currentOverlay = overlay;
    document.querySelectorAll('.overlay-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    
    // Re-color all junctions using classList (not className replacement)
    Object.values(junctions).forEach(j => {
        const status = getStatus(j.state, overlay);
        // Remove old status classes
        j.element.classList.remove('status-healthy', 'status-moderate', 'status-heavy', 'status-critical', 'status-offline');
        j.element.classList.add(`status-${status}`);
    });
}

// ── Filter Toggles ──
function toggleFilter(el) {
    el.classList.toggle('active');
}

// ── Nav ──
function navTo(page) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    event.target.closest('.nav-item').classList.add('active');
}

function toggleEvents() {
    // Could show a modal of all events; for now just scroll to timeline
    document.querySelector('.timeline').scrollIntoView({ behavior: 'smooth' });
}
