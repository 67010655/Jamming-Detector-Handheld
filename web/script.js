const POLL_INTERVAL_MS = 100; 
let canvas = document.getElementById('spectrumCanvas');
let ctx = canvas.getContext('2d');
let polarCanvas = document.getElementById('polarCanvas');
let polarCtx = polarCanvas.getContext('2d');
let bearingLog = []; 

// Format seconds into HH:MM:SS for Uptime
function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

// Update the circular ring for score
function updateScoreRing(score) {
    const ring = document.getElementById('score-ring-fill');
    if (!ring) return;
    
    // Total circumference is 2 * PI * r (r=45) = ~283
    const maxOffset = 283;
    const pct = score / 99;
    const offset = maxOffset - (pct * maxOffset);
    ring.style.strokeDashoffset = offset;
}

// Draw the spectrum graph with Glow effect
function drawSpectrum(data) {
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    // Draw Grid (Subtle)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 1; i < 6; i++) {
        let y = (height / 6) * i;
        ctx.moveTo(0, y); ctx.lineTo(width, y);
    }
    for (let i = 1; i < 10; i++) {
        let x = (width / 10) * i;
        ctx.moveTo(x, 0); ctx.lineTo(x, height);
    }
    ctx.stroke();

    if (!data || data.length === 0) return;

    // Draw Gradient Area
    const gradient = ctx.createLinearGradient(0, height, 0, 0);
    gradient.addColorStop(0, 'rgba(0, 255, 170, 0.0)');
    gradient.addColorStop(1, 'rgba(0, 255, 170, 0.2)');

    ctx.beginPath();
    ctx.moveTo(0, height);
    data.forEach((val, i) => {
        let x = (width / (data.length - 1)) * i;
        let y = height - ((val + 100) * (height / 100)); // Normalized
        ctx.lineTo(x, y);
    });
    ctx.lineTo(width, height);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Main Line with Glow
    ctx.shadowBlur = 10;
    ctx.shadowColor = '#00ffaa';
    ctx.strokeStyle = '#00ffaa';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.shadowBlur = 0; // reset
}

// Draw the polar compass graph
function drawPolar(bearing, state) {
    const w = polarCanvas.width;
    const h = polarCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const r = (w / 2) - 40;

    polarCtx.clearRect(0, 0, w, h);

    let color = '#00ffaa';
    if (state === 'WATCH') color = '#ffcc00';
    if (state === 'JAMMING') color = '#ff3333';

    // Draw Rings
    polarCtx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    polarCtx.lineWidth = 1;
    polarCtx.beginPath();
    polarCtx.arc(cx, cy, r, 0, Math.PI * 2);
    polarCtx.arc(cx, cy, r * 0.66, 0, Math.PI * 2);
    polarCtx.arc(cx, cy, r * 0.33, 0, Math.PI * 2);
    polarCtx.stroke();

    // Cardinal Labels (Matching LCD: Left=90, Right=270)
    polarCtx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    polarCtx.font = '700 12px Outfit';
    polarCtx.textAlign = 'center';
    polarCtx.fillText('0°', cx, cy - r - 15);      // Top
    polarCtx.fillText('180°', cx, cy + r + 22);    // Bottom
    polarCtx.fillText('90°', cx - r - 22, cy + 5);  // Left (Match LCD)
    polarCtx.fillText('270°', cx + r + 22, cy + 5); // Right

    if (bearing !== undefined && bearing !== null) {
        document.getElementById('bearing-display').innerText = `${Math.round(bearing).toString().padStart(3, '0')}°`;
        
        // Draw Current Scanning/Detection Line (Glow effect)
        // Counter-clockwise math: 0=top, 90=left, 180=bot, 270=right
        const currentRad = (-bearing - 90) * Math.PI / 180;
        polarCtx.strokeStyle = color;
        polarCtx.lineWidth = 3;
        polarCtx.shadowBlur = 15;
        polarCtx.shadowColor = color;
        polarCtx.beginPath();
        polarCtx.moveTo(cx, cy);
        polarCtx.lineTo(cx + Math.cos(currentRad) * r, cy + Math.sin(currentRad) * r);
        polarCtx.stroke();
        polarCtx.shadowBlur = 0;

        // Log jammers if state is not normal
        if (state !== 'SCANNING') {
            bearingLog.push({ brg: bearing, color: color });
            if (bearingLog.length > 20) bearingLog.shift();
        }
    }

    // Draw past detected jammers (Fading dots)
    bearingLog.forEach((log, i) => {
        const rad = (-log.brg - 90) * Math.PI / 180;
        const px = cx + Math.cos(rad) * r;
        const py = cy + Math.sin(rad) * r;
        const alpha = (i + 1) / bearingLog.length;
        
        polarCtx.fillStyle = log.color;
        polarCtx.globalAlpha = alpha * 0.7;
        polarCtx.beginPath();
        polarCtx.arc(px, py, 6, 0, Math.PI * 2);
        polarCtx.fill();
    });
    polarCtx.globalAlpha = 1.0;
}

async function fetchStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        
        // Metrics Update
        let m = data.metrics;
        if (m) {
            document.getElementById('state-badge').innerText = m.state;
            document.getElementById('state-badge').dataset.state = m.state;
            document.getElementById('score-text').innerText = Math.round(m.score);
            updateScoreRing(m.score);

            document.getElementById('noise-text').innerText = `${m.noise_floor.toFixed(1)} dBm`;
            document.getElementById('peak-text').innerText = `${m.peak_p.toFixed(1)} dBm`;
            
            let rise = m.floor_rise;
            let riseStr = (rise >= 0 ? '+' : '') + rise.toFixed(1);
            document.getElementById('rise-text').innerText = `${riseStr} dB`;
            
            if (document.getElementById('margin-text')) {
                let marginStr = (m.margin >= 0 ? '+' : '') + m.margin.toFixed(1);
                document.getElementById('margin-text').innerText = `${marginStr} dB`;
            }
        }

        if (data.uptime !== undefined) {
            document.getElementById('uptime-text').innerText = formatUptime(data.uptime);
        }

        if (data.spectrum) drawSpectrum(data.spectrum);
        if (data.bearing !== undefined) drawPolar(data.bearing, m ? m.state : 'SCANNING');

    } catch (error) {
        console.error("Dashboard Sync Error:", error);
    }
    setTimeout(fetchStatus, POLL_INTERVAL_MS);
}

async function fetchHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        const tbody = document.getElementById('history-body');
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No events recorded.</td></tr>';
            return;
        }

        let html = '';
        data.forEach(row => {
            const timeStr = row.timestamp.split(' ')[1];
            html += `
                <tr>
                    <td>${timeStr}</td>
                    <td><span class="status-indicator-small" data-state="${row.state}">${row.state}</span></td>
                    <td style="color: var(--theme-color); font-weight: bold;">${row.score}</td>
                    <td>${row.bearing_deg || 0}°</td>
                    <td>${row.peak_p.toFixed(1)}</td>
                    <td>+${row.floor_rise.toFixed(1)}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) { console.error("History Error:", e); }
}

function resizeCanvas() {
    const container = canvas.parentElement;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
}

window.addEventListener('resize', resizeCanvas);
resizeCanvas();
fetchStatus();
fetchHistory();
setInterval(fetchHistory, 5000);

document.getElementById('export-btn').addEventListener('click', () => { window.location.href = '/api/export'; });
document.getElementById('clear-btn').addEventListener('click', async () => {
    if (confirm('Clear all logs?')) {
        const resp = await fetch('/api/clear', { method: 'POST' });
        const res = await resp.json();
        if (res.success) fetchHistory();
    }
});