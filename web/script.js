const POLL_INTERVAL_MS = 300; // ~3 FPS (Optimized for Pi Zero 2W)
let canvas = document.getElementById('spectrumCanvas');
let ctx = canvas.getContext('2d');
let polarCanvas = document.getElementById('polarCanvas');
let polarCtx = polarCanvas.getContext('2d');
let bearingLog = []; // Local cache for polar dots

// Format seconds into HH:MM:SS
function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

// Draw the spectrum graph
function drawSpectrum(data) {
    const width = canvas.width;
    const height = canvas.height;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Draw Grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    // Horizontal lines (every 10 dB)
    for (let i = 1; i < 6; i++) {
        let y = (height / 6) * i;
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
    }
    // Vertical lines
    for (let i = 1; i < 10; i++) {
        let x = (width / 10) * i;
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
    }
    ctx.stroke();

    if (!data || data.length === 0) return;

    // Map data points
    // Assume data values range roughly between -100 and -30
    const MIN_DB = -100;
    const MAX_DB = -40;
    const RANGE = MAX_DB - MIN_DB;

    ctx.beginPath();
    let startX = 0;
    let startY = height;

    // Determine the theme color based on body data-state
    const state = document.body.getAttribute('data-state');
    let color = '#00ffaa'; // SCANNING
    if (state === 'WATCH') color = '#ffcc00';
    if (state === 'JAMMING') color = '#ff3333';

    ctx.moveTo(0, height);

    for (let i = 0; i < data.length; i++) {
        let x = (i / (data.length - 1)) * width;
        let db = data[i];

        // Normalize and invert (0 is top, height is bottom)
        let normalized = (db - MIN_DB) / RANGE;
        normalized = Math.max(0, Math.min(1, normalized)); // clamp
        let y = height - (normalized * height);

        ctx.lineTo(x, y);
    }

    ctx.lineTo(width, height);
    ctx.closePath();

    // Create Gradient
    let gradient = ctx.createLinearGradient(0, 0, 0, height);
    // Convert hex to rgba for gradient
    let r = 0, g = 255, b = 170; // defaults
    if (state === 'WATCH') { r = 255; g = 204; b = 0; }
    if (state === 'JAMMING') { r = 255; g = 51; b = 51; }

    gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.6)`);
    gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.0)`);

    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
}

// Draw the polar compass graph
function drawPolar(bearing, state) {
    const w = polarCanvas.width;
    const h = polarCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const r = (w / 2) - 15;

    polarCtx.clearRect(0, 0, w, h);

    // Theme color
    let color = '#00ffaa';
    if (state === 'WATCH') color = '#ffcc00';
    if (state === 'JAMMING') color = '#ff3333';

    // Draw rings
    polarCtx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    polarCtx.beginPath();
    polarCtx.arc(cx, cy, r, 0, Math.PI * 2);
    polarCtx.arc(cx, cy, r * 0.6, 0, Math.PI * 2);
    polarCtx.stroke();

    // Draw cardinal lines
    polarCtx.beginPath();
    polarCtx.moveTo(cx, cy - r); polarCtx.lineTo(cx, cy + r);
    polarCtx.moveTo(cx - r, cy); polarCtx.lineTo(cx + r, cy);
    polarCtx.stroke();

    // Labels
    polarCtx.fillStyle = '#888899';
    polarCtx.font = '10px Inter';
    polarCtx.textAlign = 'center';
    polarCtx.fillText('N', cx, cy - r - 4);
    polarCtx.fillText('S', cx, cy + r + 10);
    polarCtx.fillText('W', cx - r - 8, cy + 4);
    polarCtx.fillText('E', cx + r + 8, cy + 4);

    // Update bearing log if new bearing provided
    if (bearing !== undefined && bearing !== null) {
        document.getElementById('bearing-display').innerText = `${bearing}°`;
        // Only log if it's a significant signal or just keep recent
        bearingLog.push(bearing);
        if (bearingLog.length > 20) bearingLog.shift();
    }

    // Draw bearing dots
    bearingLog.forEach((brg, i) => {
        const rad = (brg - 90) * Math.PI / 180;
        const px = cx + Math.cos(rad) * r;
        const py = cy + Math.sin(rad) * r;
        
        const alpha = (i + 1) / bearingLog.length;
        polarCtx.fillStyle = color;
        polarCtx.globalAlpha = alpha;
        polarCtx.beginPath();
        polarCtx.arc(px, py, 4, 0, Math.PI * 2);
        polarCtx.fill();
    });
    polarCtx.globalAlpha = 1.0;

    // Draw current bearing line
    if (bearing !== undefined) {
        const rad = (bearing - 90) * Math.PI / 180;
        polarCtx.strokeStyle = color;
        polarCtx.lineWidth = 2;
        polarCtx.beginPath();
        polarCtx.moveTo(cx, cy);
        polarCtx.lineTo(cx + Math.cos(rad) * r, cy + Math.sin(rad) * r);
        polarCtx.stroke();
    }
}

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Update Text Metrics
        const m = data.metrics;
        if (m && m.state) {
            const badge = document.getElementById('state-badge');
            if (badge) {
                document.body.setAttribute('data-state', m.state);
                badge.innerText = m.state;
            }

            const stateText = document.getElementById('state-text');
            if (stateText) {
                const shortMap = { "SCANNING": "SCAN", "WATCH": "WTCH", "JAMMING": "JAM!" };
                stateText.innerText = shortMap[m.state] || m.state;
            }

            const nfVal = document.getElementById('nf-val');
            if (nfVal) nfVal.innerText = m.noise_floor !== undefined ? m.noise_floor.toFixed(1) : "-90.0";
            
            const peakVal = document.getElementById('peak-val');
            if (peakVal) peakVal.innerText = m.peak_p !== undefined ? m.peak_p.toFixed(1) : "0.0";
            
            const baseVal = document.getElementById('base-val');
            if (baseVal) baseVal.innerText = m.baseline_p !== undefined ? m.baseline_p.toFixed(1) : "0.0";
            
            const riseVal = document.getElementById('rise-val');
            if (riseVal) riseVal.innerText = m.floor_rise !== undefined ? `+${m.floor_rise.toFixed(1)}` : "+0.0";

            const scoreText = document.getElementById('score-text');
            if (scoreText) scoreText.innerText = m.score !== undefined ? m.score.toString().padStart(2, '0') : "00";

            const scoreBar = document.getElementById('score-bar');
            if (scoreBar) {
                let pct = Math.min(100, Math.max(0, (m.score / 99) * 100));
                scoreBar.style.height = `${pct}%`;
            }

            const marginText = document.getElementById('margin-text');
            if (marginText && m.margin !== undefined) {
                let marginStr = m.margin > 0 ? `+${m.margin.toFixed(1)}` : m.margin.toFixed(1);
                marginText.innerText = `${marginStr} dB`;
            }
        }

        // Update Uptime
        const uptimeText = document.getElementById('uptime-text');
        if (uptimeText && data.uptime !== undefined) {
            uptimeText.innerText = formatUptime(data.uptime);
        }

        // Update Graph
        if (data.spectrum && canvas) {
            drawSpectrum(data.spectrum);
        }

        // Update Polar
        if (polarCanvas && data.bearing !== undefined) {
            drawPolar(data.bearing, m ? m.state : 'SCANNING');
        }

    } catch (error) {
        console.error("Error fetching dashboard data:", error);
    }

    // Schedule next poll
    setTimeout(fetchStatus, POLL_INTERVAL_MS);
}

async function fetchHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();

        const tbody = document.getElementById('history-body');
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--text-muted);">No events recorded yet.</td></tr>';
            return;
        }

        let html = '';
        data.forEach(row => {
            // Clean up timestamp (remove date if it's today, or just show time)
            const timeStr = row.timestamp.split(' ')[1]; // Get HH:MM:SS

            html += `
                <tr>
                    <td>${timeStr}</td>
                    <td><span class="state-cell" data-val="${row.state}">${row.state}</span></td>
                    <td style="color: var(--theme-color); font-weight: bold;">${row.score}</td>
                    <td style="font-family: monospace;">${row.bearing_deg || 0}°</td>
                    <td>${row.peak_p.toFixed(1)}</td>
                    <td>+${row.floor_rise.toFixed(1)}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (error) {
        console.error("Error fetching history:", error);
    }
}

// Ensure canvas matches container size
function resizeCanvas() {
    const container = canvas.parentElement;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
}

window.addEventListener('resize', resizeCanvas);

// Start
resizeCanvas();
fetchStatus();

// Fetch history every 5 seconds (Optimized for Pi Zero 2W)
fetchHistory();
setInterval(fetchHistory, 5000);

// Export CSV handler
document.getElementById('export-btn').addEventListener('click', () => {
    window.location.href = '/api/export';
});

// Clear History handler
document.getElementById('clear-btn').addEventListener('click', async () => {
    if (confirm('Are you sure you want to clear all history? This cannot be undone.')) {
        try {
            const response = await fetch('/api/clear', { method: 'POST' });
            const result = await response.json();
            if (result.success) {
                // Clear the table immediately in the UI
                document.querySelector('#history-table tbody').innerHTML = '';
                alert('History cleared successfully.');
            }
        } catch (error) {
            console.error('Error clearing history:', error);
            alert('Failed to clear history.');
        }
    }
});
