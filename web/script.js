const POLL_INTERVAL_MS = 100; // 10 FPS
let canvas = document.getElementById('spectrumCanvas');
let ctx = canvas.getContext('2d');

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

async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Update Text Metrics
        const m = data.metrics;
        if (m && m.state) {
            document.body.setAttribute('data-state', m.state);
            document.getElementById('state-badge').innerText = m.state;

            // Short text mapping
            const shortMap = { "SCANNING": "SCAN", "WATCH": "WTCH", "JAMMING": "JAM!" };
            document.getElementById('state-text').innerText = shortMap[m.state] || m.state;

            document.getElementById('nf-val').innerText = m.floor_rise !== undefined ? (m.peak_p - m.floor_rise - m.peak_diff).toFixed(1) : "-90.0";
            // Wait, proper NF is missing from metrics dict in detector.py! 
            // Let's rely on calculating it or just printing floor_rise.
            // Actually, we can just show the values given
            document.getElementById('peak-val').innerText = m.peak_p ? m.peak_p.toFixed(1) : "0.0";
            document.getElementById('base-val').innerText = m.baseline_p ? m.baseline_p.toFixed(1) : "0.0";
            document.getElementById('rise-val').innerText = m.floor_rise ? `+${m.floor_rise.toFixed(1)}` : "0.0";

            document.getElementById('score-text').innerText = m.score ? m.score.toString().padStart(2, '0') : "00";

            // Score bar height
            let pct = Math.min(100, Math.max(0, (m.score / 99) * 100));
            document.getElementById('score-bar').style.height = `${pct}%`;

            // Calculate Margin (Using default thresholds from detector.py since not passed explicitly)
            // Warn peak threshold is 18.0
            let warn_peak_thresh = 18.0;
            // Margin = peak_diff - warn_peak_thresh
            let margin = m.peak_diff - warn_peak_thresh;
            let marginStr = margin > 0 ? `+${margin.toFixed(1)}` : margin.toFixed(1);
            document.getElementById('margin-text').innerText = `${marginStr} dB`;
        }

        // Update Uptime
        if (data.uptime !== undefined) {
            document.getElementById('uptime-text').innerText = formatUptime(data.uptime);
        }

        // Update Graph
        if (data.spectrum) {
            drawSpectrum(data.spectrum);
        }

    } catch (error) {
        console.error("Error fetching dashboard data:", error);
    }

    // Schedule next poll
    setTimeout(fetchStatus, POLL_INTERVAL_MS);
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
