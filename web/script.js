const POLL_INTERVAL_MS = 100;
const spectrumCanvas = document.getElementById('spectrumCanvas');
const polarCanvas = document.getElementById('polarCanvas');
let bearingLog = [];

// Initialize Clocks (Local fallback)
function updateClock() {
    const now = new Date();
    // Only update if not yet received from API
    if (document.getElementById('realtime-clock').innerText === '00:00:00') {
        document.getElementById('realtime-clock').innerText = now.toTimeString().split(' ')[0];
    }
}
setInterval(updateClock, 1000);

function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
    const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function updateScoreRing(score) {
    const ring = document.getElementById('score-ring-fill');
    if (!ring) return;
    const maxOffset = 283;
    const pct = Math.min(Math.max(score / 99, 0), 1);
    ring.style.strokeDashoffset = maxOffset - (pct * maxOffset);
}

function drawSpectrum(data) {
    if (!spectrumCanvas || spectrumCanvas.width === 0) return;
    const ctx = spectrumCanvas.getContext('2d');
    const w = spectrumCanvas.width;
    const h = spectrumCanvas.height;
    ctx.clearRect(0, 0, w, h);
    
    // Grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for(let i=1; i<5; i++) {
        let y = (h/5)*i; ctx.moveTo(0, y); ctx.lineTo(w, y);
        let x = (w/5)*i; ctx.moveTo(x, 0); ctx.lineTo(x, h);
    }
    ctx.stroke();

    if (!data || data.length === 0) return;

    const step = w / (data.length - 1);
    ctx.beginPath();
    ctx.moveTo(0, h);
    data.forEach((val, i) => {
        const x = i * step;
        const y = h - ((val + 100) * (h / 100));
        ctx.lineTo(x, y);
    });
    
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(0, 255, 170, 0.2)');
    grad.addColorStop(1, 'rgba(0, 255, 170, 0)');
    ctx.lineTo(w, h);
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.shadowBlur = 8;
    ctx.shadowColor = '#00ffaa';
    ctx.strokeStyle = '#00ffaa';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.shadowBlur = 0;
}

function drawPolar(bearing, state) {
    if (!polarCanvas || polarCanvas.width === 0) return;
    const ctx = polarCanvas.getContext('2d');
    const w = polarCanvas.width;
    const h = polarCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(cx, cy) - 40;

    ctx.clearRect(0, 0, w, h);

    let color = '#00ffaa';
    if (state === 'WATCH') color = '#ffcc00';
    if (state === 'JAMMING') color = '#ff3333';

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.arc(cx, cy, r * 0.66, 0, Math.PI * 2);
    ctx.arc(cx, cy, r * 0.33, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.font = '700 12px Outfit';
    ctx.textAlign = 'center';
    ctx.fillText('0°', cx, cy - r - 12);
    ctx.fillText('180°', cx, cy + r + 20);
    ctx.fillText('90°', cx - r - 22, cy + 5);
    ctx.fillText('270°', cx + r + 22, cy + 5);

    if (bearing !== undefined && bearing !== null) {
        // UPDATE BEARING TEXT
        document.getElementById('bearing-display').innerText = `${Math.round(bearing).toString().padStart(3, '0')}°`;
        
        const rad = (-bearing - 90) * Math.PI / 180;
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.shadowBlur = 15;
        ctx.shadowColor = color;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(rad) * r, cy + Math.sin(rad) * r);
        ctx.stroke();
        ctx.shadowBlur = 0;

        if (state !== 'SCANNING') {
            bearingLog.push({ brg: bearing, color: color });
            if (bearingLog.length > 20) bearingLog.shift();
        }
    }

    bearingLog.forEach((log, i) => {
        const rad = (-log.brg - 90) * Math.PI / 180;
        const alpha = (i + 1) / bearingLog.length;
        ctx.fillStyle = log.color;
        ctx.globalAlpha = alpha * 0.7;
        ctx.beginPath();
        ctx.arc(cx + Math.cos(rad)*r, cy + Math.sin(rad)*r, 6, 0, Math.PI*2);
        ctx.fill();
    });
    ctx.globalAlpha = 1.0;
}

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        // Update Time & Date from API
        if (data.real_time) document.getElementById('realtime-clock').innerText = data.real_time;
        if (data.real_date) document.getElementById('realtime-date').innerText = data.real_date.toUpperCase();

        if (data.metrics) {
            const m = data.metrics;
            const badge = document.getElementById('status-badge');
            badge.innerText = m.state;
            badge.dataset.state = m.state;
            
            document.getElementById('score-text').innerText = Math.round(m.score).toString().padStart(2, '0');
            updateScoreRing(m.score);

            document.getElementById('noise-text').innerText = m.noise_floor.toFixed(1);
            document.getElementById('peak-text').innerText = m.peak_p.toFixed(1);
            document.getElementById('base-text').innerText = (m.noise_floor - 5).toFixed(1);
            
            const rise = m.floor_rise;
            document.getElementById('rise-text').innerText = (rise >= 0 ? '+' : '') + rise.toFixed(1);
            document.getElementById('margin-text').innerText = (m.margin >= 0 ? '+' : '') + m.margin.toFixed(1) + " dB";
        }

        if (data.uptime !== undefined) {
            document.getElementById('uptime-text').innerText = formatUptime(data.uptime);
        }

        if (data.spectrum) drawSpectrum(data.spectrum);
        if (data.bearing !== undefined) drawPolar(data.bearing, data.metrics ? data.metrics.state : 'SCANNING');

    } catch (e) { console.error("Sync Error:", e); }
    setTimeout(fetchStatus, POLL_INTERVAL_MS);
}

async function fetchHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        const tbody = document.getElementById('history-body');
        if (!data || data.length === 0) return;

        let html = '';
        data.forEach(row => {
            const timeStr = row.timestamp.split(' ')[1] || row.timestamp;
            html += `<tr>
                <td>${timeStr}</td>
                <td><span class="status-indicator-small" data-state="${row.state}">${row.state}</span></td>
                <td>${row.score}</td>
                <td>${row.bearing_deg || 0}°</td>
                <td>${row.peak_p.toFixed(1)}</td>
                <td>+${row.floor_rise.toFixed(1)}</td>
            </tr>`;
        });
        tbody.innerHTML = html;
    } catch (e) { console.error("History Error:", e); }
}

function resizeCanvas() {
    [spectrumCanvas, polarCanvas].forEach(c => {
        if (!c) return;
        const container = c.parentElement;
        if (container.clientWidth > 0 && container.clientHeight > 0) {
            c.width = container.clientWidth;
            c.height = container.clientHeight;
        }
    });
}

window.addEventListener('load', () => {
    resizeCanvas();
    fetchStatus();
    fetchHistory();
    setInterval(fetchHistory, 5000);
});
window.addEventListener('resize', resizeCanvas);

document.getElementById('export-btn').onclick = () => window.location.href = '/api/export';
document.getElementById('clear-btn').onclick = async () => {
    if (confirm('Clear all logs?')) {
        await fetch('/api/clear', { method: 'POST' });
        fetchHistory();
    }
};