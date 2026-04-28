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
            rotate=1
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

        self._f_title     = _try(bold, 15)
        self._f_subtitle  = _try(regular, 11)
        self._f_status    = _try(bold, 28)
        self._f_state_big = _try(bold, 18)
        self._f_score_big = _try(mono, 36)
        self._f_score_sub = _try(regular, 14)
        self._f_label     = _try(regular, 10)
        self._f_value     = _try(bold, 22)
        self._f_unit      = _try(regular, 10)
        self._f_brg       = _try(bold, 16)
        self._f_compass   = _try(regular, 10)
        self._f_small     = _try(bold, 10)
        self._f_footer    = _try(bold, 8)
        self._f_fps       = _try(bold, 18)
        self._f_fps_label = _try(regular, 10)

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
        k = max(5, n // 40)
        if k % 2 == 0:
            k += 1
        y_s = np.convolve(y_new, np.ones(k) / k, mode='same')
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

        # ── theme ───────────────────────────────────────────────────
        if state == "JAMMING":
            accent  = (255, 80, 80)
            border  = (120, 30, 30)
            hdr_bg  = (40, 6, 6)
            lbl     = (100, 30, 30)
            grid    = (30, 10, 10)
            fill_c  = (45, 8, 8)
        elif state == "WATCH":
            accent  = (255, 200, 50)
            border  = (120, 90, 20)
            hdr_bg  = (40, 30, 5)
            lbl     = (100, 75, 18)
            grid    = (30, 22, 5)
            fill_c  = (35, 25, 4)
        else:
            accent  = (0, 220, 120)
            border  = (0, 70, 40)
            hdr_bg  = (4, 28, 16)
            lbl     = (0, 60, 32)
            grid    = (0, 20, 12)
            fill_c  = (0, 28, 15)

        line_col = self._dim(accent, 0.25)
        dim_txt  = self._dim(accent, 0.40)

        # ── layout constants ────────────────────────────────────────
        BD      = 2       # border width
        HDR_H   = 42      # header height
        SIDE_W  = 108     # left panel width
        RIGHT_W = 66      # right score panel width
        METRIC_H = 62     # bottom metrics row height
        BOTTOM_H = 30     # footer bar height

        # Derived positions
        content_top    = BD + HDR_H
        content_bottom = H - BD - BOTTOM_H
        spec_left      = BD + SIDE_W
        spec_right     = W - BD - RIGHT_W
        spec_top       = content_top
        spec_bottom    = content_bottom - METRIC_H
        metric_top     = spec_bottom
        metric_bottom  = content_bottom
        right_left     = spec_right
        right_right    = W - BD
        footer_top     = content_bottom
        footer_bottom  = H - BD

        # ════════════════════════════════════════════════════════════
        # BACKGROUND + BORDER
        # ════════════════════════════════════════════════════════════
        draw.rectangle((0, 0, W - 1, H - 1), fill=(8, 8, 8))
        # Outer border
        draw.rectangle((0, 0, W - 1, H - 1), outline=border, width=BD)

        # ════════════════════════════════════════════════════════════
        # HEADER
        # ════════════════════════════════════════════════════════════
        draw.rectangle((BD, BD, W - BD - 1, BD + HDR_H - 1), fill=hdr_bg)
        # Header bottom line
        draw.line((BD, content_top, W - BD, content_top), fill=line_col, width=1)

        draw.text((BD + 8, BD + 6), "GNSS L1 JAMMEING DETECTOR",
                  fill=(220, 220, 220), font=self._f_title)

        bw = self.app.sample_rate_hz / 2e6  # ±bandwidth in MHz
        sub_text = f"1575.42 MHz  |  GPS L1  |  G:{self.app.gain_db}dB"
        draw.text((BD + 8, BD + 24), sub_text,
                  fill=dim_txt, font=self._f_subtitle)

        # Status text (right side of header)
        short = {"SCANNING": "SCANNING", "WATCH": "WATCH", "JAMMING": "JAMMING"}
        st_txt = short.get(state, state)
        sw, _ = self._get_text_size(st_txt, self._f_status)
        draw.text((W - BD - sw - 10, BD + 8), st_txt,
                  fill=accent, font=self._f_status)

        # ════════════════════════════════════════════════════════════
        # LEFT PANEL
        # ════════════════════════════════════════════════════════════
        lp_l = BD
        lp_r = BD + SIDE_W
        lp_t = content_top
        lp_b = content_bottom
        draw.rectangle((lp_l, lp_t, lp_r, lp_b), fill=(6, 6, 6))
        # Right separator
        draw.line((lp_r, lp_t, lp_r, lp_b), fill=line_col, width=1)

        # STATE label + value
        draw.text((lp_l + 6, lp_t + 4), "STATE", fill=lbl, font=self._f_label)
        draw.text((lp_l + 6, lp_t + 16), st_txt, fill=accent,
                  font=self._f_state_big)

        # Compass
        compass_cx = lp_l + SIDE_W // 2
        compass_cy = lp_t + 130
        compass_r  = 38
        self._draw_polar(draw, accent, lbl, compass_cx, compass_cy, compass_r)

        # BRG
        best = self.get_best_bearing()
        bear_str = f"{best:03d}deg" if best is not None else "---"
        brg_y = lp_b - 58
        draw.text((lp_l + 6, brg_y), "BRG", fill=lbl, font=self._f_label)
        draw.text((lp_l + 6, brg_y + 12), bear_str, fill=accent,
                  font=self._f_brg)

        # Uptime
        uptime = int(time.time() - self.app.start_time)
        up_str = f"{uptime // 60}:{uptime % 60:02d}"
        draw.text((lp_l + 6, lp_b - 18), up_str,
                  fill=dim_txt, font=self._f_small)

        # ════════════════════════════════════════════════════════════
        # SPECTRUM AREA
        # ════════════════════════════════════════════════════════════
        draw.rectangle((spec_left, spec_top, spec_right, spec_bottom),
                       fill=(4, 4, 4))

        # Spectrum title
        spec_title = f"SPECTRUM  1575.42MHz  +-{bw:.3f}MHz"
        draw.text((spec_left + 6, spec_top + 3), spec_title,
                  fill=lbl, font=self._f_label)

        # Grid
        gh = spec_bottom - spec_top
        gw = spec_right - spec_left
        for i in range(1, 5):
            y = spec_top + int(gh * i / 5)
            draw.line((spec_left, y, spec_right, y), fill=grid, width=1)
        for i in range(1, 7):
            x = spec_left + int(gw * i / 7)
            draw.line((x, spec_top, x, spec_bottom), fill=grid, width=1)

        # Center freq marker
        cx = (spec_left + spec_right) // 2
        draw.line((cx, spec_top, cx, spec_bottom),
                  fill=self._dim(accent, 0.15), width=1)

        # Noise floor line
        nf_y = spec_bottom - 14
        draw.line((spec_left, nf_y, spec_right, nf_y),
                  fill=self._dim(accent, 0.20), width=1)
        draw.text((spec_left + 4, nf_y - 12), "NF",
                  fill=lbl, font=self._f_label)

        # ── draw spectrum curve ─────────────────────────────────────
        pts = scale_points(power, nf, gw, spec_top + 14, spec_bottom - 4)
        pts_off = [(x + spec_left, y) for x, y in pts]

        if len(pts_off) > 2:
            sm = self._smooth(pts_off, gw)

            # Temporal smoothing
            if (self._prev_smooth_y is not None
                    and len(self._prev_smooth_y) == len(sm)):
                a = 0.35
                sm = [(x, int(y * (1 - a) + py * a))
                      for (x, y), (_, py) in zip(sm, self._prev_smooth_y)]
            self._prev_smooth_y = sm

            # Fill under curve
            if len(sm) >= 2:
                poly = list(sm) + [(sm[-1][0], spec_bottom),
                                   (sm[0][0], spec_bottom)]
                draw.polygon(poly, fill=fill_c)

            # Curve line
            draw.line(sm, fill=accent, width=2)
            # Highlight
            draw.line(sm, fill=self._lerp(accent, (255, 255, 255), 0.2),
                      width=1)
        elif len(pts_off) > 1:
            draw.line(pts_off, fill=accent, width=2)

        # Spectrum border
        draw.rectangle((spec_left, spec_top, spec_right, spec_bottom),
                       outline=line_col)

        # ════════════════════════════════════════════════════════════
        # RIGHT PANEL (SCORE + VERTICAL BAR + FPS)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((right_left, content_top, right_right, content_bottom),
                       fill=(6, 6, 6))
        # Left separator
        draw.line((right_left, content_top, right_left, content_bottom),
                  fill=line_col, width=1)

        # SCORE label
        draw.text((right_left + 6, content_top + 4), "SCORE",
                  fill=lbl, font=self._f_label)

        # Large score number
        score_str = f"{score:02d}"
        ssw, _ = self._get_text_size(score_str, self._f_score_big)
        draw.text((right_left + (RIGHT_W - ssw) // 2, content_top + 16),
                  score_str, fill=accent, font=self._f_score_big)
        draw.text((right_left + (RIGHT_W) // 2 + 2, content_top + 52),
                  "/99", fill=dim_txt, font=self._f_score_sub)

        # Vertical score bar
        bar_x = right_left + 14
        bar_w = RIGHT_W - 28
        bar_top_y = content_top + 72
        bar_bot_y = content_bottom - 44
        bar_h = bar_bot_y - bar_top_y

        # Bar background
        draw.rectangle((bar_x, bar_top_y, bar_x + bar_w, bar_bot_y),
                       fill=(18, 18, 18))
        draw.rectangle((bar_x, bar_top_y, bar_x + bar_w, bar_bot_y),
                       outline=self._dim(line_col, 0.6))

        # Bar fill (from bottom up)
        fill_h = int(bar_h * score / 99)
        if fill_h > 0:
            draw.rectangle(
                (bar_x + 1, bar_bot_y - fill_h, bar_x + bar_w - 1, bar_bot_y),
                fill=accent
            )

        # FPS
        fps_y = content_bottom - 38
        draw.text((right_left + 6, fps_y), "FPS",
                  fill=lbl, font=self._f_fps_label)
        draw.text((right_left + 6, fps_y + 12), f"{fps_val}",
                  fill=accent, font=self._f_fps)

        # ════════════════════════════════════════════════════════════
        # METRICS ROW (3 columns: NOISE FLOOR | PEAK | FLOOR RISE)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((spec_left, metric_top, spec_right, metric_bottom),
                       fill=(6, 6, 6))
        # Top separator
        draw.line((spec_left, metric_top, spec_right, metric_top),
                  fill=line_col, width=1)

        met_w = spec_right - spec_left
        col_w = met_w // 3
        metrics_data = [
            ("NOISE FLOOR", f"{nf:.1f}",        "dBFS"),
            ("PEAK",        f"{peak:.1f}",       "dBFS"),
            ("FLOOR RISE",  f"{rise:+.1f}",      "dB"),
        ]

        for i, (label, val, unit) in enumerate(metrics_data):
            mx = spec_left + i * col_w + 8
            # Vertical separator between columns
            if i > 0:
                sx = spec_left + i * col_w
                draw.line((sx, metric_top + 2, sx, metric_bottom - 2),
                          fill=line_col, width=1)
            draw.text((mx, metric_top + 4), label,
                      fill=lbl, font=self._f_label)
            draw.text((mx, metric_top + 17), val,
                      fill=accent, font=self._f_value)
            draw.text((mx, metric_top + 42), unit,
                      fill=dim_txt, font=self._f_unit)

        # Metrics border
        draw.rectangle((spec_left, metric_top, spec_right, metric_bottom),
                       outline=line_col)

        # ════════════════════════════════════════════════════════════
        # BOTTOM BAR
        # ════════════════════════════════════════════════════════════
        draw.rectangle((BD, footer_top, W - BD, footer_bottom), fill=(6, 6, 6))
        draw.line((BD, footer_top, W - BD, footer_top),
                  fill=line_col, width=1)

        # SIG bar (signal strength based on score)
        sig_x = BD + 8
        sig_y = footer_top + 4
        draw.text((sig_x, sig_y), "SIG", fill=lbl, font=self._f_small)
        bar_sx = sig_x + 26
        bar_sw = 120
        bar_sh = 8
        draw.rectangle((bar_sx, sig_y + 2, bar_sx + bar_sw, sig_y + bar_sh + 2),
                       fill=(18, 18, 18))
        sig_fill = int(bar_sw * score / 99)
        if sig_fill > 0:
            draw.rectangle(
                (bar_sx, sig_y + 2, bar_sx + sig_fill, sig_y + bar_sh + 2),
                fill=accent
            )

        # Margin text (right side)
        margin_val = peak - (nf + self.app.warn_peak_threshold_db)
        margin_txt = f"MARGIN:{margin_val:+.1f}dB"
        mw, _ = self._get_text_size(margin_txt, self._f_small)
        draw.text((W - BD - mw - 10, sig_y), margin_txt,
                  fill=dim_txt, font=self._f_small)

        # Footer text
        footer_txt = "KMITL SPACE ENGINEERING  |  GNSS JAMMING DETECTOR v1.0"
        fw, _ = self._get_text_size(footer_txt, self._f_footer)
        fx = (W - fw) // 2
        draw.text((fx, footer_top + 16), footer_txt,
                  fill=self._dim(accent, 0.30), font=self._f_footer)

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
    def _draw_polar(self, draw, accent, lbl, cx, cy, r):
        # Concentric rings
        for radius in [r // 3, r * 2 // 3, r]:
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                         outline=self._dim(accent, 0.15))

        # Cross-hair lines
        for angle in range(0, 360, 45):
            rad = np.radians(angle - 90)
            ex = int(cx + np.cos(rad) * r)
            ey = int(cy + np.sin(rad) * r)
            draw.line((cx, cy, ex, ey), fill=self._dim(accent, 0.12), width=1)

        # Cardinal labels
        dim_lbl = self._dim(accent, 0.30)
        f = self._f_compass
        draw.text((cx - 3, cy - r - 12), "N", fill=dim_lbl, font=f)
        draw.text((cx - 3, cy + r + 3),  "S", fill=dim_lbl, font=f)
        draw.text((cx - r - 10, cy - 5), "W", fill=dim_lbl, font=f)
        draw.text((cx + r + 4, cy - 5),  "E", fill=dim_lbl, font=f)

        # Bearing vectors
        for angle_deg, norm in self._bearing_log:
            rad = np.radians(angle_deg - 90)
            px = int(cx + np.cos(rad) * r * norm)
            py = int(cy + np.sin(rad) * r * norm)
            draw.line((cx, cy, px, py), fill=accent, width=1)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=accent)

        # Center dot
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=accent)