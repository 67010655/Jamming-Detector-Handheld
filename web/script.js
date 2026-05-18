const POLL_INTERVAL_MS = 100;
const spectrumCanvas = document.getElementById('spectrumCanvas');
let bearingLog = [];

// Initialize Clocks
function updateClock() {
    const now = new Date();
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

    ctx.shadowBlur = 10;
    ctx.shadowColor = getComputedStyle(document.documentElement).getPropertyValue('--theme-color');
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--theme-color');
    ctx.lineWidth = 2.5;
    ctx.stroke();
    ctx.shadowBlur = 0;
}

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.real_time) document.getElementById('realtime-clock').innerText = data.real_time;
        if (data.real_date) document.getElementById('realtime-date').innerText = data.real_date.toUpperCase();

        if (data.metrics) {
            const m = data.metrics;
            const badge = document.getElementById('status-badge');
            badge.innerText = m.state;
            badge.dataset.state = m.state;

            // DYNAMIC THEME SWITCHING
            let themeColor = '#00ffaa';
            let glowColor = 'rgba(0, 255, 170, 0.4)';
            if (m.state === 'WATCH') {
                themeColor = '#ffcc00';
                glowColor = 'rgba(255, 204, 0, 0.4)';
            } else if (m.state === 'JAMMING') {
                themeColor = '#ff3333';
                glowColor = 'rgba(255, 51, 51, 0.4)';
            }
            document.documentElement.style.setProperty('--theme-color', themeColor);
            document.documentElement.style.setProperty('--theme-glow', glowColor);
            
            document.getElementById('score-text').innerText = Math.round(m.score).toString().padStart(2, '0');
            updateScoreRing(m.score);

            document.getElementById('noise-text').innerText = m.noise_floor.toFixed(1);
            document.getElementById('peak-text').innerText = m.peak_p.toFixed(1);
            
            const rise = m.floor_rise;
            document.getElementById('rise-text').innerText = (rise >= 0 ? '+' : '') + rise.toFixed(1);
            document.getElementById('rise-text').style.color = rise > 5 ? '#ff3333' : 'var(--theme-color)';
            
            document.getElementById('margin-text').innerText = (m.margin >= 0 ? '+' : '') + m.margin.toFixed(1) + " dB";
        }

        if (data.uptime !== undefined) {
            document.getElementById('uptime-text').innerText = formatUptime(data.uptime);
        }

        if (data.spectrum) drawSpectrum(data.spectrum);

        // Update RF Engineer Stats
        if (data.metrics) {
            let maxPeak = parseFloat(sessionStorage.getItem('maxPeak') || '-200');
            if (data.metrics.peak_p > maxPeak) {
                maxPeak = data.metrics.peak_p;
                sessionStorage.setItem('maxPeak', maxPeak);
            }
            if (document.getElementById('max-peak-text')) {
                document.getElementById('max-peak-text').innerHTML = maxPeak.toFixed(1) + ' <span class="unit">dBFS</span>';
            }
            if (document.getElementById('avg-nf-text')) {
                document.getElementById('avg-nf-text').innerHTML = data.metrics.noise_floor.toFixed(1) + ' <span class="unit">dBFS</span>';
            }
        }

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
        let jamCount = 0;
        let lastBearing = 0;

        data.forEach((row, index) => {
            const timeStr = row.timestamp.split(' ')[1] || row.timestamp;
            html += `<tr>
                <td>${timeStr}</td>
                <td><span class="status-indicator-small" data-state="${row.state}">${row.state}</span></td>
                <td>${row.score}</td>
                <td>${row.bearing_deg || 0}°</td>
                <td>${row.peak_p.toFixed(1)}</td>
                <td>+${row.floor_rise.toFixed(1)}</td>
            </tr>`;
            
            if (row.state === 'JAMMING') jamCount++;
            if (index === 0) lastBearing = row.bearing_deg || 0; // Assuming newest first
        });
        tbody.innerHTML = html;

        if (document.getElementById('jam-events-text')) {
            document.getElementById('jam-events-text').innerText = jamCount;
        }
        if (document.getElementById('last-bearing-text')) {
            document.getElementById('last-bearing-text').innerText = lastBearing + '°';
        }
    } catch (e) { console.error("History Error:", e); }
}

function resizeCanvas() {
    if (!spectrumCanvas) return;
    const container = spectrumCanvas.parentElement;
    if (container.clientWidth > 0 && container.clientHeight > 0) {
        spectrumCanvas.width = container.clientWidth;
        spectrumCanvas.height = container.clientHeight;
    }
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