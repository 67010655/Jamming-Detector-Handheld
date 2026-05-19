/* ═══════════════════════════════════════════════
   GNSS Jamming Detector — Dashboard Script
   ═══════════════════════════════════════════════ */

// ── Constants ──
const POLL_MS = 250; // Relaxed polling for Pi CPU
const MARGIN_MAX = 50;
const WATERFALL_ROWS = 60; // Reduced from 120 for 2x performance
const WATERFALL_ADD_MS = 500;

// ── DOM Refs ──
const $id = id => document.getElementById(id);
const spectrumCanvas = $id('spectrumCanvas');
const marginCanvas   = $id('marginCanvas');
const waterfallCanvas = $id('waterfallCanvas');

// ── State ──
let marginHistory  = [];
let waterfallData  = [];
let lastWfTime     = 0;
let allLogs        = [];
let activeFilter   = 'ALL';
let isDark         = true;

let latestSpectrum = null;
let renderPending = false;

const session = {
    maxPeak: -200, peakRise: 0, nfSum: 0, nfCount: 0,
    jamCount: 0, watchCount: 0, lastState: ''
};

// ── Theme Toggle ──
function toggleTheme() {
    isDark = !isDark;
    document.body.dataset.theme = isDark ? 'dark' : 'light';
    localStorage.setItem('jd-theme', isDark ? 'dark' : 'light');
    requestRender();
}

function loadTheme() {
    const saved = localStorage.getItem('jd-theme');
    if (saved === 'light') { isDark = false; document.body.dataset.theme = 'light'; }
}

$id('theme-toggle').addEventListener('click', toggleTheme);

// ── Clock ──
function updateClock() {
    const now = new Date();
    $id('clock-time').textContent = now.toTimeString().split(' ')[0];
}
setInterval(updateClock, 1000);

// ── Helpers ──
function fmtUp(s) {
    const h = Math.floor(s / 3600).toString().padStart(2, '0');
    const m = Math.floor((s % 3600) / 60).toString().padStart(2, '0');
    const sec = Math.floor(s % 60).toString().padStart(2, '0');
    return `${h}:${m}:${sec}`;
}
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function lerpColor(c1, c2, t) {
    return [Math.round(lerp(c1[0], c2[0], t)), Math.round(lerp(c1[1], c2[1], t)), Math.round(lerp(c1[2], c2[2], t))];
}

// ── State Colors ──
function stateAccent(state) {
    if (state === 'JAMMING') return { color: '#ef4444', glow: 'rgba(239,68,68,0.25)' };
    if (state === 'WATCH')   return { color: '#f0b429', glow: 'rgba(240,180,41,0.25)' };
    return { color: '#00e68a', glow: 'rgba(0,230,138,0.25)' };
}

function applyStateTheme(state) {
    const a = stateAccent(state);
    document.documentElement.style.setProperty('--accent', a.color);
    document.documentElement.style.setProperty('--accent-glow', a.glow);
    document.documentElement.style.setProperty('--accent-dim', a.glow.replace(/[\d.]+\)$/, '0.1)'));
    const badge = $id('state-badge');
    if (badge.textContent !== state) {
        badge.textContent = state;
        badge.dataset.state = state;
    }
}

// ── Score Ring ──
function updateRing(score) {
    const ring = $id('ring-fill');
    if (!ring) return;
    const pct = clamp(score / 99, 0, 1);
    ring.style.strokeDashoffset = 283 - pct * 283;
}

// ── Canvas Color Helpers (Theme-Aware) ──
function canvasColors() {
    if (isDark) return {
        bg: '#080c10', grid: 'rgba(255,255,255,0.05)', gridText: 'rgba(255,255,255,0.2)',
        text: 'rgba(255,255,255,0.5)', line: '#00e68a', fill: 'rgba(0,230,138,0.08)',
        nfLine: 'rgba(255,255,255,0.15)', zero: 'rgba(255,255,255,0.1)'
    };
    return {
        bg: '#eaecf0', grid: 'rgba(0,0,0,0.06)', gridText: 'rgba(0,0,0,0.25)',
        text: 'rgba(0,0,0,0.45)', line: '#00a85a', fill: 'rgba(0,168,90,0.06)',
        nfLine: 'rgba(0,0,0,0.15)', zero: 'rgba(0,0,0,0.12)'
    };
}

// ── Request Render via AnimationFrame ──
function requestRender() {
    if (!renderPending) {
        renderPending = true;
        requestAnimationFrame(performRender);
    }
}

function performRender() {
    renderPending = false;
    if (latestSpectrum) {
        drawSpectrum(latestSpectrum);
    }
    drawMarginTrend();
    drawWaterfall();
}

// ═══ DRAW SPECTRUM (OPTIMIZED: NO SHADOWBLUR) ═══
function drawSpectrum(data) {
    if (!spectrumCanvas) return;
    const ctx = spectrumCanvas.getContext('2d');
    const w = spectrumCanvas.width, h = spectrumCanvas.height;
    if (w === 0 || h === 0) return;
    const cc = canvasColors();
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = cc.bg;
    ctx.fillRect(0, 0, w, h);

    // Grid Lines
    ctx.strokeStyle = cc.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 1; i < 5; i++) {
        const y = (h / 5) * i;
        ctx.moveTo(0, y); ctx.lineTo(w, y);
        const x = (w / 5) * i;
        ctx.moveTo(x, 0); ctx.lineTo(x, h);
    }
    ctx.stroke();

    // dB Labels
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = cc.gridText;
    for (let i = 1; i < 5; i++) {
        const db = -20 * i;
        ctx.fillText(`${db}`, 4, (h / 5) * i - 3);
    }

    if (!data || data.length === 0) return;

    const step = w / (data.length - 1);
    
    // Path for line and fill
    ctx.beginPath();
    ctx.moveTo(0, h);
    data.forEach((val, i) => {
        const x = i * step;
        const y = h - ((val + 100) * (h / 80));
        ctx.lineTo(x, Math.max(0, Math.min(h, y)));
    });

    // Fill area below line
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fillStyle = cc.fill;
    ctx.fill();

    // Pure Clean Line (No heavy shadowBlur)
    ctx.beginPath();
    data.forEach((val, i) => {
        const x = i * step;
        const y = h - ((val + 100) * (h / 80));
        const clampedY = Math.max(0, Math.min(h, y));
        if (i === 0) ctx.moveTo(x, clampedY); else ctx.lineTo(x, clampedY);
    });
    ctx.strokeStyle = accent || cc.line;
    ctx.lineWidth = 2.5; // Slightly thicker line to compensate for lack of glow
    ctx.stroke();
}

// ═══ DRAW MARGIN TREND (OPTIMIZED: NO SHADOWBLUR) ═══
function drawMarginTrend() {
    if (!marginCanvas) return;
    const ctx = marginCanvas.getContext('2d');
    const w = marginCanvas.width, h = marginCanvas.height;
    if (w === 0 || h === 0) return;
    const cc = canvasColors();

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = cc.bg;
    ctx.fillRect(0, 0, w, h);

    // Zero line (dashed)
    const midY = h * 0.6;
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = cc.zero;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, midY); ctx.lineTo(w, midY); ctx.stroke();
    ctx.setLineDash([]);

    // Label
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillStyle = cc.gridText;
    ctx.fillText('0 dB', 4, midY - 4);

    if (marginHistory.length < 2) return;

    const count = marginHistory.length;
    const step = w / (MARGIN_MAX - 1);
    const rangeDB = 40; // -20 to +20

    ctx.beginPath();
    marginHistory.forEach((val, i) => {
        const x = i * step;
        const norm = clamp((val + rangeDB / 2) / rangeDB, 0, 1);
        const y = h - norm * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });

    // Color based on latest value
    const last = marginHistory[marginHistory.length - 1];
    let lineColor;
    if (last > 5) lineColor = '#ef4444';
    else if (last > 0) lineColor = '#f0b429';
    else lineColor = '#00e68a';

    // Draw Line (No heavy shadowBlur)
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Fill under trend line
    ctx.lineTo((count - 1) * step, midY);
    ctx.lineTo(0, midY);
    ctx.closePath();
    ctx.fillStyle = lineColor;
    ctx.globalAlpha = 0.08;
    ctx.fill();
    ctx.globalAlpha = 1.0;
}

// ═══ WATERFALL SPECTROGRAM (OPTIMIZED: 40 BINS) ═══
function wfColor(dbfs) {
    const t = clamp((dbfs + 100) / 70, 0, 1);
    let c;
    if (t < 0.2)       c = lerpColor([8, 10, 30],    [0, 80, 180],   t / 0.2);
    else if (t < 0.4)  c = lerpColor([0, 80, 180],   [0, 180, 120],  (t - 0.2) / 0.2);
    else if (t < 0.65) c = lerpColor([0, 180, 120],  [220, 200, 0],  (t - 0.4) / 0.25);
    else if (t < 0.85) c = lerpColor([220, 200, 0],  [240, 80, 20],  (t - 0.65) / 0.2);
    else                c = lerpColor([240, 80, 20],  [255, 255, 255],(t - 0.85) / 0.15);
    return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function drawWaterfall() {
    if (!waterfallCanvas || waterfallData.length === 0) return;
    const ctx = waterfallCanvas.getContext('2d');
    const w = waterfallCanvas.width, h = waterfallCanvas.height;
    if (w === 0 || h === 0) return;

    ctx.clearRect(0, 0, w, h);
    const rowH = Math.max(1, h / WATERFALL_ROWS);
    const rows = waterfallData.length;

    for (let r = 0; r < rows; r++) {
        const spectrum = waterfallData[r];
        const cols = spectrum.length;
        const colW = w / cols;
        const y = r * rowH;
        
        // Draw larger blocks to reduce rendering context switches
        for (let c = 0; c < cols; c++) {
            ctx.fillStyle = wfColor(spectrum[c]);
            ctx.fillRect(c * colW, y, Math.ceil(colW), Math.ceil(rowH));
        }
    }
}

// ═══ SESSION STATS ═══
function updateSession(m) {
    if (!m) return;
    if (m.peak_p > session.maxPeak) session.maxPeak = m.peak_p;
    if (m.floor_rise > session.peakRise) session.peakRise = m.floor_rise;
    session.nfSum += m.noise_floor;
    session.nfCount++;

    // Count state transitions
    if (m.state !== session.lastState) {
        if (m.state === 'JAMMING') session.jamCount++;
        if (m.state === 'WATCH') session.watchCount++;
        session.lastState = m.state;
    }

    $id('ss-max-peak').textContent = session.maxPeak > -200 ? session.maxPeak.toFixed(1) + ' dBFS' : '— dBFS';
    $id('ss-avg-nf').textContent = session.nfCount > 0 ? (session.nfSum / session.nfCount).toFixed(1) + ' dBFS' : '— dBFS';
    $id('ss-peak-rise').textContent = session.peakRise > 0 ? '+' + session.peakRise.toFixed(1) + ' dB' : '0.0 dB';
    $id('ss-jam-count').textContent = session.jamCount;
    $id('ss-watch-count').textContent = session.watchCount;
}

// ═══ FETCH STATUS ═══
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        if (data.real_time) $id('clock-time').textContent = data.real_time;
        if (data.real_date) $id('clock-date').textContent = data.real_date.toUpperCase();

        if (data.metrics) {
            const m = data.metrics;
            applyStateTheme(m.state);

            $id('score-num').textContent = Math.round(m.score).toString().padStart(2, '0');
            updateRing(m.score);

            $id('nf-val').textContent = m.noise_floor.toFixed(1);
            $id('peak-val').textContent = m.peak_p.toFixed(1);

            const rise = m.floor_rise;
            const riseEl = $id('rise-val');
            riseEl.textContent = (rise >= 0 ? '+' : '') + rise.toFixed(1);
            riseEl.style.color = rise > 5 ? '#ef4444' : '';

            // SNR = Peak - Noise Floor
            const snr = m.peak_p - m.noise_floor;
            $id('snr-val').textContent = snr.toFixed(1);

            // Margin
            const margin = m.margin || 0;
            $id('margin-val').textContent = (margin >= 0 ? '+' : '') + margin.toFixed(1) + ' dB';

            // Margin trend history
            marginHistory.push(margin);
            if (marginHistory.length > MARGIN_MAX) marginHistory.shift();

            // Session
            updateSession(m);
        }

        if (data.uptime !== undefined) $id('uptime-val').textContent = fmtUp(data.uptime);
        if (data.bearing !== undefined) {
            $id('bearing-val').textContent = Math.round(data.bearing).toString().padStart(3, '0') + '°';
            $id('ss-bearing').textContent = Math.round(data.bearing).toString().padStart(3, '0') + '°';
        }
        if (data.gain !== undefined) $id('ss-gain').textContent = data.gain.toFixed(1) + ' dB';

        if (data.spectrum) {
            latestSpectrum = data.spectrum;

            // Waterfall accumulation
            const now = Date.now();
            if (now - lastWfTime >= WATERFALL_ADD_MS) {
                // Downsample to 40 bins (reduced from 60 for better performance)
                const src = data.spectrum;
                const bins = 40;
                const step = Math.max(1, Math.floor(src.length / bins));
                const row = [];
                for (let i = 0; i < bins; i++) {
                    const idx = Math.min(i * step, src.length - 1);
                    row.push(src[idx]);
                }
                waterfallData.push(row);
                if (waterfallData.length > WATERFALL_ROWS) waterfallData.shift();
                lastWfTime = now;
            }
        }
        
        // Batch and defer all renders to requestAnimationFrame
        requestRender();
        
    } catch (e) { console.error('Status fetch error:', e); }
    setTimeout(fetchStatus, POLL_MS);
}

// ═══ FETCH HISTORY ═══
async function fetchHistory() {
    try {
        const res = await fetch('/api/history?limit=200');
        const data = await res.json();
        if (!data || data.length === 0) return;
        allLogs = data;
        renderLogs();
    } catch (e) { console.error('History fetch error:', e); }
}

function renderLogs() {
    const tbody = $id('log-body');
    if (!tbody) return;
    const filtered = activeFilter === 'ALL' ? allLogs : allLogs.filter(r => r.state === activeFilter);

    let html = '';
    filtered.forEach(row => {
        const ts = row.timestamp || '';
        const time = ts.includes(' ') ? ts.split(' ')[1] : ts;
        const nf = typeof row.noise_floor === 'number' ? row.noise_floor.toFixed(1) : '—';
        const peak = typeof row.peak_p === 'number' ? row.peak_p.toFixed(1) : '—';
        const rise = typeof row.floor_rise === 'number' ? ((row.floor_rise >= 0 ? '+' : '') + row.floor_rise.toFixed(1)) : '—';
        const margin = (typeof row.peak_p === 'number' && typeof row.noise_floor === 'number')
            ? ((row.peak_p - row.noise_floor) >= 0 ? '+' : '') + (row.peak_p - row.noise_floor).toFixed(1)
            : '—';
        html += `<tr>
            <td>${time}</td>
            <td><span class="state-pill" data-state="${row.state}">${row.state}</span></td>
            <td>${row.score}</td>
            <td>${row.bearing_deg || 0}°</td>
            <td>${peak}</td>
            <td>${rise}</td>
            <td>${nf}</td>
            <td>${margin}</td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

// ═══ FILTER TABS ═══
document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        activeFilter = tab.dataset.filter;
        renderLogs();
    });
});

// ═══ BUTTONS ═══
$id('export-btn').addEventListener('click', () => { window.location.href = '/api/export'; });
$id('clear-btn').addEventListener('click', async () => {
    if (confirm('Clear all detection logs?')) {
        await fetch('/api/clear', { method: 'POST' });
        allLogs = [];
        renderLogs();
    }
});

// ═══ CANVAS RESIZE ═══
function resizeCanvas(canvas) {
    if (!canvas) return;
    const parent = canvas.parentElement;
    if (parent.clientWidth > 0 && parent.clientHeight > 0) {
        canvas.width = parent.clientWidth;
        canvas.height = parent.clientHeight;
    }
}

function resizeAll() {
    resizeCanvas(spectrumCanvas);
    resizeCanvas(marginCanvas);
    resizeCanvas(waterfallCanvas);
}

// ═══ INIT ═══
window.addEventListener('load', () => {
    loadTheme();
    updateClock();
    resizeAll();
    fetchStatus();
    fetchHistory();
    setInterval(fetchHistory, 5000);
});
window.addEventListener('resize', resizeAll);