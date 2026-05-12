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
        self._toast_msg = None
        self._toast_until = 0
        self._pwr_confirm = False
        self._pwr_confirm_until = 0

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

        self._f_title     = _try(bold, 14)
        self._f_subtitle  = _try(bold, 11)
        self._f_status    = _try(bold, 22)
        self._f_state_big = _try(bold, 26)
        self._f_score_big = _try(mono, 32)
        self._f_score_sub = _try(regular, 11)
        self._f_label     = _try(bold, 11)
        self._f_value     = _try(bold, 22)
        self._f_unit      = _try(regular, 10)
        self._f_brg       = _try(bold, 18)
        self._f_compass   = _try(regular, 10)
        self._f_small     = _try(bold, 10)
        self._f_footer    = _try(bold, 9)
        self._f_fps       = _try(bold, 14)
        self._f_fps_label = _try(regular, 10)
        self._f_dblabel   = _try(regular, 9)
        self._f_btn       = _try(bold, 13)
        self._f_met_val   = _try(mono, 14)
        self._f_toast     = _try(bold, 18)
        self._f_subtitle_small = _try(bold, 10)

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

    def show_toast(self, message, duration=1.5):
        """Show a temporary pop-up message on the screen."""
        self._toast_msg = message
        self._toast_until = time.time() + duration

    # ════════════════════════════════════════════════════════════════
    #                   SPLASH SCREEN
    # ════════════════════════════════════════════════════════════════
    def draw_splash(self, message="BOOTING..."):
        draw = self.app._draw
        W, H = self.app.w, self.app.h
        
        # Background
        draw.rectangle((0, 0, W, H), fill=(8, 12, 16))
        
        # Title
        tw, th = self._get_text_size("GNSS JAMMING DETECTOR", self._f_state_big)
        draw.text(((W - tw) // 2, H // 2 - 40), "GNSS JAMMING DETECTOR", fill=(0, 255, 136), font=self._f_state_big)
        
        # Subtitle
        sw, sh = self._get_text_size("KMITL SPACE & GEO ENGINEERING", self._f_status)
        draw.text(((W - sw) // 2, H // 2), "KMITL SPACE & GEO ENGINEERING", fill=(255, 255, 255), font=self._f_status)
        
        # Message
        msg_color = (255, 50, 50) if "SHUT" in message.upper() else (255, 220, 50)
        mw, mh = self._get_text_size(message, self._f_state_big)
        draw.text(((W - mw) // 2, H // 2 + 50), message, fill=msg_color, font=self._f_state_big)
        
        if self.preview:
            self.app._img.save("preview.png")
        else:
            with self._spi_lock:
                self.app.device.display(self.app._img)

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

        # ── theme colours (BRIGHT for outdoor use) ───────────────────
        if state == "JAMMING":
            accent    = (255, 60, 70)
            accent_br = (255, 120, 130)  # Brighter variant for text
            hdr_bg    = (60, 5, 8)
            grid      = (80, 25, 30)
        elif state == "WATCH":
            accent    = (255, 230, 50)
            accent_br = (255, 245, 140)
            hdr_bg    = (60, 50, 5)
            grid      = (100, 85, 15)
        else:
            accent    = (0, 255, 140)
            accent_br = (120, 255, 200)
            hdr_bg    = (5, 45, 25)
            grid      = (0, 100, 60)

        white  = (255, 255, 255)
        bright = (240, 240, 255)  # Slightly cool white for labels
        dim    = (160, 160, 180)  # Muted for secondary info

        # ── layout ──────────────────────────────────────────────────
        hdr_b   = 36
        rp_l    = 420
        foot_t  = 268   # Bottom bar starts here (H=320, so 52px for buttons)

        # Background
        draw.rectangle((0, 0, W - 1, H - 1), fill=(5, 5, 8))

        # ═══ HEADER ═══
        uptime = int(time.time() - self.app.start_time)
        hrs, mins, secs = uptime // 3600, (uptime % 3600) // 60, uptime % 60
        up_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

        draw.rectangle((0, 0, W, hdr_b), fill=hdr_bg)
        draw.line((0, hdr_b, W, hdr_b), fill=accent, width=2)

        # Title row
        draw.text((8, 3), "GNSS JAMMING DETECTOR", fill=white, font=self._f_title)
        # Subtitle row
        sub = f"L1 1575.42MHz | Gain: {self.app.gain_db:.1f} | UP Time: {up_str}"
        draw.text((8, 20), sub, fill=accent_br, font=self._f_subtitle_small)

        # State badge (right side of header) - Extra large for field visibility
        sw, sh = self._get_text_size(state, self._f_status)
        badge_x = W - sw - 12
        badge_y = (hdr_b - sh) // 2
        # Draw badge box with a slight rounding look (just a rectangle for now but larger)
        draw.rectangle((badge_x - 8, 2, W - 2, hdr_b - 2), fill=accent, outline=white, width=1)
        draw.text((badge_x - 2, badge_y), state, fill=(0, 0, 0), font=self._f_status)

        # ═══ RIGHT PANEL ═══
        rp_w = W - rp_l
        draw.rectangle((rp_l, hdr_b, W, foot_t), fill=(10, 10, 15))
        draw.line((rp_l, hdr_b, rp_l, foot_t), fill=accent, width=2)

        # SIG STR label (one line, small)
        draw.text((rp_l + 6, hdr_b + 5), "SIG STR", fill=bright, font=self._f_small)

        # Score value as percentage
        pct = int(np.clip(score * 100 / 99, 0, 100))
        pct_str = f"{pct}"
        draw.text((rp_l + 6, hdr_b + 20), pct_str, fill=accent, font=self._f_score_big)
        draw.text((rp_l + 6, hdr_b + 54), "/100%", fill=dim, font=self._f_score_sub)

        # Vertical bar
        bar_x, bar_w = rp_l + 6, rp_w - 12
        bar_top, bar_bot = hdr_b + 72, foot_t - 28
        bar_h = bar_bot - bar_top
        draw.rectangle((bar_x, bar_top, bar_x + bar_w, bar_bot), fill=(20, 20, 25), outline=self._dim(accent, 0.5))
        fill_h = int(bar_h * score / 99)
        if fill_h > 0:
            draw.rectangle((bar_x + 1, bar_bot - fill_h, bar_x + bar_w - 1, bar_bot), fill=accent)
            if fill_h > 3:
                draw.rectangle((bar_x + 2, bar_bot - fill_h, bar_x + bar_w - 2, bar_bot - fill_h + 3), fill=accent_br)

        # FPS in right panel footer
        draw.text((rp_l + 6, foot_t - 22), f"FPS {fps_val}", fill=dim, font=self._f_small)

        # ═══ MAIN CONTENT AREA ═══
        content_l = 0
        content_w = rp_l

        if self.view_mode == 1:  # SEARCH MODE (Radar)
            self._draw_radar(draw, content_l + content_w // 2, (hdr_b + foot_t) // 2, 100, accent, grid, white)

        elif self.view_mode == 2:  # ANALYTICS MODE (History)
            self._draw_history(draw, content_l + 12, hdr_b + 18, rp_l - 12, foot_t - 75, accent, grid, white)
            self._draw_spectrum(draw, content_l + 8, foot_t - 68, rp_l - 8, foot_t - 4, metrics, power, accent, grid, nf, peak, small=True)

        else:  # NORMAL MODE
            # Spectrum: large — this is the main display
            spec_bot = foot_t - 72
            self._draw_spectrum(draw, content_l + 8, hdr_b + 4, rp_l - 4, spec_bot, metrics, power, accent, grid, nf, peak)

            # Metrics grid below spectrum (4 columns as requested)
            met_y = spec_bot + 6
            col_w = content_w // 4
            met_data = [
                ("NOISE FLOOR", f"{nf:.1f}", white),
                ("PEAK POWER",  f"{peak:.1f}", accent_br),
                ("FLOOR RISE",  f"{rise:+.1f}", accent_br),
                ("MARGIN",      f"{margin_val:+.1f}", accent_br),
            ]
            for i, (ml, mv, mcolor) in enumerate(met_data):
                mx = content_l + i * col_w
                # Vertical divider
                if i > 0:
                    draw.line((mx, met_y + 4, mx, foot_t - 6), fill=(60, 60, 70), width=1)
                
                # Center text in column
                tw, _ = self._get_text_size(ml, self._f_small)
                draw.text((mx + (col_w - tw)//2, met_y), ml, fill=dim, font=self._f_small)
                
                vw, vh = self._get_text_size(mv, self._f_value)
                draw.text((mx + (col_w - vw)//2, met_y + 16), mv, fill=mcolor, font=self._f_value)
                
                uw, _ = self._get_text_size("dB", self._f_small)
                draw.text((mx + (col_w - uw)//2, met_y + 40), "dB", fill=mcolor, font=self._f_small)

        # ═══ BOTTOM BUTTON BAR ═══
        draw.rectangle((0, foot_t, W, H), fill=(12, 12, 18))
        draw.line((0, foot_t, W, foot_t), fill=accent, width=2)

        btns = ["MODE", "CALIB", "GAIN-", "GAIN+", "PWR"]
        btn_count = len(btns)
        btn_w = W // btn_count
        btn_h = H - foot_t
        self._touch_zones = {}

        for i, label in enumerate(btns):
            bx = i * btn_w
            is_pressed = (label == self._last_pressed and now < self._pressed_until)

            if label == "PWR":
                bg_c = (180, 40, 40) if is_pressed else (60, 10, 10)
                outline_c = (200, 60, 60)
                ic = white
            else:
                bg_c = accent if is_pressed else (30, 30, 45)
                outline_c = self._dim(accent, 0.7)
                ic = (0, 0, 0) if is_pressed else white

            draw.rectangle((bx + 2, foot_t + 3, bx + btn_w - 2, H - 3), fill=bg_c, outline=outline_c)
            self._touch_zones[label] = (bx, foot_t, bx + btn_w, H)

            # Draw button content (icons for PWR/GAIN, text for others)
            cx = bx + btn_w // 2
            cy = foot_t + btn_h // 2
            r = 12

            if label == "PWR":
                # Power icon: thicker and bolder
                pr = 11
                draw.arc((cx - pr, cy - pr , cx + pr, cy + pr), 135, 405, fill=ic, width=3)
                draw.line((cx, cy - pr - 3, cx, cy - 2), fill=ic, width=3)
            elif label == "GAIN-":
                # Down triangle
                draw.polygon([(cx - 8, cy - 4), (cx + 8, cy - 4), (cx, cy + 8)], fill=ic)
                draw.line((cx - 10, cy - 10, cx + 10, cy - 10), fill=ic, width=2)
            elif label == "GAIN+":
                # Up triangle
                draw.polygon([(cx - 8, cy + 4), (cx + 8, cy + 4), (cx, cy - 8)], fill=ic)
                draw.line((cx - 10, cy + 10, cx + 10, cy + 10), fill=ic, width=2)
            else:
                # Text label for MODE, CALIB
                tw, th = self._get_text_size(label, self._f_btn)
                ty = foot_t + (btn_h - th) // 2
                draw.text((bx + (btn_w - tw) // 2, ty), label, fill=ic, font=self._f_btn)

        # ═══ TOAST OVERLAY ═══
        if now < self._toast_until and self._toast_msg and not self._pwr_confirm:
            msg = self._toast_msg
            tw, th = self._get_text_size(msg, self._f_toast)
            pad_x, pad_y = 28, 16
            box_w, box_h = tw + pad_x * 2, th + pad_y * 2
            cx, cy = W // 2, (hdr_b + foot_t) // 2

            draw.rectangle((cx - box_w//2 - 2, cy - box_h//2 - 2, cx + box_w//2 + 2, cy + box_h//2 + 2), fill=self._dim(accent, 0.15))
            draw.rectangle((cx - box_w//2, cy - box_h//2, cx + box_w//2, cy + box_h//2), fill=(10, 10, 18), outline=accent, width=2)
            draw.text((cx - tw//2, cy - th//2), msg, fill=white, font=self._f_toast)

        # ═══ PWR CONFIRM DIALOG ═══
        if self._pwr_confirm and now < self._pwr_confirm_until:
            cx, cy = W // 2, (hdr_b + foot_t) // 2
            dlg_w, dlg_h = 280, 120

            # Dialog background
            draw.rectangle((cx - dlg_w//2 - 3, cy - dlg_h//2 - 3, cx + dlg_w//2 + 3, cy + dlg_h//2 + 3), fill=(80, 10, 10))
            draw.rectangle((cx - dlg_w//2, cy - dlg_h//2, cx + dlg_w//2, cy + dlg_h//2), fill=(15, 8, 12), outline=(255, 80, 80), width=2)

            # Title text
            q_text = "POWER OFF?"
            qw, qh = self._get_text_size(q_text, self._f_value)
            draw.text((cx - qw//2, cy - dlg_h//2 + 14), q_text, fill=(255, 100, 100), font=self._f_value)

            # YES / NO buttons
            btn_y_top = cy + 8
            btn_y_bot = cy + dlg_h//2 - 10
            btn_gap = 20

            # YES button (left)
            yes_x1 = cx - dlg_w//2 + 20
            yes_x2 = cx - btn_gap//2
            draw.rectangle((yes_x1, btn_y_top, yes_x2, btn_y_bot), fill=(200, 40, 40), outline=(255, 120, 120))
            yw, yh = self._get_text_size("YES", self._f_btn)
            draw.text(((yes_x1 + yes_x2 - yw)//2, (btn_y_top + btn_y_bot - yh)//2), "YES", fill=white, font=self._f_btn)
            self._touch_zones["PWR_YES"] = (yes_x1, btn_y_top, yes_x2, btn_y_bot)

            # NO button (right)
            no_x1 = cx + btn_gap//2
            no_x2 = cx + dlg_w//2 - 20
            draw.rectangle((no_x1, btn_y_top, no_x2, btn_y_bot), fill=(30, 80, 50), outline=(80, 200, 120))
            nw, nh = self._get_text_size("NO", self._f_btn)
            draw.text(((no_x1 + no_x2 - nw)//2, (btn_y_top + btn_y_bot - nh)//2), "NO", fill=white, font=self._f_btn)
            self._touch_zones["PWR_NO"] = (no_x1, btn_y_top, no_x2, btn_y_bot)
        else:
            self._touch_zones.pop("PWR_YES", None)
            self._touch_zones.pop("PWR_NO", None)

        # Output
        if self.preview:
            self.app._img.save("preview.png")
        else:
            with self._spi_lock:
                self.app.device.display(self.app._img)

    def _draw_spectrum(self, draw, l, t, r, b, metrics, power, accent, grid, nf, peak, small=False):
        draw.rectangle((l, t, r, b), outline=accent, fill=(10, 10, 12))
        sw, sh = r - l, b - t

        # Dotted Grid
        grid_c = (50, 50, 60)
        # Vertical lines (frequency)
        for i in range(1, 4):
            gx = l + (sw * i) // 4
            for gy in range(t, b, 6):
                draw.line((gx, gy, gx, gy + 2), fill=grid_c)
        # Horizontal lines (dB)
        for i in range(1, 4):
            gy = t + (sh * i) // 4
            for gx in range(l, r, 6):
                draw.line((gx, gy, gx + 2, gy), fill=grid_c)
            # Small dB labels
            db_val = -20 - i*20
            draw.text((l + 4, gy - 8), str(db_val), fill=(80, 80, 90), font=self._f_footer)

        # Noise Floor line (dashed)
        # Map nf (-120 to -40 usually) to y
        # scale_points maps 0-100% where 0 is nf and 100 is peak? 
        # Actually scale_points uses a different logic. 
        # Let's draw a fixed line for NF since it's the baseline in the graph usually.
        # But wait, the graph points are RELATIVE to NF.
        # So NF is at the bottom of the graph by definition of scale_points.
        # Let's draw the "NOISE FLOOR" label at the baseline.
        nf_y = b - 15
        draw.text((l + 10, nf_y), "NOISE FLOOR", fill=(100, 100, 110), font=self._f_footer)
        for gx in range(l, r, 8):
            draw.line((gx, nf_y + 10, gx + 4, nf_y + 10), fill=(100, 100, 110))

        pts = scale_points(power, nf, sw, t+5, b-15) # Adjusted bot to leave room for NF line
        pts_off = [(px + l, py) for px, py in pts]
        if len(pts_off) > 2:
            sm = self._smooth(pts_off, sw)
            poly = list(sm) + [(sm[-1][0], b-1), (sm[0][0], b-1)]
            draw.polygon(poly, fill=self._dim(accent, 0.15))
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
        now = time.time()

        # If PWR dialog is showing, only respond to YES/NO
        if self._pwr_confirm and now < self._pwr_confirm_until:
            for label in ["PWR_YES", "PWR_NO"]:
                zone = self._touch_zones.get(label)
                if zone:
                    x1, y1, x2, y2 = zone
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        if label == "PWR_YES":
                            self._pwr_confirm = False
                            self.app.safe_power_off()
                        else:
                            self._pwr_confirm = False
                            self.show_toast("CANCELLED", 1.0)
                        return
            # Tapped outside dialog = cancel
            self._pwr_confirm = False
            return

        for label, (x1, y1, x2, y2) in self._touch_zones.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._last_pressed, self._pressed_until = label, now + 0.2
                if label == "MODE":
                    self.view_mode = (self.view_mode + 1) % 3
                    modes = ["NORMAL", "SEARCH", "ANALYTICS"]
                    self.show_toast(f"MODE: {modes[self.view_mode]}")
                elif label == "GAIN-":
                    self.app.adjust_gain(-2.0)
                    self.show_toast(f"GAIN: {self.app.gain_db:.1f} dB")
                elif label == "GAIN+":
                    self.app.adjust_gain(2.0)
                    self.show_toast(f"GAIN: {self.app.gain_db:.1f} dB")
                elif label == "CALIB":
                    self.app.request_calibration = True
                    self.show_toast("CALIBRATING...", 3.0)
                elif label == "PWR":
                    self._pwr_confirm = True
                    self._pwr_confirm_until = now + 5.0  # 5 seconds to decide
                return