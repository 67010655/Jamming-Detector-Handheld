/* ═══════════════════════════════════════════════
   GNSS Jamming Detector — Dashboard Script
   ═══════════════════════════════════════════════ */

// ── Constants ──
const POLL_MS = 500; 
const MARGIN_MAX = 50;
const WATERFALL_ROWS = 60; 
const WATERFALL_ADD_MS = 500;
const LOW_POWER_VISUALS = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4;
const SPECTRUM_RENDER_FPS = LOW_POWER_VISUALS ? 8 : 14;
const SPECTRUM_MORPH_MS = Math.min(420, POLL_MS * 0.85);

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
let spectrumBgCanvas = null;
let spectrumBgKey = '';
let spectrumFromData = null;
let spectrumTargetData = null;
let spectrumDisplayData = null;
let spectrumAnimStart = 0;
let spectrumAnimFrame = null;
let lastSpectrumRenderAt = 0;

// Cache the last printed DOM values to avoid forced layouts (Value Differencing)
const domCache = {};

const session = {
    maxPeak: -200, peakRise: 0, nfSum: 0, nfCount: 0,
    jamCount: 0, watchCount: 0, lastState: ''
};

// ── Optimized DOM Text Updater (Throttles DOM writes) ──
function setDomText(id, val) {
    if (domCache[id] !== val) {
        const el = $id(id);
        if (el) el.textContent = val;
        domCache[id] = val;
    }
}

// ── Theme Toggle ──
function toggleTheme() {
    isDark = !isDark;
    document.body.dataset.theme = isDark ? 'dark' : 'light';
    localStorage.setItem('jd-theme', isDark ? 'dark' : 'light');
    
    // Force redraw on theme switch since colors changed
    spectrumBgCanvas = null;
    spectrumBgKey = '';
    drawSpectrum(spectrumDisplayData || lastSpectrumData);
    drawMarginTrend();
    drawWaterfall();
}

function loadTheme() {
    const saved = localStorage.getItem('jd-theme');
    if (saved === 'light') { isDark = false; document.body.dataset.theme = 'light'; }
}

$id('theme-toggle').addEventListener('click', toggleTheme);

// ── Ultra-Smooth Client Clock (Local time, avoids server time jitters) ──
function updateClock() {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    setDomText('clock-time', timeStr);
}
// Start immediate and run at smooth 1Hz interval
updateClock();
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
function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
}
async function readError(res) {
    try {
        const data = await res.json();
        return data.error || data.message || `Request failed (${res.status})`;
    } catch (e) {
        return `Request failed (${res.status})`;
    }
}
async function fetchJson(url) {
    const res = await fetch(url);
    const type = res.headers.get('content-type') || '';
    if (!res.ok || !type.includes('application/json')) {
        throw new Error(`API unavailable: ${url}`);
    }
    return res.json();
}

// ── State Colors ──
function stateAccent(state) {
    if (isDark) {
        if (state === 'JAMMING') return { color: '#ef4444', glow: 'rgba(239,68,68,0.25)' };
        if (state === 'WATCH')   return { color: '#f0b429', glow: 'rgba(240,180,41,0.25)' };
        return { color: '#00e68a', glow: 'rgba(0,230,138,0.25)' };
    }
    // Light mode: darker, more readable colors
    if (state === 'JAMMING') return { color: '#dc2626', glow: 'rgba(220,38,38,0.3)' };
    if (state === 'WATCH')   return { color: '#d97706', glow: 'rgba(217,119,6,0.3)' };
    return { color: '#059669', glow: 'rgba(5,150,105,0.3)' };
}

function applyStateTheme(state) {
    const a = stateAccent(state);
    
    // Only update CSS variables if they actually change
    if (domCache['--current-state'] !== state) {
        document.documentElement.style.setProperty('--accent', a.color);
        document.documentElement.style.setProperty('--accent-glow', a.glow);
        document.documentElement.style.setProperty('--accent-dim', a.glow.replace(/[\d.]+\)$/, '0.1)'));
        
        const badge = $id('state-badge');
        if (badge) {
            badge.textContent = state;
            badge.dataset.state = state;
        }
        domCache['--current-state'] = state;
    }
}

// ── Score Ring ──
function updateRing(score) {
    const ring = $id('ring-fill');
    if (!ring) return;
    const pct = clamp(score / 99, 0, 1);
    const offset = 283 - pct * 283;
    
    if (domCache['ring-offset'] !== offset) {
        ring.style.strokeDashoffset = offset;
        domCache['ring-offset'] = offset;
    }
}

// ── Canvas Color Helpers (Theme-Aware) ──
function canvasColors() {
    if (isDark) return {
        bg: '#080c10', grid: 'rgba(255,255,255,0.04)', gridText: 'rgba(255,255,255,0.2)',
        text: 'rgba(255,255,255,0.5)', line: '#00e68a', fill: 'rgba(0,230,138,0.07)',
        nfLine: 'rgba(255,255,255,0.15)', zero: 'rgba(255,255,255,0.1)'
    };
    return {
        bg: '#e5e7eb', grid: 'rgba(0,0,0,0.08)', gridText: 'rgba(0,0,0,0.35)',
        text: 'rgba(0,0,0,0.55)', line: '#047857', fill: 'rgba(4,120,87,0.08)',
        nfLine: 'rgba(0,0,0,0.2)', zero: 'rgba(0,0,0,0.15)'
    };
}

// Keep a reference to latest spectrum array for redraws after resize/theme changes.
let lastSpectrumData = null;

function getSpectrumBackground(w, h, cc) {
    const key = `${w}x${h}:${isDark ? 'd' : 'l'}`;
    if (spectrumBgCanvas && spectrumBgKey === key) return spectrumBgCanvas;

    const bg = document.createElement('canvas');
    bg.width = w;
    bg.height = h;
    const bgCtx = bg.getContext('2d');

    bgCtx.fillStyle = cc.bg;
    bgCtx.fillRect(0, 0, w, h);
    bgCtx.strokeStyle = cc.grid;
    bgCtx.lineWidth = 1;
    bgCtx.beginPath();
    for (let i = 1; i < 5; i++) {
        const y = (h / 5) * i;
        bgCtx.moveTo(0, y);
        bgCtx.lineTo(w, y);
        const x = (w / 5) * i;
        bgCtx.moveTo(x, 0);
        bgCtx.lineTo(x, h);
    }
    bgCtx.stroke();

    bgCtx.font = '10px "JetBrains Mono", monospace';
    bgCtx.fillStyle = cc.gridText;
    for (let i = 1; i < 5; i++) {
        const db = -20 * i;
        bgCtx.fillText(`${db}`, 4, (h / 5) * i - 3);
    }

    spectrumBgCanvas = bg;
    spectrumBgKey = key;
    return bg;
}

// ═══ DRAW SPECTRUM ═══
function drawSpectrum(data) {
    if (!spectrumCanvas || !data || data.length === 0) return;
    const ctx = spectrumCanvas.getContext('2d');
    const w = spectrumCanvas.width, h = spectrumCanvas.height;
    if (w === 0 || h === 0) return;
    const cc = canvasColors();
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();

    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(getSpectrumBackground(w, h, cc), 0, 0);

    const step = data.length > 1 ? w / (data.length - 1) : w;
    const points = data.map((val, i) => {
        const x = i * step;
        const y = h - ((val + 100) * (h / 80));
        return [x, Math.max(0, Math.min(h, y))];
    });
    
    // Path for line and fill
    ctx.beginPath();
    ctx.moveTo(0, h);
    points.forEach(([x, y]) => ctx.lineTo(x, y));

    // Fill area below line
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fillStyle = cc.fill;
    ctx.fill();

    // Clean Line
    ctx.beginPath();
    points.forEach(([x, y], i) => {
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = accent || cc.line;
    ctx.lineWidth = 2.2; 
    ctx.stroke();
}

// ═══ SPECTRUM SMOOTHING ═══
function setSpectrumTarget(data) {
    if (!data || data.length === 0) return;
    const next = data.map(value => {
        const n = Number(value);
        return Number.isFinite(n) ? n : -100;
    });

    if (!spectrumDisplayData || spectrumDisplayData.length !== next.length) {
        spectrumFromData = next;
        spectrumTargetData = next;
        spectrumDisplayData = next.slice();
        drawSpectrum(spectrumDisplayData);
        return;
    }

    spectrumFromData = spectrumDisplayData.slice();
    spectrumTargetData = next;
    spectrumAnimStart = performance.now();
    startSpectrumAnimation();
}

function startSpectrumAnimation() {
    if (spectrumAnimFrame) return;
    spectrumAnimFrame = requestAnimationFrame(animateSpectrum);
}

function animateSpectrum(now) {
    spectrumAnimFrame = null;
    if (!spectrumFromData || !spectrumTargetData) return;

    const frameMs = 1000 / SPECTRUM_RENDER_FPS;
    const rawT = clamp((now - spectrumAnimStart) / SPECTRUM_MORPH_MS, 0, 1);
    const t = easeOutCubic(rawT);

    if (now - lastSpectrumRenderAt >= frameMs || rawT >= 1) {
        for (let i = 0; i < spectrumTargetData.length; i++) {
            spectrumDisplayData[i] = lerp(spectrumFromData[i], spectrumTargetData[i], t);
        }
        drawSpectrum(spectrumDisplayData);
        lastSpectrumRenderAt = now;
    }

    if (rawT < 1) {
        startSpectrumAnimation();
    } else {
        spectrumDisplayData = spectrumTargetData.slice();
    }
}

// ═══ DRAW MARGIN TREND (CALLED ONLY WHEN NEW DATA ARRIVES) ═══
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

    // Draw Line
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Fill under trend line
    ctx.lineTo((count - 1) * step, midY);
    ctx.lineTo(0, midY);
    ctx.closePath();
    ctx.fillStyle = lineColor;
    ctx.globalAlpha = 0.06;
    ctx.fill();
    ctx.globalAlpha = 1.0;
}

// ═══ WATERFALL SPECTROGRAM (CALLED ONLY WHEN NEW ROW IS ADDED - 2Hz MAX) ═══
function wfColor(dbfs) {
    const t = clamp((dbfs + 100) / 70, 0, 1);
    let c;
    if (t < 0.2)       c = lerpColor([8, 10, 30],    [0, 80, 180],   t / 0.2);
    else if (t < 0.4)  c = lerpColor([0, 80, 180],   [0, 180, 120],  (t - 0.2) / 0.2);
    else if (t < 0.65) c = lerpColor([0, 180, 120],  [220, 200, 0],  (t - 0.4) / 0.25);
    else if (t < 0.85) c = lerpColor([220, 200, 0],  [240, 80, 20],  (t - 0.65) / 0.2);
    else                c = lerpColor([240, 80, 20],  [255, 255, 255],(t - 0.85) / 0.15);
    return c;
}

function drawWaterfall() {
    if (!waterfallCanvas || waterfallData.length === 0) return;
    const ctx = waterfallCanvas.getContext('2d');
    const w = waterfallCanvas.width, h = waterfallCanvas.height;
    if (w === 0 || h === 0) return;

    // Scroll the existing canvas and draw only the newest row.
    const rowH = Math.max(2, Math.ceil(h / WATERFALL_ROWS));
    if (h > rowH) {
        ctx.drawImage(waterfallCanvas, 0, rowH, w, h - rowH, 0, 0, w, h - rowH);
    }

    const spectrum = waterfallData[waterfallData.length - 1];
    const cols = spectrum.length;
    const y = h - rowH;
    for (let c = 0; c < cols; c++) {
        const rgb = wfColor(spectrum[c]);
        const xStart = Math.round(c * w / cols);
        const xEnd = Math.round((c + 1) * w / cols);
        ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
        ctx.fillRect(xStart, y, Math.max(1, xEnd - xStart), rowH);
    }
}

// ═══ SESSION STATS ═══
function updateSession(m) {
    if (!m) return;
    if (m.peak_p > session.maxPeak) session.maxPeak = m.peak_p;
    if (m.floor_rise > session.peakRise) session.peakRise = m.floor_rise;
    session.nfSum += m.noise_floor;
    session.nfCount++;

    if (m.state !== session.lastState) {
        if (m.state === 'JAMMING') session.jamCount++;
        if (m.state === 'WATCH') session.watchCount++;
        session.lastState = m.state;
    }

    setDomText('ss-max-peak', session.maxPeak > -200 ? session.maxPeak.toFixed(1) + ' dBFS' : '— dBFS');
    setDomText('ss-avg-nf', session.nfCount > 0 ? (session.nfSum / session.nfCount).toFixed(1) + ' dBFS' : '— dBFS');
    setDomText('ss-peak-rise', session.peakRise > 0 ? '+' + session.peakRise.toFixed(1) + ' dB' : '0.0 dB');
    setDomText('ss-jam-count', session.jamCount.toString());
    setDomText('ss-watch-count', session.watchCount.toString());
}

// ═══ FETCH STATUS ═══
async function fetchStatus() {
    try {
        const data = await fetchJson('/api/status');

        // Sync local clock date if provided (run once or verify shift)
        if (data.real_date) {
            setDomText('clock-date', data.real_date.toUpperCase());
        }

        if (data.metrics) {
            const m = data.metrics;
            applyStateTheme(m.state);

            setDomText('score-num', Math.round(m.score).toString().padStart(2, '0'));
            updateRing(m.score);

            setDomText('nf-val', m.noise_floor.toFixed(1));
            setDomText('peak-val', m.peak_p.toFixed(1));

            const rise = m.floor_rise;
            setDomText('rise-val', (rise >= 0 ? '+' : '') + rise.toFixed(1));
            
            const riseEl = $id('rise-val');
            if (riseEl) {
                riseEl.style.color = rise > 5 ? '#ef4444' : '';
            }

            // SNR = Peak - Noise Floor
            const snr = m.peak_p - m.noise_floor;
            setDomText('snr-val', snr.toFixed(1));

            // Margin
            const margin = m.margin || 0;
            setDomText('margin-val', (margin >= 0 ? '+' : '') + margin.toFixed(1) + ' dB');

            // Margin trend history
            marginHistory.push(margin);
            if (marginHistory.length > MARGIN_MAX) marginHistory.shift();

            // Session Stats
            updateSession(m);
        }

        if (data.uptime !== undefined) setDomText('uptime-val', fmtUp(data.uptime));
        if (data.bearing !== undefined) {
            const bearingStr = Math.round(data.bearing).toString().padStart(3, '0') + '°';
            setDomText('bearing-val', bearingStr);
            setDomText('ss-bearing', bearingStr);
        }
        if (data.gain !== undefined) setDomText('ss-gain', data.gain.toFixed(1) + ' dB');

        let waterfallChanged = false;

        if (data.spectrum) {
            lastSpectrumData = data.spectrum;
            setSpectrumTarget(data.spectrum);

            // Waterfall accumulation
            const now = Date.now();
            if (now - lastWfTime >= WATERFALL_ADD_MS) {
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
                waterfallChanged = true;
            }
        }
        
        // ── EVENT-DRIVEN CANVAS RENDERING ──
        // Only trigger drawing when new data arrives (4Hz max) instead of 60 FPS loop!
        // This is a massive CPU optimization.
        requestAnimationFrame(() => {
            drawMarginTrend();
            if (waterfallChanged) {
                drawWaterfall();
            }
        });
        
    } catch (e) { console.warn('Status fetch skipped:', e.message || e); }
    setTimeout(fetchStatus, POLL_MS);
}

// ═══ FETCH HISTORY ═══
async function fetchHistory() {
    try {
        const data = await fetchJson('/api/history?limit=200');
        if (!data || data.length === 0) return;
        allLogs = data;
        renderLogs();
    } catch (e) { console.warn('History fetch skipped:', e.message || e); }
}

function escHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderLogs() {
    const tbody = $id('log-body');
    if (!tbody) return;
    const filtered = activeFilter === 'ALL' ? allLogs : allLogs.filter(r => r.state === activeFilter);

    let html = '';
    filtered.forEach(row => {
        const ts = row.timestamp || '';
        const time = escHtml(ts.includes(' ') ? ts.split(' ')[1] : ts);
        const state = escHtml(row.state || '');
        const score = escHtml(row.score ?? '—');
        const bearing = escHtml(row.bearing_deg || 0);
        const nf = typeof row.noise_floor === 'number' ? row.noise_floor.toFixed(1) : '—';
        const peak = typeof row.peak_p === 'number' ? row.peak_p.toFixed(1) : '—';
        const rise = typeof row.floor_rise === 'number' ? ((row.floor_rise >= 0 ? '+' : '') + row.floor_rise.toFixed(1)) : '—';
        const margin = (typeof row.peak_p === 'number' && typeof row.noise_floor === 'number')
            ? ((row.peak_p - row.noise_floor) >= 0 ? '+' : '') + (row.peak_p - row.noise_floor).toFixed(1)
            : '—';
        html += `<tr>
            <td>${time}</td>
            <td><span class="state-pill" data-state="${state}">${state}</span></td>
            <td>${score}</td>
            <td>${bearing}°</td>
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
        document.querySelectorAll('.filter-tab').forEach(t => {
            t.classList.remove('active');
            t.setAttribute('aria-pressed', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-pressed', 'true');
        activeFilter = tab.dataset.filter;
        renderLogs();
    });
});

// ═══ BUTTONS ═══
$id('export-btn').addEventListener('click', async () => {
    try {
        const res = await fetch('/api/export');
        if (!res.ok) {
            alert(await readError(res));
            return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'jamming_history.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('Export failed. Check the dashboard connection.');
    }
});
$id('clear-btn').addEventListener('click', async () => {
    if (confirm('Clear all detection logs?')) {
        try {
            const res = await fetch('/api/clear', { method: 'POST' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                alert(data.error || `Clear failed (${res.status})`);
                return;
            }
            allLogs = [];
            renderLogs();
        } catch (e) {
            alert('Clear failed. Check the dashboard connection.');
        }
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
    spectrumBgCanvas = null;
    spectrumBgKey = '';
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
    initParticles();
});
window.addEventListener('resize', () => {
    resizeAll();
    resizeParticles();
});

// ═══ PARTICLE BACKGROUND SYSTEM ═══
const particleCanvas = document.getElementById('particleCanvas');
const pCtx = particleCanvas ? particleCanvas.getContext('2d') : null;
let particles = [];
// Reduce particle count on mobile/touch devices for extreme smoothness
const isMobile = typeof navigator !== 'undefined' && (navigator.maxTouchPoints > 0 || /Mobi|Android/i.test(navigator.userAgent));
const PARTICLE_COUNT = LOW_POWER_VISUALS ? 0 : (isMobile ? 12 : 32);
const CONNECTION_DIST = 160;
const CONNECTION_DIST_SQ = CONNECTION_DIST * CONNECTION_DIST;

function resizeParticles() {
    if (!particleCanvas) return;
    particleCanvas.width = window.innerWidth;
    particleCanvas.height = window.innerHeight;
}

function createParticle() {
    return {
        x: Math.random() * particleCanvas.width,
        y: Math.random() * particleCanvas.height,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        r: Math.random() * 2.5 + 0.8,
        alpha: Math.random() * 0.6 + 0.3,
        pulse: Math.random() * Math.PI * 2
    };
}

function initParticles() {
    if (!particleCanvas || !pCtx) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (PARTICLE_COUNT === 0) return;
    resizeParticles();
    particles = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push(createParticle());
    }
    requestAnimationFrame(animateParticles);
}

function animateParticles() {
    if (document.hidden) {
        requestAnimationFrame(animateParticles);
        return;
    }
    if (!pCtx) return;
    const w = particleCanvas.width, h = particleCanvas.height;
    if (w === 0 || h === 0) { requestAnimationFrame(animateParticles); return; }

    pCtx.clearRect(0, 0, w, h);

    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#00e68a';

    // Parse accent color to RGB for alpha manipulation
    let r = 0, g = 230, b = 138;
    if (accent.startsWith('#') && accent.length === 7) {
        r = parseInt(accent.slice(1, 3), 16);
        g = parseInt(accent.slice(3, 5), 16);
        b = parseInt(accent.slice(5, 7), 16);
    }

    // Update & draw particles
    for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.pulse += 0.015;

        // Wrap edges
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;

        const glow = p.alpha * (0.7 + 0.3 * Math.sin(p.pulse));
        pCtx.beginPath();
        pCtx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        pCtx.fillStyle = `rgba(${r},${g},${b},${glow})`;
        pCtx.fill();

        // Draw connections to nearby particles with high-performance early-outs
        for (let j = i + 1; j < particles.length; j++) {
            const q = particles[j];
            const dx = p.x - q.x;
            if (Math.abs(dx) >= CONNECTION_DIST) continue;

            const dy = p.y - q.y;
            if (Math.abs(dy) >= CONNECTION_DIST) continue;

            const distSq = dx * dx + dy * dy;
            if (distSq < CONNECTION_DIST_SQ) {
                const dist = Math.sqrt(distSq);
                const lineAlpha = (1 - dist / CONNECTION_DIST) * 0.2;
                pCtx.beginPath();
                pCtx.moveTo(p.x, p.y);
                pCtx.lineTo(q.x, q.y);
                pCtx.strokeStyle = `rgba(${r},${g},${b},${lineAlpha})`;
                pCtx.lineWidth = 0.8;
                pCtx.stroke();
            }
        }
    }

    requestAnimationFrame(animateParticles);
}
