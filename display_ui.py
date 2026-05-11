import time
import threading
import numpy as np
import spidev
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
        self._prev_smooth_y = None
        self._fps_time = time.time()
        self._fps_count = 0
        self._fps_display = 0
        self.view_mode = 0  # 0: Normal, 1: Search, 2: Analytics
        self.show_menu = False
        self._touch_zones = {} 
        
        if not self.preview:
            self._init_touch()

    def _get_text_size(self, text, font):
        draw = self.app._draw
        if hasattr(draw, "textbbox"):
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            return right - left, bottom - top
        if hasattr(font, "getsize"):
            return font.getsize(text)
        return len(text) * 8, 12

    def _init_display(self):
        print("[SYSTEM] Initializing Display...")
        from luma.core.interface.serial import spi
        from luma.lcd.device import ili9488

        serial = spi(
            port=0,
            device=0,
            gpio_DC=24,
            gpio_RST=25,
            bus_speed_hz=32000000,
        )

        self.app.device = ili9488(
            serial,
            width=self.app.w,
            height=self.app.h,
            rotate=0
        )

    def _init_drawing(self):
        self.app._img = Image.new("RGB", (self.app.w, self.app.h), "black")
        self.app._draw = ImageDraw.Draw(self.app._img)
        self._load_fonts()

    def _load_fonts(self):
        bold = ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]
        regular = ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]
        mono = ["DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "C:/Windows/Fonts/consola.ttf"]

        def _try(paths, size):
            for p in paths:
                try: return ImageFont.truetype(p, size)
                except: continue
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

    @staticmethod
    def _dim(c, f):
        return tuple(max(0, min(255, int(v * f))) for v in c)

    @staticmethod
    def _lerp(c1, c2, t):
        t = max(0.0, min(1.0, t))
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

    @staticmethod
    def _smooth(pts, n):
        if len(pts) < 3: return pts
        xs = np.array([p[0] for p in pts], dtype=np.float64)
        ys = np.array([p[1] for p in pts], dtype=np.float64)
        x_new = np.linspace(xs[0], xs[-1], n)
        y_new = np.interp(x_new, xs, ys)
        k = max(7, min(11, n // 30))
        if k % 2 == 0: k += 1
        pad_w = k // 2
        y_padded = np.pad(y_new, pad_width=pad_w, mode='edge')
        y_s = np.convolve(y_padded, np.ones(k) / k, mode='valid')
        return list(zip(x_new.astype(int), np.clip(y_s, ys.min(), ys.max()).astype(int)))

    # ── main draw ───────────────────────────────────────────────────
    def draw_ui(self, metrics, power):
        draw = self.app._draw
        W, H = self.app.w, self.app.h
        
        self._fps_count += 1
        now = time.time()
        if now - self._fps_time >= 1.0:
            self._fps_display = self._fps_count
            self._fps_count = 0
            self._fps_time = now
        fps_val = self._fps_display if self._fps_display > 0 else self.app.target_fps

        state = metrics["state"]
        accent = (255, 80, 90) if state=="JAMMING" else ((255, 220, 50) if state=="WATCH" else (0, 255, 136))
        white_high = (255, 255, 255)
        lbl_white = (255, 255, 255)
        grid = self._dim(accent, 0.2)
        fill_c = self._dim(accent, 0.15)

        # Clear background
        draw.rectangle((0, 0, W - 1, H - 1), fill=(3, 3, 3))

        # Render current mode
        if self.view_mode == 1:
            self._render_search_mode(draw, metrics, accent, white_high, lbl_white)
        elif self.view_mode == 2:
            self._render_analytics_mode(draw, metrics, power, accent, white_high, lbl_white, grid, fill_c)
        else:
            self._render_normal_mode(draw, metrics, power, accent, white_high, lbl_white, grid, fill_c, fps_val)

        # Overlay menu
        self._draw_overlay_menu(draw, accent, white_high)

        # Output
        if self.preview:
            self.app._img.save("preview.png")
            if not self._preview_shown:
                try: self.app._img.show()
                except: pass
                self._preview_shown = True
        else:
            self.app.device.display(self.app._img)

    def _render_normal_mode(self, draw, metrics, power, accent, white_high, lbl_white, grid, fill_c, fps_val):
        W, H = self.app.w, self.app.h
        hdr_b, lp_r, rp_l, spec_b, met_b = 44, 106, 418, 232, 284
        state, nf, score = metrics["state"], metrics.get("noise_floor", -90), metrics.get("score", 0)
        
        # Header
        hdr_bg = (40, 8, 10) if state=="JAMMING" else ((50, 44, 10) if state=="WATCH" else (8, 40, 20))
        draw.rectangle((0, 0, W, hdr_b), fill=hdr_bg)
        draw.line((0, hdr_b, W, hdr_b), fill=accent, width=1)
        draw.text((8, 5), "GNSS L1 JAMMING DETECTOR", fill=white_high, font=self._f_title)
        draw.text((W - 100, 10), state, fill=accent, font=self._f_status)
        bw = self.app.sample_rate_hz / 2e6
        draw.text((8, 23), f"1575.42 MHz | G:{self.app.gain_db}dB", fill=accent, font=self._f_subtitle)

        # Left Panel
        draw.rectangle((0, hdr_b, lp_r, 284), fill=(6, 6, 6))
        draw.line((lp_r, hdr_b, lp_r, 284), fill=accent, width=1)
        draw.text((8, hdr_b + 5), "STATE", fill=lbl_white, font=self._f_label)
        draw.text((8, hdr_b + 15), state[:4], fill=accent, font=self._f_state_big)
        self._draw_polar(draw, accent, 53, hdr_b + 100, 38)

        # Right Panel
        draw.rectangle((rp_l, hdr_b, W, 284), fill=(6, 6, 6))
        draw.line((rp_l, hdr_b, rp_l, 284), fill=accent, width=1)
        draw.text((rp_l + 8, hdr_b + 5), "SCORE", fill=lbl_white, font=self._f_label)
        draw.text((rp_l + 10, hdr_b + 18), f"{score:02d}", fill=accent, font=self._f_score_big)
        draw.text((rp_l + 8, 250), f"FPS: {fps_val}", fill=white_high, font=self._f_small)

        # Spectrum Area
        spec_l, spec_r, spec_t = lp_r, rp_l, hdr_b
        draw.rectangle((spec_l, spec_t, spec_r, spec_b), outline=accent, width=1)
        pts = scale_points(power, nf, spec_r-spec_l, spec_t+15, spec_b-5)
        pts_off = [(x + spec_l, y) for x, y in pts]
        if len(pts_off) > 1: draw.line(pts_off, fill=accent, width=2)

        # Metrics Row
        draw.rectangle((spec_l, spec_b, spec_r, met_b), fill=(10, 10, 15), outline=accent, width=1)
        draw.text((spec_l + 10, spec_b + 10), f"NF: {nf:.1f} dBFS   PEAK: {metrics['peak_p']:.1f} dBFS", fill=white_high, font=self._f_value)

        # Bottom Bar
        bar_y = 284
        draw.rectangle((0, bar_y, W, 320), fill=(5, 5, 5))
        draw.line((0, bar_y, W, bar_y), fill=accent, width=1)
        draw.text((8, bar_y + 5), "SIG STR", fill=lbl_white, font=self._f_small)
        bar_w = int((W - 120) * score / 99)
        draw.rectangle((70, bar_y + 8, 70 + bar_w, bar_y + 16), fill=accent)
        draw.text((W - 40, bar_y + 5), f"{int(score*100/99)}%", fill=white_high, font=self._f_small)

    def _render_search_mode(self, draw, metrics, accent, white_high, lbl_white):
        W, H = self.app.w, self.app.h
        cx, cy = W // 2, H // 2 - 20
        self._draw_polar(draw, accent, cx, cy, 110)
        draw.text((W//2 - 60, 15), "SEARCH MODE (COMPASS)", fill=white_high, font=self._f_title)
        draw.text((20, 50), "SCORE", fill=lbl_white, font=self._f_status)
        draw.text((20, 80), f"{metrics['score']:02d}", fill=accent, font=self._f_score_big)
        draw.text((W - 120, 50), "STATE", fill=lbl_white, font=self._f_status)
        draw.text((W - 120, 80), metrics["state"][:4], fill=accent, font=self._f_state_big)

    def _render_analytics_mode(self, draw, metrics, power, accent, white_high, lbl_white, grid, fill_c):
        W, H = self.app.w, self.app.h
        spec_l, spec_r, spec_t, spec_b = 10, W - 10, 50, H - 60
        draw.rectangle((spec_l, spec_t, spec_r, spec_b), fill=(5, 5, 10), outline=accent, width=1)
        nf = metrics.get("noise_floor", -90)
        pts = scale_points(power, nf, spec_r-spec_l, spec_t+10, spec_b-10)
        pts_off = [(x + spec_l, y) for x, y in pts]
        if len(pts_off) > 1:
            draw.polygon(pts_off + [(pts_off[-1][0], spec_b), (pts_off[0][0], spec_b)], fill=fill_c)
            draw.line(pts_off, fill=accent, width=2)
        draw.text((W//2 - 80, 15), "DETAILED SPECTRUM ANALYTICS", fill=white_high, font=self._f_title)

    def record_bearing(self, angle_deg, peak_dbfs):
        norm = float(np.clip((peak_dbfs + 90) / 30.0, 0.0, 1.0))
        self._bearing_log.append((int(angle_deg) % 360, norm))
        if len(self._bearing_log) > 12: self._bearing_log.pop(0)

    def get_best_bearing(self):
        if not self._bearing_log: return None
        return max(self._bearing_log, key=lambda x: x[1])[0]

    def _draw_polar(self, draw, accent, cx, cy, r):
        dim_accent = self._dim(accent, 0.2)
        for radius in [r // 3, r * 2 // 3, r]:
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=dim_accent, width=1)
        for angle in range(0, 360, 45):
            rad = np.radians(angle - 90)
            draw.line((cx, cy, int(cx + np.cos(rad) * r), int(cy + np.sin(rad) * r)), fill=dim_accent, width=1)
        for angle_deg, norm in self._bearing_log:
            rad = np.radians(angle_deg - 90)
            px, py = int(cx + np.cos(rad) * r * norm), int(cy + np.sin(rad) * r * norm)
            draw.line((cx, cy, px, py), fill=accent, width=1)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=accent)
        draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=(255, 255, 255))

    def toggle_view_mode(self):
        self.view_mode = (self.view_mode + 1) % 3
        print(f"[UI] View Mode changed to: {self.view_mode}")

    def _draw_overlay_menu(self, draw, accent, white):
        W, H = self.app.w, self.app.h
        btn_w, btn_h, gap = 64, 28, 6
        buttons = ["VIEW", "SNAP", "CALIB", "MUTE", "GAIN+", "EXIT"]
        start_x = (W - (len(buttons) * (btn_w + gap))) // 2
        y = H - btn_h - 4
        for i, label in enumerate(buttons):
            bx = start_x + i * (btn_w + gap)
            draw.rectangle((bx, y, bx + btn_w, y + btn_h), fill=(25, 25, 35), outline=accent, width=1)
            lw, lh = self._get_text_size(label, self._f_footer)
            draw.text((bx + (btn_w - lw)//2, y + (btn_h - lh)//2), label, fill=white, font=self._f_footer)
            self._touch_zones[label] = (bx, y, bx + btn_w, y + btn_h)

    def _init_touch(self):
        print("[SYSTEM] Initializing Touch Controller (XPT2046)...")
        try:
            self._touch_spi = spidev.SpiDev()
            self._touch_spi.open(0, 1) # SPI Bus 0, Device 1 (GPIO 7 / CS1)
            self._touch_spi.max_speed_hz = 1000000
            threading.Thread(target=self._touch_worker, daemon=True).start()
        except Exception as e: print(f"[ERROR] Touch init: {e}")

    def _touch_worker(self):
        X_MIN, X_MAX, Y_MIN, Y_MAX = 200, 3800, 300, 3900
        while True:
            try:
                rx = self._touch_spi.xfer2([0x90, 0, 0])
                ry = self._touch_spi.xfer2([0xD0, 0, 0])
                x_raw, y_raw = ((rx[1]<<8)|rx[2])>>3, ((ry[1]<<8)|ry[2])>>3
                if x_raw > 150 and y_raw > 150:
                    sx = int(np.clip((x_raw - X_MIN) * self.app.w / (X_MAX - X_MIN), 0, self.app.w-1))
                    sy = int(np.clip((y_raw - Y_MIN) * self.app.h / (Y_MAX - Y_MIN), 0, self.app.h-1))
                    self._handle_click(sx, sy)
                    time.sleep(0.4)
                time.sleep(0.05)
            except: time.sleep(1)

    def _handle_click(self, x, y):
        for label, (x1, y1, x2, y2) in self._touch_zones.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                print(f"[TOUCH] {label}")
                if label == "VIEW": self.toggle_view_mode()
                elif label == "MUTE": self.app.toggle_mute()
                elif label == "CALIB": self.app.recalibrate()
                elif label == "SNAP": self.app.manual_capture()
                elif label == "GAIN+": self.app.adjust_gain(2.0)
                elif label == "EXIT": self.app.running = False
                return