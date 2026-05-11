import time
import threading
import numpy as np
try:
    import spidev
    import RPi.GPIO as GPIO
except ImportError:
    spidev = None
    GPIO = None
from PIL import Image, ImageDraw, ImageFont
from dsp import scale_points


class DisplayUI:
    def __init__(self, app, preview=False):
        self.app = app
        self.preview = preview
        self._preview_shown = False
        if not self.preview:
            self._init_display()
        self._init_drawing()
        self._bearing_log = []
        self._history_log = [] # For Mode 2
        self._prev_smooth_y = None
        self._fps_time = time.time()
        self._fps_count = 0
        self._fps_display = 0
        self.view_mode = 0   # 0: Normal, 1: Search, 2: Analytics
        self._touch_zones = {}
        self._touch_ok = False
        self._spi_lock = threading.Lock()
        self._last_pressed = None
        self._pressed_until = 0

        if not self.preview:
            self._init_touch()

    # ── text size helper ────────────────────────────────────────────
    def _get_text_size(self, text, font):
        draw = self.app._draw
        if hasattr(draw, "textbbox"):
            l, t, r, b = draw.textbbox((0, 0), text, font=font)
            return r - l, b - t
        if hasattr(font, "getsize"):
            return font.getsize(text)
        return len(text) * 8, 12

    # ── display init ────────────────────────────────────────────────
    def _init_display(self):
        print("[SYSTEM] Initializing Display (ILI9488)...")
        from luma.core.interface.serial import spi
        from luma.lcd.device import ili9488
        serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25,
                     bus_speed_hz=24000000) # Slightly slower for stability
        self.app.device = ili9488(serial, width=self.app.w,
                                  height=self.app.h, rotate=0)

    def _init_drawing(self):
        self.app._img = Image.new("RGB", (self.app.w, self.app.h), "black")
        self.app._draw = ImageDraw.Draw(self.app._img)
        self._load_fonts()

    # ── fonts ───────────────────────────────────────────────────────
    def _load_fonts(self):
        bold = ["DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "C:/Windows/Fonts/arialbd.ttf"]
        regular = ["DejaVuSans.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                   "C:/Windows/Fonts/arial.ttf"]
        mono = ["DejaVuSansMono-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                "C:/Windows/Fonts/consola.ttf"]

        def _try(paths, size):
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        self._f_title     = _try(bold, 12)
        self._f_subtitle  = _try(regular, 10)
        self._f_status    = _try(bold, 20)
        self._f_state_big = _try(bold, 26)
        self._f_score_big = _try(mono, 36)
        self._f_score_sub = _try(regular, 12)
        self._f_label     = _try(regular, 9)
        self._f_value     = _try(bold, 22)
        self._f_unit      = _try(regular, 9)
        self._f_brg       = _try(bold, 16)
        self._f_compass   = _try(regular, 9)
        self._f_small     = _try(bold, 9)
        self._f_footer    = _try(bold, 8)
        self._f_fps       = _try(bold, 16)
        self._f_fps_label = _try(regular, 9)
        self._f_dblabel   = _try(regular, 8)
        self._f_btn       = _try(bold, 10)

    # ── colour helpers ──────────────────────────────────────────────
    @staticmethod
    def _dim(c, f):
        return tuple(max(0, min(255, int(v * f))) for v in c)

    @staticmethod
    def _lerp(c1, c2, t):
        t = max(0.0, min(1.0, t))
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

    @staticmethod
    def _smooth(pts, n):
        if len(pts) < 3:
            return pts
        xs = np.array([p[0] for p in pts], dtype=np.float64)
        ys = np.array([p[1] for p in pts], dtype=np.float64)
        x_new = np.linspace(xs[0], xs[-1], n)
        y_new = np.interp(x_new, xs, ys)
        k = max(7, min(11, n // 30))
        if k % 2 == 0:
            k += 1
        pad_w = k // 2
        y_padded = np.pad(y_new, pad_width=pad_w, mode='edge')
        y_s = np.convolve(y_padded, np.ones(k) / k, mode='valid')
        return list(zip(x_new.astype(int),
                        np.clip(y_s, ys.min(), ys.max()).astype(int)))

    # ── bearing helpers ─────────────────────────────────────────────
    def record_bearing(self, angle_deg, peak_dbfs):
        norm = float(np.clip((peak_dbfs + 90) / 30.0, 0.0, 1.0))
        self._bearing_log.append((int(angle_deg) % 360, norm))
        if len(self._bearing_log) > 12:
            self._bearing_log.pop(0)

    def get_best_bearing(self):
        if not self._bearing_log:
            return None
        return max(self._bearing_log, key=lambda x: x[1])[0]

    # ════════════════════════════════════════════════════════════════
    #                   MAIN DRAW ENTRY POINT
    # ════════════════════════════════════════════════════════════════
    def draw_ui(self, metrics, power):
        draw = self.app._draw
        W, H = self.app.w, self.app.h  # 480 × 320

        # FPS
        self._fps_count += 1
        now = time.time()
        if now - self._fps_time >= 1.0:
            self._fps_display = self._fps_count
            self._fps_count = 0
            self._fps_time = now
        fps_val = self._fps_display if self._fps_display > 0 else self.app.target_fps

        state = metrics["state"]
        nf    = metrics.get("noise_floor", self.app.noise_floor)
        peak  = metrics["peak_p"]
        rise  = metrics["floor_rise"]
        score = metrics.get("score", 0)
        margin_val = metrics.get("margin", 0.0)
        
        # Log history for Mode 2
        self._history_log.append(margin_val)
        if len(self._history_log) > 50: self._history_log.pop(0)

        # ── theme colours ───────────────────────────────────────────
        if state == "JAMMING":
            accent   = (255, 80, 90)
            hdr_bg   = (40, 8, 10)
            grid     = (60, 20, 25)
            fill_c   = (80, 15, 20)
        elif state == "WATCH":
            accent   = (255, 220, 50)
            hdr_bg   = (50, 44, 10)
            grid     = (80, 70, 15)
            fill_c   = (100, 80, 10)
        else:
            accent   = (0, 255, 136)
            hdr_bg   = (8, 40, 20)
            grid     = (0, 80, 50)
            fill_c   = (0, 100, 60)

        white  = (255, 255, 255)
        lbl    = (255, 255, 255)

        # ── layout ──────────────────────────────────────────────────
        hdr_b   = 44
        lp_r    = 106
        rp_l    = 418
        foot_t  = 284

        # Background
        draw.rectangle((0, 0, W - 1, H - 1), fill=(3, 3, 3))

        # HEADER
        draw.rectangle((0, 0, W, hdr_b), fill=hdr_bg)
        draw.line((0, hdr_b, W, hdr_b), fill=accent, width=1)
        draw.text((8, 5), "GNSS L1 JAMMING DETECTOR HANDHELD", fill=white, font=self._f_title)
        sub = f"GPS L1 | 1575.42 MHz | G:{self.app.gain_db}dB | MODE:{self.view_mode}"
        draw.text((8, 23), sub, fill=accent, font=self._f_subtitle)
        sw, _ = self._get_text_size(state, self._f_status)
        draw.text((W - sw - 14, 10), state, fill=accent, font=self._f_status)

        # LEFT PANEL — 6 CONTROL BUTTONS
        draw.rectangle((0, hdr_b, lp_r, foot_t), fill=(6, 6, 6))
        draw.line((lp_r, hdr_b, lp_r, foot_t), fill=accent, width=1)

        btns = ["VIEW", "SNAP", "CALIB", "MUTE", "GAIN", "EXIT"]
        btn_w, btn_h, btn_gap = lp_r - 12, 30, 5
        btn_x, btn_top = 6, hdr_b + 6
        self._touch_zones = {}

        for i, label in enumerate(btns):
            by = btn_top + i * (btn_h + btn_gap)
            is_pressed = (label == self._last_pressed and now < self._pressed_until)
            bg_c = white if is_pressed else (25, 25, 40)
            tx_c = (0,0,0) if is_pressed else white
            
            draw.rectangle((btn_x, by, btn_x + btn_w, by + btn_h), fill=bg_c, outline=accent)
            if label == "GAIN":
                draw.line((btn_x + btn_w//2, by, btn_x + btn_w//2, by+btn_h), fill=accent)
                draw.text((btn_x+12, by+8), "-", fill=tx_c, font=self._f_btn)
                draw.text((btn_x+btn_w-18, by+8), "+", fill=tx_c, font=self._f_btn)
                draw.text((btn_x+32, by+8), "GAIN", fill=tx_c, font=self._f_btn)
            else:
                tw, th = self._get_text_size(label, self._f_btn)
                draw.text((btn_x + (btn_w - tw)//2, by + (btn_h - th)//2), label, fill=tx_c, font=self._f_btn)
            self._touch_zones[label] = (btn_x, by, btn_x + btn_w, by + btn_h)

        # RIGHT PANEL
        draw.rectangle((rp_l, hdr_b, W, foot_t), fill=(6, 6, 6))
        draw.line((rp_l, hdr_b, rp_l, foot_t), fill=accent, width=1)
        draw.text((rp_l + 8, hdr_b + 8), "SCORE", fill=lbl, font=self._f_label)
        sc_str = f"{score:02d}"
        draw.text((rp_l + 12, hdr_b + 22), sc_str, fill=accent, font=self._f_score_big)
        draw.text((rp_l + 25, hdr_b + 58), "/99", fill=white, font=self._f_score_sub)

        # ── MAIN CONTENT AREA ───────────────────────────────────────
        content_w = rp_l - lp_r
        if self.view_mode == 1: # SEARCH MODE (Radar Focus)
            self._draw_radar(draw, lp_r + content_w//2, (hdr_b + foot_t)//2, 95, accent, grid, white)
            
        elif self.view_mode == 2: # ANALYTICS MODE (History Focus)
            self._draw_history(draw, lp_r + 15, hdr_b + 40, rp_l - 15, foot_t - 60, accent, grid, white)
            self._draw_spectrum(draw, lp_r + 10, foot_t - 55, rp_l - 10, foot_t - 5, metrics, power, accent, grid, nf, peak, small=True)
            
        else: # NORMAL MODE
            self._draw_spectrum(draw, lp_r + 2, hdr_b + 2, rp_l - 2, 210, metrics, power, accent, grid, nf, peak)
            # Metrics below spectrum
            met_t, met_b = 210, foot_t
            col_w = content_w // 2
            for i, (ml, mv, mu) in enumerate([("NOISE",f"{nf:.1f}","dB"), ("PEAK",f"{peak:.1f}","dB"), ("RISE",f"{rise:+.1f}","dB"), ("MARGIN",f"{margin_val:+.1f}","dB")]):
                mx = lp_r + (i%2)*col_w + 10
                my = met_t + (i//2)*32 + 5
                draw.text((mx, my), ml, fill=lbl, font=self._f_label)
                draw.text((mx, my+12), f"{mv} {mu}", fill=accent, font=self._f_brg)

        # FOOTER
        draw.rectangle((0, foot_t, W, H), fill=(6, 6, 6))
        draw.line((0, foot_t, W, foot_t), fill=accent, width=1)
        draw.text((10, foot_t + 15), "KMITL SPACE ENG | GNSS HANDHELD", fill=white, font=self._f_footer)
        draw.text((W - 60, foot_t + 5), f"FPS: {fps_val}", fill=accent, font=self._f_label)

        # Output
        if self.preview: self.app._img.save("preview.png")
        else:
            with self._spi_lock: self.app.device.display(self.app._img)

    def _draw_spectrum(self, draw, l, t, r, b, metrics, power, accent, grid, nf, peak, small=False):
        draw.rectangle((l, t, r, b), outline=accent)
        sw, sh = r - l, b - t
        pts = scale_points(power, nf, sw, t+5, b-5)
        pts_off = [(px + l, py) for px, py in pts]
        if len(pts_off) > 2:
            sm = self._smooth(pts_off, sw)
            poly = list(sm) + [(sm[-1][0], b-1), (sm[0][0], b-1)]
            draw.polygon(poly, fill=self._dim(accent, 0.2))
            draw.line(sm, fill=accent, width=1 if small else 2)

    def _draw_radar(self, draw, cx, cy, radius, accent, grid, white):
        for r in [radius, radius*0.66, radius*0.33]:
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=grid)
        draw.line((cx-radius, cy, cx+radius, cy), fill=grid)
        draw.line((cx, cy-radius, cx, cy+radius), fill=grid)
        draw.text((cx-5, cy-radius-12), "N", fill=white, font=self._f_compass)
        for angle, strength in self._bearing_log:
            rad = np.radians(angle - 90)
            lx, ly = cx + int(radius * strength * np.cos(rad)), cy + int(radius * strength * np.sin(rad))
            draw.line((cx, cy, lx, ly), fill=accent, width=2)

    def _draw_history(self, draw, l, t, r, b, accent, grid, white):
        draw.text((l, t-15), "MARGIN HISTORY", fill=white, font=self._f_label)
        draw.rectangle((l, t, r, b), outline=grid)
        if not self._history_log: return
        bw = (r - l) // 50
        for i, val in enumerate(self._history_log):
            h = int(np.clip((val+20) * (b-t)/40, 0, b - t))
            bx = l + i * bw
            draw.rectangle((bx, b - h, bx + bw - 1, b), fill=accent if val > 0 else (200,0,0))

    def _init_touch(self):
        if spidev is None or GPIO is None: return
        self._T_CS_MANUAL = 22
        try:
            self._touch_spi = spidev.SpiDev()
            self._touch_spi.open(0, 1)
            self._touch_spi.max_speed_hz, self._touch_spi.mode, self._touch_spi.no_cs = 100000, 0, True
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self._T_CS_MANUAL, GPIO.OUT, initial=GPIO.HIGH)
            self._touch_ok = True
            threading.Thread(target=self._touch_worker, daemon=True).start()
        except: pass

    def _read_xpt2046(self, cmd):
        with self._spi_lock:
            GPIO.output(self._T_CS_MANUAL, 0)
            resp = self._touch_spi.xfer2([cmd, 0, 0])
            GPIO.output(self._T_CS_MANUAL, 1)
            return ((resp[1] << 8) | resp[2]) >> 3

    def _touch_worker(self):
        X_MIN, X_MAX, Y_MIN, Y_MAX = 300, 3850, 130, 3840
        while True:
            try:
                x_raw, y_raw = self._read_xpt2046(0x94), self._read_xpt2046(0xD4)
                if 50 < x_raw < 4050 and 50 < y_raw < 4050:
                    sx = int(np.clip(479 - ((x_raw - X_MIN) * 480 / (X_MAX - X_MIN)), 0, 479))
                    sy = int(np.clip(319 - ((y_raw - Y_MIN) * 320 / (Y_MAX - Y_MIN)), 0, 319))
                    self._handle_click(sx, sy)
                    time.sleep(0.3)
                time.sleep(0.05)
            except: time.sleep(1)

    def _handle_click(self, x, y):
        for label, (x1, y1, x2, y2) in self._touch_zones.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._last_pressed, self._pressed_until = label, time.time() + 0.15
                if label == "VIEW": self.view_mode = (self.view_mode + 1) % 3
                elif label == "GAIN":
                    if x < x1 + (x2-x1)//2: self.app.adjust_gain(-2.0)
                    else: self.app.adjust_gain(2.0)
                elif label == "MUTE": self.app.toggle_mute()
                elif label == "CALIB": self.app.recalibrate()
                elif label == "SNAP": self.app.manual_capture()
                elif label == "EXIT": self.app.running = False
                return