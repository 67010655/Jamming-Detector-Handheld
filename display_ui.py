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
import config

# XPT2046 touch-controller SPI command bytes (single-ended, 12-bit)
_XPT2046_CMD_X = 0xD4   # channel 5 — X position (datasheet convention)
_XPT2046_CMD_Y = 0x94   # channel 1 — Y position (datasheet convention)


class DisplayUI:
    def __init__(self, app, preview=False):
        self.app = app
        self.preview = preview
        self._preview_shown = False
        if not self.preview:
            self._init_display()
        self._init_drawing()
        self._bearing_log = []
        self._persistent_jam = None   # (angle, strength, 'JAMMING') — last strongest jam until next event
        self._active_jam_peak = None  # Strongest bearing tracked during current JAMMING session
        self._history_log = [] # For Mode 2
        self._prev_smooth_y = None
        self._fps_time = time.time()
        self._fps_count = 0
        self._fps_display = 0
        self.view_mode = 0   # 0: Normal, 1: Search, 2: Analytics
        self._touch_zones = {}
        self._zones_lock = threading.RLock()
        self._touch_running = True
        self._touch_ok = False
        self._spi_lock = threading.Lock()
        self._last_pressed = None
        self._pressed_until = 0
        self._toast_msg = None
        self._toast_until = 0
        self._pwr_confirm = False
        self._pwr_confirm_until = 0
        self._calib_confirm = False
        self._calib_confirm_until = 0

        if not self.preview:
            self._init_touch()

    # ── text size helper ────────────────────────────────────────────
    def _get_text_size(self, text, font):
        draw = self._draw
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
                     bus_speed_hz=config.SPI_CLOCK_HZ)
        self.app.device = ili9488(serial, width=self.app.w,
                                  height=self.app.h, rotate=0)

    def _init_drawing(self):
        self._img = Image.new("RGB", (self.app.w, self.app.h), "black")
        self._draw = ImageDraw.Draw(self._img)
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
        self._f_splash_title = _try(bold, 38)
        self._f_score_big = _try(mono, 30)
        self._f_score_sub = _try(regular, 11)
        self._f_label     = _try(bold, 11)
        self._f_value     = _try(bold, 22)
        self._f_unit      = _try(regular, 10)
        self._f_brg       = _try(bold, 18)
        self._f_compass   = _try(regular, 10)
        self._f_small     = _try(bold, 10)
        self._f_footer    = _try(bold, 9)
        self._f_footer_bold = _try(bold, 9)
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
    def record_bearing(self, angle_deg, peak_dbfs, state="SCANNING"):
        norm = float(np.clip((peak_dbfs + 90) / 30.0, 0.0, 1.0))
        entry = (int(angle_deg) % 360, norm, state, float(peak_dbfs))
        self._bearing_log.append(entry)
        if len(self._bearing_log) > 24:  # Increased history window for detailed scanning
            self._bearing_log.pop(0)
        if state == "JAMMING":
            # Compare raw unclipped decibel peak power (peak_dbfs) to find the absolute strongest direction
            if self._active_jam_peak is None or float(peak_dbfs) > self._active_jam_peak[3]:
                self._active_jam_peak = entry

    def get_best_bearing(self):
        if not self._bearing_log:
            return None
        # Compare raw unclipped decibels if available
        if len(self._bearing_log[0]) == 4:
            return max(self._bearing_log, key=lambda x: x[3])[0]
        return max(self._bearing_log, key=lambda x: x[1])[0]

    def keep_strongest_jamming_bearing(self):
        """When jamming ends, pin the strongest sig-strength bearing until the next JAMMING event."""
        jams = [item for item in self._bearing_log if len(item) == 4 and item[2] == "JAMMING"]
        strongest_jam = self._active_jam_peak
        if jams:
            # Sift through log using actual raw peak dBFS for absolute precision
            best_log = max(jams, key=lambda x: x[3])
            if strongest_jam is None or best_log[3] > strongest_jam[3]:
                strongest_jam = best_log
        if strongest_jam is not None:
            self._persistent_jam = strongest_jam
        self._active_jam_peak = None
        self._bearing_log = [
            item for item in self._bearing_log
            if not (len(item) >= 3 and item[2] == "JAMMING")
        ]

    def clear_persistent_jam(self):
        """Clear pinned jam line when a new JAMMING event starts."""
        self._persistent_jam = None
        self._active_jam_peak = None

    @staticmethod
    def get_cardinal_direction(bearing):
        bearing = bearing % 360
        if bearing >= 337.5 or bearing < 22.5:
            return "N"
        elif 22.5 <= bearing < 67.5:
            return "NE"
        elif 67.5 <= bearing < 112.5:
            return "E"
        elif 112.5 <= bearing < 157.5:
            return "SE"
        elif 157.5 <= bearing < 202.5:
            return "S"
        elif 202.5 <= bearing < 247.5:
            return "SW"
        elif 247.5 <= bearing < 292.5:
            return "W"
        else:
            return "NW"

    def show_toast(self, message, duration=1.5):
        """Show a temporary pop-up message on the screen."""
        self._toast_msg = message
        self._toast_until = time.time() + duration

    # ════════════════════════════════════════════════════════════════
    #                   SPLASH SCREEN
    # ════════════════════════════════════════════════════════════════
    def draw_splash(self, message="BOOTING...", progress=None):
        import os
        draw = self._draw
        W, H = self.app.w, self.app.h
        
        # Background
        draw.rectangle((0, 0, W, H), fill=(8, 12, 16))

        # --- Sponsor logos (top, centered) ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        logo_dir = os.path.join(current_dir, 'web')
        target_height = 42
        filenames = [
            "National_Broadcasting_and_Telecommunications_Commission_(Thailand)_Seal.png",
            "BTFP_Logo.webp",
            "KMITL_Sublogo.svg.png"
        ]

        loaded_logos = []
        for fn in filenames:
            logo_path = os.path.join(logo_dir, fn)
            if os.path.exists(logo_path):
                try:
                    logo_img = Image.open(logo_path)
                    w_orig, h_orig = logo_img.size
                    aspect = w_orig / h_orig
                    target_width = int(target_height * aspect)
                    if hasattr(Image, "Resampling"):
                        resampler = Image.Resampling.LANCZOS
                    else:
                        resampler = Image.ANTIALIAS
                    logo_resized = logo_img.resize((target_width, target_height), resampler)
                    loaded_logos.append(logo_resized)
                except Exception as e:
                    print(f"[UI] Error loading logo {fn}: {e}")

        logo_y = 32
        if loaded_logos:
            spacing = 24
            total_width = sum(l.size[0] for l in loaded_logos) + spacing * (len(loaded_logos) - 1)
            start_x = (W - total_width) // 2
            cur_x = start_x
            for logo in loaded_logos:
                if logo.mode in ('RGBA', 'LA') or (logo.mode == 'P' and 'transparency' in logo.info):
                    mask = logo.convert('RGBA')
                    self._img.paste(logo, (cur_x, logo_y), mask)
                else:
                    self._img.paste(logo, (cur_x, logo_y))
                cur_x += logo.size[0] + spacing

        # --- Title block below logos (proportional vertical rhythm) ---
        gap_logo_title = 22   # logos → GUNJAM
        gap_title_sub = 14    # GUNJAM → department line
        gap_sub_lines = 7     # department → KMITL (tighter pair)
        accent = (0, 255, 136)
        sub_color = (200, 220, 255)
        title_y = logo_y + target_height + gap_logo_title if loaded_logos else 44

        tw, th = self._get_text_size("GUNJAM", self._f_splash_title)
        draw.text(((W - tw) // 2, title_y), "GUNJAM", fill=accent, font=self._f_splash_title)

        y = title_y + th + gap_title_sub
        telecom_text = "TELECOMMUNICATION ENGINEERING DEPARTMENT"
        sw, sh = self._get_text_size(telecom_text, self._f_title)
        draw.text(((W - sw) // 2, y), telecom_text, fill=sub_color, font=self._f_title)

        y += sh + gap_sub_lines
        kw, kh = self._get_text_size("KMITL", self._f_title)
        draw.text(((W - kw) // 2, y), "KMITL", fill=sub_color, font=self._f_title)

        # Draw Progress Bar if progress is provided
        if progress is not None:
            # Progress bar dimensions
            bar_w, bar_h = 320, 14
            bar_x = (W - bar_w) // 2
            bar_y = 200
            
            # Draw progress bar background (track)
            draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), fill=(16, 24, 32), outline=(0, 100, 60), width=1)
            
            # Calculate filled width
            fill_w = int(bar_w * (np.clip(progress, 0, 100) / 100.0))
            if fill_w > 0:
                # Vibrant progress bar fill
                draw.rectangle((bar_x + 1, bar_y + 1, bar_x + fill_w - 1, bar_y + bar_h - 1), fill=(0, 255, 136))
                # Add light highlight line on top for standard premium glassmorphism
                draw.line((bar_x + 1, bar_y + 1, bar_x + fill_w - 1, bar_y + 1), fill=(255, 255, 255))

            # Put message underneath progress bar
            msg_color = (255, 50, 50) if "SHUT" in message.upper() else (255, 220, 50)
            mw, mh = self._get_text_size(message, self._f_subtitle)
            draw.text(((W - mw) // 2, bar_y + 24), message, fill=msg_color, font=self._f_subtitle)
        else:
            # Fallback/Default layout when no progress bar is requested
            msg_color = (255, 50, 50) if "SHUT" in message.upper() else (255, 220, 50)
            mw, mh = self._get_text_size(message, self._f_state_big)
            draw.text(((W - mw) // 2, 210), message, fill=msg_color, font=self._f_state_big)
        
        if self.preview:
            self._img.save("preview.png")
        else:
            with self._spi_lock:
                self.app.device.display(self._img)

    # ════════════════════════════════════════════════════════════════
    #                   MAIN DRAW ENTRY POINT
    # ════════════════════════════════════════════════════════════════
    def draw_ui(self, metrics, power):
        draw = self._draw
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
        if getattr(self.app, 'fixed_nf', False):
            sub += " | [GUARD FIXED]"
        elif getattr(self.app, 'baseline_guard_active', False):
            sub += " | [GUARD LOCKED]"
        draw.text((8, 20), sub, fill=accent_br, font=self._f_subtitle_small)

        # State badge (right side of header) - Extra large for field visibility
        sw, sh = self._get_text_size(state, self._f_status)
        badge_w = sw + 20
        bx1, by1, bx2, by2 = W - badge_w - 2, 2, W - 2, hdr_b - 2
        draw.rectangle((bx1, by1, bx2, by2), fill=accent, outline=white, width=1)
        # Center text exactly in the badge box
        tx = bx1 + (badge_w - sw) // 2
        ty = by1 + (by2 - by1 - sh) // 2
        draw.text((tx, ty), state, fill=(0, 0, 0), font=self._f_status)

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
            self._draw_radar(
                draw, content_l + content_w // 2, (hdr_b + foot_t) // 2,
                100, accent, grid, white, state, metrics,
            )
            # Label
            draw.text((content_l + 10, hdr_b + 5), "GYRO COMPASS", fill=self._dim(white, 0.4), font=self._f_footer)

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
                ("PEAK POWER",  f"{peak:.1f}", white),
                ("FLOOR RISE",  f"{rise:+.1f}", white),
                ("MARGIN",      f"{margin_val:+.1f}", white),
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
                
                unit = "dBm" if i < 2 else "dB"
                uw, _ = self._get_text_size(unit, self._f_small)
                draw.text((mx + (col_w - uw)//2, met_y + 40), unit, fill=mcolor, font=self._f_small)

        # ═══ BOTTOM BUTTON BAR ═══
        draw.rectangle((0, foot_t, W, H), fill=(12, 12, 18))
        draw.line((0, foot_t, W, foot_t), fill=accent, width=2)

        btns = ["MODE", "CALIB", "GAIN-", "GAIN+", "PWR"]
        btn_count = len(btns)
        btn_w = W // btn_count
        btn_h = H - foot_t
        _new_zones = {}

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
            _new_zones[label] = (bx, foot_t, bx + btn_w, H)

            # Draw button content: icons stay fast to scan, labels reduce field mistakes.
            cx = bx + btn_w // 2
            cy = foot_t + btn_h // 2
            r = 12

            if label == "PWR":
                # Standard Power Icon (Gap at Top)
                pr = 10
                gap = 60
                icon_y = cy - 5
                draw.arc((cx - pr, icon_y - pr, cx + pr, icon_y + pr), 270 + gap//2, 270 - gap//2 + 360, fill=ic, width=3)
                draw.line((cx, icon_y - pr - 2, cx, icon_y + 1), fill=ic, width=3)
                tw, th = self._get_text_size("PWR", self._f_footer_bold)
                draw.text((cx - tw // 2, H - th - 8), "PWR", fill=ic, font=self._f_footer_bold)
            elif label == "GAIN-":
                # Down triangle
                icon_y = cy - 5
                draw.polygon([(cx - 8, icon_y - 4), (cx + 8, icon_y - 4), (cx, icon_y + 8)], fill=ic)
                draw.line((cx - 10, icon_y - 10, cx + 10, icon_y - 10), fill=ic, width=2)
                tw, th = self._get_text_size("GAIN-", self._f_footer_bold)
                draw.text((cx - tw // 2, H - th - 8), "GAIN-", fill=ic, font=self._f_footer_bold)
            elif label == "GAIN+":
                # Up triangle
                icon_y = cy - 5
                draw.polygon([(cx - 8, icon_y + 4), (cx + 8, icon_y + 4), (cx, icon_y - 8)], fill=ic)
                draw.line((cx - 10, icon_y + 10, cx + 10, icon_y + 10), fill=ic, width=2)
                tw, th = self._get_text_size("GAIN+", self._f_footer_bold)
                draw.text((cx - tw // 2, H - th - 8), "GAIN+", fill=ic, font=self._f_footer_bold)
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
            dlg_w, dlg_h = 360, 120

            # Dialog background
            draw.rectangle((cx - dlg_w//2 - 3, cy - dlg_h//2 - 3, cx + dlg_w//2 + 3, cy + dlg_h//2 + 3), fill=(80, 40, 10))
            draw.rectangle((cx - dlg_w//2, cy - dlg_h//2, cx + dlg_w//2, cy + dlg_h//2), fill=(15, 8, 8), outline=(255, 150, 50), width=2)

            # Title text
            q_text = "CHOOSE POWER ACTION"
            qw, qh = self._get_text_size(q_text, self._f_btn)
            draw.text((cx - qw//2, cy - dlg_h//2 + 14), q_text, fill=(255, 200, 100), font=self._f_btn)

            # YES / NO / RESTART buttons
            btn_y_top = cy + 12
            btn_y_bot = cy + dlg_h//2 - 12

            # SHUTDOWN button (left)
            s_x1 = cx - 165
            s_x2 = cx - 55
            draw.rectangle((s_x1, btn_y_top, s_x2, btn_y_bot), fill=(180, 30, 30), outline=(255, 100, 100))
            sw, sh = self._get_text_size("SHUTDOWN", self._f_subtitle_small)
            draw.text(((s_x1 + s_x2 - sw)//2, (btn_y_top + btn_y_bot - sh)//2), "SHUTDOWN", fill=white, font=self._f_subtitle_small)
            _new_zones["PWR_SHUT"] = (s_x1, btn_y_top, s_x2, btn_y_bot)

            # RESTART button (middle)
            r_x1 = cx - 45
            r_x2 = cx + 45
            draw.rectangle((r_x1, btn_y_top, r_x2, btn_y_bot), fill=(30, 80, 180), outline=(100, 150, 255))
            rw, rh = self._get_text_size("RESTART", self._f_subtitle_small)
            draw.text(((r_x1 + r_x2 - rw)//2, (btn_y_top + btn_y_bot - rh)//2), "RESTART", fill=white, font=self._f_subtitle_small)
            _new_zones["PWR_REBOOT"] = (r_x1, btn_y_top, r_x2, btn_y_bot)

            # CANCEL button (right)
            c_x1 = cx + 55
            c_x2 = cx + 165
            draw.rectangle((c_x1, btn_y_top, c_x2, btn_y_bot), fill=(40, 50, 60), outline=(150, 160, 170))
            cw, ch = self._get_text_size("CANCEL", self._f_subtitle_small)
            draw.text(((c_x1 + c_x2 - cw)//2, (btn_y_top + btn_y_bot - ch)//2), "CANCEL", fill=white, font=self._f_subtitle_small)
            _new_zones["PWR_CANCEL"] = (c_x1, btn_y_top, c_x2, btn_y_bot)

        # ═══ CALIB CHOICE DIALOG ═══
        if self._calib_confirm and now < self._calib_confirm_until:
            cx, cy = W // 2, (hdr_b + foot_t) // 2
            dlg_w, dlg_h = 300, 140

            draw.rectangle((cx - dlg_w//2 - 3, cy - dlg_h//2 - 3, cx + dlg_w//2 + 3, cy + dlg_h//2 + 3), fill=(10, 40, 60))
            draw.rectangle((cx - dlg_w//2, cy - dlg_h//2, cx + dlg_w//2, cy + dlg_h//2), fill=(5, 10, 15), outline=(100, 200, 255), width=2)

            q_text = "CHOOSE CALIBRATION MODE"
            qw, qh = self._get_text_size(q_text, self._f_btn)
            draw.text((cx - qw//2, cy - dlg_h//2 + 12), q_text, fill=white, font=self._f_btn)

            # Buttons
            btn_h_c = 40
            # AUTO button
            ax1, ay1 = cx - dlg_w//2 + 15, cy - 10
            ax2, ay2 = cx + dlg_w//2 - 15, cy + btn_h_c - 10
            draw.rectangle((ax1, ay1, ax2, ay2), fill=(20, 60, 100), outline=(80, 150, 255))
            txt1 = "1. AUTO NF (Dynamic)"
            tw1, th1 = self._get_text_size(txt1, self._f_btn)
            draw.text((ax1 + (ax2-ax1-tw1)//2, ay1 + (ay2-ay1-th1)//2), txt1, fill=white, font=self._f_btn)
            _new_zones["CAL_AUTO"] = (ax1, ay1, ax2, ay2)

            # FIXED button
            fx1, fy1 = cx - dlg_w//2 + 15, cy + btn_h_c
            fx2, fy2 = cx + dlg_w//2 - 15, cy + btn_h_c * 2
            draw.rectangle((fx1, fy1, fx2, fy2), fill=(100, 60, 20), outline=(255, 150, 80))
            txt2 = "2. FIXED NF (Static)"
            tw2, th2 = self._get_text_size(txt2, self._f_btn)
            draw.text((fx1 + (fx2-fx1-tw2)//2, fy1 + (fy2-fy1-th2)//2), txt2, fill=white, font=self._f_btn)
            _new_zones["CAL_FIXED"] = (fx1, fy1, fx2, fy2)

        # ═══ ATOMIC ZONE UPDATE ═══
        with self._zones_lock:
            self._touch_zones = _new_zones

        # Output
        if self.preview:
            self._img.save("preview.png")
        else:
            with self._spi_lock:
                self.app.device.display(self._img)

    def _draw_spectrum(self, draw, l, t, r, b, metrics, power, accent, grid, nf, peak, small=False):
        # Draw background and grid first
        draw.rectangle((l, t, r, b), outline=None, fill=(10, 10, 12))
        sw, sh = r - l, b - t
        
        # Label (Subtle)
        lbl = "MINI SPECTRUM" if small else "REAL-TIME SPECTRUM"
        draw.text((l + 6, t + 4), lbl, fill=self._dim(accent, 0.5), font=self._f_footer)

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
        nf_y = b - 15
        draw.text((l + 10, nf_y), "NOISE FLOOR", fill=(100, 100, 110), font=self._f_footer)
        for gx in range(l, r, 8):
            draw.line((gx, nf_y + 10, gx + 4, nf_y + 10), fill=(100, 100, 110))

        pts = scale_points(power, nf, sw, t+5, b-15) # Adjusted bot to leave room for NF line
        pts_off = [(px + l, py) for px, py in pts]
        if len(pts_off) > 2:
            sm = self._smooth(pts_off, sw)
            # Clip points slightly to stay inside borders
            sm = [(max(l+1, min(r-1, px)), py) for px, py in sm]
            poly = list(sm) + [(sm[-1][0], b-1), (sm[0][0], b-1)]
            draw.polygon(poly, fill=self._dim(accent, 0.15))
            draw.line(sm, fill=accent, width=1 if small else 2)
            
        # Draw outline LAST so it's always visible
        draw.rectangle((l, t, r, b), outline=accent, fill=None, width=1)

    # Gyro-relative compass ring labels (0° = reference heading at boot, not magnetic north)
    _RADAR_CARDINALS = (
        (0, "0", "N"), (45, "45", "NE"), (90, "90", "E"), (135, "135", "SE"),
        (180, "180", "S"), (225, "225", "SW"), (270, "270", "W"), (315, "315", "NW"),
    )

    def _draw_radar(self, draw, cx, cy, radius, accent, grid, white, state="SCANNING", metrics=None):
        # theta: device heading from MPU6050 gyro integration (relative compass, not GPS/magnetometer)
        theta = self.app.current_bearing

        # Draw outer bezel rings (double outline for premium look)
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=grid, width=1)
        draw.ellipse((cx-(radius-4), cy-(radius-4), cx+(radius-4), cy+(radius-4)), outline=grid, width=1)

        # Concentric inner rings
        for r in [radius*0.66, radius*0.33]:
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=grid)

        # Draw tick marks every 30 degrees (clockwise: rel_ang - 90)
        for tick_angle in range(0, 360, 30):
            rel_ang = (tick_angle - theta) % 360
            rad = np.radians(rel_ang - 90)
            x_out = cx + int(radius * np.cos(rad))
            y_out = cy + int(radius * np.sin(rad))
            x_in = cx + int((radius - 6) * np.cos(rad))
            y_in = cy + int((radius - 6) * np.sin(rad))
            draw.line((x_in, y_in, x_out, y_out), fill=grid, width=1)

        # Draw dynamically rotating crosshair grid lines: 0°↔180° and 90°↔270° (clockwise)
        # 0° ↔ 180° (North-South line)
        rel_0 = (0 - theta) % 360
        rad_0 = np.radians(rel_0 - 90)
        x_0 = cx + int(radius * np.cos(rad_0))
        y_0 = cy + int(radius * np.sin(rad_0))
        
        rel_180 = (180 - theta) % 360
        rad_180 = np.radians(rel_180 - 90)
        x_180 = cx + int(radius * np.cos(rad_180))
        y_180 = cy + int(radius * np.sin(rad_180))
        draw.line((x_0, y_0, x_180, y_180), fill=grid, width=1)

        # 90° ↔ 270° (East-West line)
        rel_90 = (90 - theta) % 360
        rad_90 = np.radians(rel_90 - 90)
        x_90 = cx + int(radius * np.cos(rad_90))
        y_90 = cy + int(radius * np.sin(rad_90))
        
        rel_270 = (270 - theta) % 360
        rad_270 = np.radians(rel_270 - 90)
        x_270 = cx + int(radius * np.cos(rad_270))
        y_270 = cy + int(radius * np.sin(rad_270))
        draw.line((x_90, y_90, x_270, y_270), fill=grid, width=1)
        
        # Cardinal numbers outside the ring, and abbreviations inside the ring
        for label_angle, deg_text, label_text in self._RADAR_CARDINALS:
            rel_ang = (label_angle - theta) % 360
            rad = np.radians(rel_ang - 90)
            
            # Number outside the circle
            lx_num = cx + int((radius + 12) * np.cos(rad))
            ly_num = cy + int((radius + 12) * np.sin(rad))
            tw_num, th_num = self._get_text_size(deg_text, self._f_compass)
            draw.text((lx_num - tw_num // 2, ly_num - th_num // 2), deg_text, fill=self._dim(white, 0.6), font=self._f_compass)
            
            # Abbreviation inside the circle (below/underneath the number)
            lx_abbr = cx + int((radius - 14) * np.cos(rad))
            ly_abbr = cy + int((radius - 14) * np.sin(rad))
            tw_abbr, th_abbr = self._get_text_size(label_text, self._f_compass)
            draw.text((lx_abbr - tw_abbr // 2, ly_abbr - th_abbr // 2), label_text, fill=white, font=self._f_compass)

        # Draw historical bearing lines with state-restricted heights
        for item in self._bearing_log:
            if len(item) == 4:
                angle, strength, line_state, _ = item
            elif len(item) == 3:
                angle, strength, line_state = item
            else:
                angle, strength = item[0], item[1]
                line_state = "WATCH"  # Fallback

            if line_state == "JAMMING":
                line_color = (255, 60, 70)   # Red
                line_len = radius            # Outer circle
            elif line_state == "WATCH":
                line_color = (255, 230, 50)  # Yellow
                line_len = radius * 0.66     # Middle circle
            elif line_state == "SCANNING":
                line_color = (0, 255, 140)   # Green
                line_len = radius * 0.33     # Innermost circle
            else:
                line_color = accent
                line_len = radius * strength

            rel_angle = (angle - theta) % 360
            rad = np.radians(rel_angle - 90)
            lx, ly = cx + int(line_len * np.cos(rad)), cy + int(line_len * np.sin(rad))
            draw.line((cx, cy, lx, ly), fill=line_color, width=2)

        # Pinned last-jam bearing (strongest sig during last JAMMING) until next jam event
        if self._persistent_jam is not None:
            pj = self._persistent_jam
            angle, strength = pj[0], pj[1]
            rel_angle = (angle - theta) % 360
            rad = np.radians(rel_angle - 90)
            lx, ly = cx + int(radius * np.cos(rad)), cy + int(radius * np.sin(rad))
            pin_color = (255, 90, 100)
            draw.line((cx, cy, lx, ly), fill=pin_color, width=3)
            draw.ellipse((lx - 3, ly - 3, lx + 3, ly + 3), fill=pin_color)

        # Draw dedicated white line representing the direction the device is currently facing
        draw.line((cx, cy, cx, cy - radius), fill=(255, 255, 255), width=2)
        # Add a tiny white triangle pointer at the tip
        draw.polygon([(cx - 4, cy - radius), (cx + 4, cy - radius), (cx, cy - radius + 6)], fill=(255, 255, 255))
        
        # Draw central user position dot
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(10, 10, 15), outline=white, width=1)
        
        # Bearing readout (bottom-right): heading + cardinal; show last jam when pinned
        brg_val = f"{int(self.app.current_bearing):03d}°"
        dir_name = self.get_cardinal_direction(self.app.current_bearing)

        lx, ly = 330, cy + 40
        draw.text((lx, ly), "HEADING", fill=(160, 160, 180), font=self._f_small)
        draw.text((lx, ly + 15), brg_val, fill=accent, font=self._f_score_big)
        draw.text((lx, ly + 48), dir_name, fill=accent, font=self._f_brg)



        if self._persistent_jam is not None and state != "JAMMING":
            jam_angle = self._persistent_jam[0]
            jam_dir = self.get_cardinal_direction(jam_angle)
            draw.text((lx, ly + 68), "LAST JAM", fill=(160, 160, 180), font=self._f_small)
            draw.text(
                (lx, ly + 78),
                f"{jam_angle:03d}° {jam_dir}",
                fill=(255, 90, 100),
                font=self._f_label,
            )

    def _draw_history(self, draw, l, t, r, b, accent, grid, white):
        draw.text((l, t-15), "MARGIN HISTORY", fill=self._dim(white, 0.6), font=self._f_label)
        draw.rectangle((l, t, r, b), outline=grid)
        if not self._history_log: return
        
        count = 50
        bw = (r - l) / float(count) # Use float for precise width
        for i, val in enumerate(self._history_log):
            h = int(np.clip((val+20) * (b-t)/40, 0, b - t))
            bx1 = l + int(i * bw)
            bx2 = l + int((i + 1) * bw) - 1
            draw.rectangle((bx1, b - h, bx2, b), fill=accent if val > 0 else (200,0,0))

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
        except Exception as e:
            print(f"[TOUCH] Init failed: {e}")

    def _read_xpt2046(self, cmd):
        with self._spi_lock:
            GPIO.output(self._T_CS_MANUAL, 0)
            resp = self._touch_spi.xfer2([cmd, 0, 0])
            GPIO.output(self._T_CS_MANUAL, 1)
            return ((resp[1] << 8) | resp[2]) >> 3

    def _load_touch_calibration(self):
        import os
        import json
        self._calib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "touch_calibration.json")
        
        # Default calibration parameters for XPT2046
        self._calib_params = {
            "X_MIN": 300,
            "X_MAX": 3850,
            "Y_MIN": 130,
            "Y_MAX": 3840,
            "SWAP_XY": False,
            "INVERT_X": True,
            "INVERT_Y": True
        }
        
        if os.path.exists(self._calib_path):
            try:
                with open(self._calib_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k in self._calib_params:
                        if k in data:
                            self._calib_params[k] = data[k]
                print(f"[TOUCH] Loaded calibration from {self._calib_path}: {self._calib_params}")
            except Exception as e:
                print(f"[TOUCH] Error loading calibration, using defaults: {e}")

    def _touch_worker(self):
        self._load_touch_calibration()
        while self._touch_running:
            try:
                x_raw, y_raw = self._read_xpt2046(_XPT2046_CMD_Y), self._read_xpt2046(_XPT2046_CMD_X)
                if 50 < x_raw < 4050 and 50 < y_raw < 4050:
                    params = self._calib_params
                    x_min, x_max = params["X_MIN"], params["X_MAX"]
                    y_min, y_max = params["Y_MIN"], params["Y_MAX"]
                    swap_xy = params.get("SWAP_XY", False)
                    invert_x = params.get("INVERT_X", True)
                    invert_y = params.get("INVERT_Y", True)

                    # Swap axes if configured
                    if swap_xy:
                        x_raw, y_raw = y_raw, x_raw
                        x_min, x_max, y_min, y_max = y_min, y_max, x_min, x_max
                        invert_x, invert_y = invert_y, invert_x

                    # Scale raw coordinates to 480x320 screen resolution
                    dx = x_max - x_min if x_max != x_min else 1
                    dy = y_max - y_min if y_max != y_min else 1

                    sx = (x_raw - x_min) * float(config.WIDTH) / dx
                    sy = (y_raw - y_min) * float(config.HEIGHT) / dy

                    if invert_x:
                        sx = float(config.WIDTH - 1) - sx
                    if invert_y:
                        sy = float(config.HEIGHT - 1) - sy

                    sx = int(np.clip(sx, 0, config.WIDTH - 1))
                    sy = int(np.clip(sy, 0, config.HEIGHT - 1))

                    self._handle_click(sx, sy)
                    time.sleep(0.3)
                time.sleep(0.05)
            except Exception:
                time.sleep(1)

    def _handle_click(self, x, y):
        now = time.time()
        self.app.buzzer.play_click()
        with self._zones_lock:
            zones = dict(self._touch_zones)

        # If PWR dialog is showing, only respond to buttons
        if self._pwr_confirm and now < self._pwr_confirm_until:
            for label in ["PWR_SHUT", "PWR_REBOOT", "PWR_CANCEL"]:
                zone = zones.get(label)
                if zone:
                    x1, y1, x2, y2 = zone
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        self._pwr_confirm = False
                        if label == "PWR_SHUT":
                            self.app.shutdown_requested.set()
                        elif label == "PWR_REBOOT":
                            self.app.reboot_requested.set()
                        else:
                            self.show_toast("CANCELLED", 1.0)
                        return
            # Tapped outside dialog = cancel
            self._pwr_confirm = False
            return

        # If CALIB dialog is showing
        if self._calib_confirm and now < self._calib_confirm_until:
            for label in ["CAL_AUTO", "CAL_FIXED"]:
                zone = zones.get(label)
                if zone:
                    x1, y1, x2, y2 = zone
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        self._calib_confirm = False
                        if label == "CAL_AUTO":
                            self.app.fixed_nf = False
                            self.show_toast("CALIB: AUTO MODE", 1.5)
                        else:
                            self.app.fixed_nf = True
                            self.show_toast("CALIB: FIXED MODE", 1.5)
                        self.app.request_calibration.set()
                        return
            self._calib_confirm = False
            return

        for label, (x1, y1, x2, y2) in zones.items():
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
                    self._calib_confirm = True
                    self._calib_confirm_until = now + 10.0 # 10 seconds to decide
                elif label == "PWR":
                    self._pwr_confirm = True
                    self._pwr_confirm_until = now + 5.0  # 5 seconds to decide
                return
