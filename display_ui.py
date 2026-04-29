import time
import numpy as np
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
        self.app._img = Image.new(
            "RGB",
            (self.app.w, self.app.h),
            "black"
        )
        self.app._draw = ImageDraw.Draw(self.app._img)
        self._load_fonts()

    def _load_fonts(self):
        bold = [
            "DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        regular = [
            "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        mono = [
            "DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "C:/Windows/Fonts/consola.ttf",
        ]

        def _try(paths, size):
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        self._f_title     = _try(bold, 12)      # Title font
        self._f_subtitle  = _try(regular, 10)   # Subtitle
        self._f_status    = _try(bold, 20)      # Status badge
        self._f_state_big = _try(bold, 26)      # STATE value (SCAN/WTCH/JAM!)
        self._f_score_big = _try(mono, 36)      # Score number (02/28/82)
        self._f_score_sub = _try(regular, 12)   # /99
        self._f_label     = _try(regular, 9)    # Small labels
        self._f_value     = _try(bold, 22)      # Metric values
        self._f_unit      = _try(regular, 9)    # Units (dBFS, dB)
        self._f_brg       = _try(bold, 16)      # Bearing value
        self._f_compass   = _try(regular, 9)    # Compass N/S/E/W
        self._f_small     = _try(bold, 10)      # Small text
        self._f_footer    = _try(bold, 8)       # Footer
        self._f_fps       = _try(bold, 16)      # FPS number
        self._f_fps_label = _try(regular, 9)    # FPS label
        self._f_dblabel   = _try(regular, 8)    # dB axis labels

    # ── helpers ─────────────────────────────────────────────────────
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
        return list(zip(x_new.astype(int), np.clip(y_s, ys.min(), ys.max()).astype(int)))

    # ── main draw ───────────────────────────────────────────────────
    def draw_ui(self, metrics, power):
        draw = self.app._draw
        W, H = self.app.w, self.app.h  # 480, 320

        # FPS tracking
        self._fps_count += 1
        now = time.time()
        if now - self._fps_time >= 1.0:
            self._fps_display = self._fps_count
            self._fps_count = 0
            self._fps_time = now
        fps_val = self._fps_display if self._fps_display > 0 else self.app.target_fps

        state = metrics["state"]
        nf    = self.app.noise_floor
        peak  = metrics["peak_p"]
        rise  = metrics["floor_rise"]
        score = metrics.get("score", 0)

        # ── theme (state-based color) ───────────────────────────────
        if state == "JAMMING":
            accent  = (255, 80, 90)     # Red
            border_c = (255, 80, 90)
            hdr_bg  = (40, 8, 10)
            grid    = (60, 20, 25)
            fill_c  = (80, 15, 20)
        elif state == "WATCH":
            accent  = (255, 220, 50)    # Yellow
            border_c = (255, 220, 50)
            hdr_bg  = (50, 44, 10)
            grid    = (80, 70, 15)
            fill_c  = (100, 80, 10)
        else:  # SCANNING
            accent  = (0, 255, 136)     # Green
            border_c = (0, 255, 136)
            hdr_bg  = (8, 40, 20)
            grid    = (0, 80, 50)
            fill_c  = (0, 100, 60)

        white_high = (255, 255, 255)
        white_low  = (255, 255, 255)      # 100% white
        lbl_white  = (255, 255, 255)      # 100% white

        # ── layout constants (EXACT to prompt) ──────────────────────
        hdr_t, hdr_b = 0, 44
        lp_l, lp_r = 0, 106
        rp_l, rp_r = 418, 480
        spec_l, spec_r = 106, 418
        spec_t, spec_b = 44, 232
        met_t, met_b = 232, 284
        foot_t, foot_b = 284, 320

        # ════════════════════════════════════════════════════════════
        # BACKGROUND
        # ════════════════════════════════════════════════════════════
        draw.rectangle((0, 0, W - 1, H - 1), fill=(3, 3, 3))

        # ════════════════════════════════════════════════════════════
        # HEADER (y=0..44)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((0, hdr_t, W, hdr_b), fill=hdr_bg)
        draw.line((0, hdr_b, W, hdr_b), fill=accent, width=1)

        # Title left
        draw.text((8, 5), "GNSS L1 JAMMING DETECTOR HANDHELD", fill=white_high, font=self._f_title)

        # Subtitle: frequency | band | gain
        bw = self.app.sample_rate_hz / 2e6
        sub_text = f"1575.42 MHz  |  GPS L1  |  G:{self.app.gain_db}dB"
        draw.text((8, 23), sub_text, fill=accent, font=self._f_subtitle)

        # State text top-right (no border, full text)
        sw, sh = self._get_text_size(state, self._f_status)
        badge_x = W - sw - 14
        badge_y = 10
        draw.text((badge_x, badge_y), state, fill=accent, font=self._f_status)

        # Short state text for the left panel
        short_state = {"SCANNING": "SCAN", "WATCH": "WTCH", "JAMMING": "JAM!"}
        st_txt = short_state.get(state, state)

        # ════════════════════════════════════════════════════════════
        # LEFT PANEL (x=0..106)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((lp_l, hdr_b, lp_r, foot_t), fill=(6, 6, 6))
        draw.line((lp_r, hdr_b, lp_r, foot_t), fill=accent, width=1)

        # STATE text large
        draw.text((lp_l + 8, hdr_b + 8), "STATE", fill=lbl_white, font=self._f_label)
        draw.text((lp_l + 8, hdr_b + 20), st_txt, fill=accent, font=self._f_state_big)

        # Polar compass chart center
        compass_cx = lp_l + (lp_r - lp_l) // 2
        compass_cy = hdr_b + 105
        self._draw_polar(draw, accent, compass_cx, compass_cy, 36)

        # BEARING + uptime bottom
        best = self.get_best_bearing()
        bear_str = f"{best} DEG" if best is not None else "---"
        brg_y = compass_cy + 54
        draw.text((lp_l + 8, brg_y), "BEARING", fill=lbl_white, font=self._f_label)
        draw.text((lp_l + 8, brg_y + 14), bear_str, fill=accent, font=self._f_brg)

        uptime = int(time.time() - self.app.start_time)
        hrs = uptime // 3600
        mins = (uptime % 3600) // 60
        secs = uptime % 60
        up_str = f"UPTIME: {hrs:02d}:{mins:02d}:{secs:02d}"
        draw.text((lp_l + 8, foot_t - 16), up_str, fill=white_high, font=self._f_small)

        # ════════════════════════════════════════════════════════════
        # RIGHT PANEL (x=418..480)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((rp_l, hdr_b, rp_r, foot_t), fill=(6, 6, 6))
        draw.line((rp_l, hdr_b, rp_l, foot_t), fill=accent, width=1)

        draw.text((rp_l + 8, hdr_b + 8), "SCORE", fill=lbl_white, font=self._f_label)
        score_str = f"{score:02d}"
        ssw, ssh = self._get_text_size(score_str, self._f_score_big)
        score_x = rp_l + ((rp_r - rp_l) - ssw) // 2
        draw.text((score_x, hdr_b + 22), score_str, fill=accent, font=self._f_score_big)

        sw99, _ = self._get_text_size("/99", self._f_score_sub)
        sub_x = rp_l + ((rp_r - rp_l) - sw99) // 2
        draw.text((sub_x, hdr_b + 58), "/99", fill=white_high, font=self._f_score_sub)

        # Vertical bar fill bottom-up
        bar_x = rp_l + 10
        bar_w = (rp_r - rp_l) - 20
        bar_top_y = hdr_b + 80
        bar_bot_y = foot_t - 42
        bar_h = bar_bot_y - bar_top_y

        draw.rectangle((bar_x, bar_top_y, bar_x + bar_w, bar_bot_y), fill=(18, 18, 18), outline=self._dim(accent, 0.40), width=1)
        fill_h = int(bar_h * score / 99)
        if fill_h > 0:
            draw.rectangle((bar_x + 1, bar_bot_y - fill_h, bar_x + bar_w - 1, bar_bot_y), fill=accent)

        # FPS bottom
        fps_y = foot_t - 36
        draw.text((rp_l + 8, fps_y), "FPS", fill=lbl_white, font=self._f_fps_label)
        draw.text((rp_l + 8, fps_y + 14), f"{fps_val}", fill=accent, font=self._f_fps)

        # ════════════════════════════════════════════════════════════
        # SPECTRUM AREA (x=106..418, y=44..232)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((spec_l, spec_t, spec_r, spec_b), fill=(3, 3, 3))
        
        spec_draw_top = spec_t + 18
        spec_draw_bottom = spec_b - 4
        spec_draw_h = spec_draw_bottom - spec_draw_top
        spec_w = spec_r - spec_l

        # Horizontal grid lines
        db_labels = [-40, -50, -60, -70, -80, -90]
        for db_val in db_labels:
            norm = (db_val + 90) / 50.0
            y = spec_draw_top + int((1.0 - norm) * spec_draw_h)
            draw.line((spec_l, y, spec_r, y), fill=grid, width=1)

        # Vertical grid lines
        for i in range(1, 7):
            x = spec_l + int(spec_w * i / 7)
            draw.line((x, spec_draw_top, x, spec_draw_bottom), fill=grid, width=1)

        # Center frequency marker dashed vertical line
        cx = (spec_l + spec_r) // 2
        for y in range(spec_draw_top, spec_draw_bottom, 4):
            draw.line((cx, y, cx, y + 2), fill=self._dim(accent, 0.30), width=1)

        # Noise floor reference dashed horizontal line
        nf_norm = (nf + 90) / 50.0
        nf_y = spec_draw_top + int((1.0 - nf_norm) * spec_draw_h)
        nf_y = max(spec_draw_top, min(spec_draw_bottom, nf_y))
        for x in range(spec_l, spec_r, 4):
            draw.line((x, nf_y, x + 2, nf_y), fill=self._dim(accent, 0.35), width=1)
        draw.text((spec_l + 4, nf_y - 10), "NF", fill=lbl_white, font=self._f_label)

        # Draw spectrum curve
        pts = scale_points(power, nf, spec_w, spec_draw_top, spec_draw_bottom)
        pts_off = [(x + spec_l, y) for x, y in pts]

        if len(pts_off) > 2:
            sm = self._smooth(pts_off, spec_w)
            if (self._prev_smooth_y is not None and len(self._prev_smooth_y) == len(sm)):
                a = 0.35
                sm = [(x, int(y * (1 - a) + py * a)) for (x, y), (_, py) in zip(sm, self._prev_smooth_y)]
            self._prev_smooth_y = sm

            # Gradient fill (solid color fill_c for PIL)
            poly = list(sm) + [(sm[-1][0], spec_draw_bottom), (sm[0][0], spec_draw_bottom)]
            draw.polygon(poly, fill=fill_c)

            # Spectrum curve line width=2
            draw.line(sm, fill=accent, width=2)
            draw.line(sm, fill=self._lerp(accent, white_high, 0.15), width=1)
        elif len(pts_off) > 1:
            draw.line(pts_off, fill=accent, width=2)

        # Peak hold dashed line
        if peak > nf:
            peak_norm = (peak + 90) / 50.0
            peak_y = spec_draw_top + int((1.0 - peak_norm) * spec_draw_h)
            peak_y = max(spec_draw_top, min(spec_draw_bottom, peak_y))
            for x in range(spec_l, spec_r, 4):
                draw.line((x, peak_y, x + 2, peak_y), fill=self._dim(accent, 0.40), width=1)

        # Spectrum title
        spec_title = f"SPECTRUM  1575.42MHz  +-{bw:.3f}MHz"
        draw.text((spec_l + 6, spec_t + 3), spec_title, fill=lbl_white, font=self._f_label)

        # Y-axis dB labels on left: WHITE color always (drawn last so they are visible over the curve)
        for db_val in db_labels:
            norm = (db_val + 90) / 50.0
            y_pos = spec_draw_top + int((1.0 - norm) * spec_draw_h)
            db_text = f"{db_val}"
            _, th = self._get_text_size(db_text, self._f_dblabel)
            draw.text((spec_l + 4, y_pos - th // 2), db_text, fill=white_high, font=self._f_dblabel)

        draw.rectangle((spec_l, spec_t, spec_r, spec_b), outline=accent, width=1)

        # ════════════════════════════════════════════════════════════
        # METRICS ROW (y=232..284)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((spec_l, met_t, spec_r, met_b), fill=(6, 6, 6))
        draw.line((spec_l, met_t, spec_r, met_t), fill=accent, width=1)

        col_w = (spec_r - spec_l) // 4
        metrics_data = [
            ("NOISE FLOOR", f"{nf:.1f}", "dBFS"),
            ("PEAK", f"{peak:.1f}", "dBFS"),
            ("FLOOR RISE", f"{rise:+.1f}", "dB"),
            ("SCORE", f"{score}/99", ""),
        ]

        for i, (label, val, unit) in enumerate(metrics_data):
            mx = spec_l + i * col_w + 10
            if i > 0:
                sx = spec_l + i * col_w
                draw.line((sx, met_t + 2, sx, met_b - 2), fill=self._dim(accent, 0.50), width=1)

            draw.text((mx, met_t + 6), label, fill=lbl_white, font=self._f_label)
            draw.text((mx, met_t + 20), val, fill=accent, font=self._f_value)
            if unit:
                draw.text((mx, met_t + 42), unit, fill=white_high, font=self._f_unit)

        draw.rectangle((spec_l, met_t, spec_r, met_b), outline=accent, width=1)

        # ════════════════════════════════════════════════════════════
        # BOTTOM BAR (y=284..320)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((0, foot_t, W, foot_b), fill=(6, 6, 6))
        draw.line((0, foot_t, W, foot_t), fill=accent, width=1)

        # Margin text (right side)
        margin_val = peak - (nf + self.app.warn_peak_threshold_db)
        margin_txt = f"MARGIN:{margin_val:+.1f}dB"
        max_mw, _ = self._get_text_size("MARGIN:+99.9dB", self._f_small)
        fixed_margin_x = W - max_mw - 10

        # Percentage text
        pct_txt = f"{int(score * 100 / 99)}%"
        max_pw, _ = self._get_text_size("100%", self._f_small)
        fixed_pct_x = fixed_margin_x - 20 - max_pw
        pw, _ = self._get_text_size(pct_txt, self._f_small)

        # SIG STR bar
        sig_x = 8
        sig_y = foot_t + 6
        draw.text((sig_x, sig_y), "SIG STR", fill=lbl_white, font=self._f_small)

        bar_sx = sig_x + 52
        bar_sw = max(10, (fixed_pct_x - 6) - bar_sx)
        bar_sh = 8

        draw.rectangle((bar_sx, sig_y + 2, bar_sx + bar_sw, sig_y + bar_sh + 2), fill=(18, 18, 18))
        sig_fill = int(bar_sw * score / 99)
        if sig_fill > 0:
            draw.rectangle((bar_sx, sig_y + 2, bar_sx + sig_fill, sig_y + bar_sh + 2), fill=accent)

        pct_draw_x = fixed_pct_x + max_pw - pw
        draw.text((pct_draw_x, sig_y), pct_txt, fill=white_high, font=self._f_small)
        draw.text((fixed_margin_x, sig_y), margin_txt, fill=accent, font=self._f_small)

        footer_txt = "KMITL SPACE ENGINEERING  |  GNSS JAMMER DETECTOR v1.0"
        fw, _ = self._get_text_size(footer_txt, self._f_footer)
        draw.text(((W - fw) // 2, foot_t + 18), footer_txt, fill=white_low, font=self._f_footer)

        # Outer border with state-based color theme (drawn last)
        draw.rectangle((0, 0, W - 1, H - 1), outline=border_c, width=2)

        # ── output ──────────────────────────────────────────────────
        if self.preview:
            self.app._img.save("preview.png")
            if not self._preview_shown:
                try:
                    self.app._img.show()
                except Exception:
                    pass
                self._preview_shown = True
        else:
            self.app.device.display(self.app._img)

    # ── bearing ─────────────────────────────────────────────────────
    def record_bearing(self, angle_deg, peak_dbfs):
        norm = float(np.clip((peak_dbfs + 90) / 30.0, 0.0, 1.0))
        self._bearing_log.append((int(angle_deg) % 360, norm))
        if len(self._bearing_log) > 8:
            self._bearing_log.pop(0)

    def get_best_bearing(self):
        if not self._bearing_log:
            return None
        return max(self._bearing_log, key=lambda x: x[1])[0]

    # ── polar compass ───────────────────────────────────────────────
    def _draw_polar(self, draw, accent, cx, cy, r):
        dim_accent = self._dim(accent, 0.15)

        # Concentric rings
        for radius in [r // 3, r * 2 // 3, r]:
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                         outline=dim_accent, width=1)

        # Cross-hair lines (45° increments)
        dim_lines = self._dim(accent, 0.12)
        for angle in range(0, 360, 45):
            rad = np.radians(angle - 90)
            ex = int(cx + np.cos(rad) * r)
            ey = int(cy + np.sin(rad) * r)
            draw.line((cx, cy, ex, ey), fill=dim_lines, width=1)

        # Cardinal labels (N, S, E, W)
        card_color = (255, 255, 255)
        f = self._f_compass
        draw.text((cx - 3, cy - r - 12), "N", fill=card_color, font=f)
        draw.text((cx - 3, cy + r + 3),  "S", fill=card_color, font=f)
        draw.text((cx - r - 10, cy - 5), "W", fill=card_color, font=f)
        draw.text((cx + r + 4, cy - 5),  "E", fill=card_color, font=f)

        # Bearing vectors (accent color)
        for angle_deg, norm in self._bearing_log:
            rad = np.radians(angle_deg - 90)
            px = int(cx + np.cos(rad) * r * norm)
            py = int(cy + np.sin(rad) * r * norm)
            draw.line((cx, cy, px, py), fill=accent, width=1)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=accent)

        # Center dot
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=accent)
