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
        self._prev_smooth_y = None
        self._fps_time = time.time()
        self._fps_count = 0
        self._fps_display = 0
        self.view_mode = 0   # 0: Normal, 1: Search, 2: Analytics
        self._touch_zones = {}
        self._touch_ok = False
        self._spi_lock = threading.Lock()

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
        if len(self._bearing_log) > 8:
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

        # ── theme colours ───────────────────────────────────────────
        if state == "JAMMING":
            accent   = (255, 80, 90)
            border_c = (255, 80, 90)
            hdr_bg   = (40, 8, 10)
            grid     = (60, 20, 25)
            fill_c   = (80, 15, 20)
        elif state == "WATCH":
            accent   = (255, 220, 50)
            border_c = (255, 220, 50)
            hdr_bg   = (50, 44, 10)
            grid     = (80, 70, 15)
            fill_c   = (100, 80, 10)
        else:
            accent   = (0, 255, 136)
            border_c = (0, 255, 136)
            hdr_bg   = (8, 40, 20)
            grid     = (0, 80, 50)
            fill_c   = (0, 100, 60)

        white  = (255, 255, 255)
        lbl    = (255, 255, 255)

        # ── layout ──────────────────────────────────────────────────
        hdr_t, hdr_b   = 0, 44
        lp_l, lp_r     = 0, 106
        rp_l, rp_r     = 418, 480
        spec_l, spec_r = 106, 418
        spec_t, spec_b = 44, 232
        met_t, met_b   = 232, 284
        foot_t, foot_b = 284, 320

        # Background
        draw.rectangle((0, 0, W - 1, H - 1), fill=(3, 3, 3))

        # ════════════════════════════════════════════════════════════
        #  HEADER  (y = 0 … 44)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((0, hdr_t, W, hdr_b), fill=hdr_bg)
        draw.line((0, hdr_b, W, hdr_b), fill=accent, width=1)
        draw.text((8, 5), "GNSS L1 JAMMING DETECTOR HANDHELD",
                  fill=white, font=self._f_title)
        bw = self.app.sample_rate_hz / 2e6
        sub = f"1575.42 MHz  |  GPS L1  |  G:{self.app.gain_db}dB"
        draw.text((8, 23), sub, fill=accent, font=self._f_subtitle)
        sw, _ = self._get_text_size(state, self._f_status)
        draw.text((W - sw - 14, 10), state, fill=accent, font=self._f_status)

        # ════════════════════════════════════════════════════════════
        #  LEFT PANEL — 6 CONTROL BUTTONS  (x = 0 … 106)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((lp_l, hdr_b, lp_r, foot_t), fill=(6, 6, 6))
        draw.line((lp_r, hdr_b, lp_r, foot_t), fill=accent, width=1)

        btns = ["VIEW", "SNAP", "CALIB", "MUTE", "GAIN+", "EXIT"]
        btn_w = lp_r - lp_l - 12    # 94 px wide
        btn_h = 30
        btn_gap = 5
        btn_x = lp_l + 6
        btn_top = hdr_b + 6
        self._touch_zones = {}
        for i, label in enumerate(btns):
            by = btn_top + i * (btn_h + btn_gap)
            draw.rectangle((btn_x, by, btn_x + btn_w, by + btn_h),
                           fill=(25, 25, 40), outline=accent, width=1)
            tw, th = self._get_text_size(label, self._f_btn)
            draw.text((btn_x + (btn_w - tw) // 2, by + (btn_h - th) // 2),
                      label, fill=white, font=self._f_btn)
            self._touch_zones[label] = (btn_x, by, btn_x + btn_w, by + btn_h)

        # UPTIME at bottom of left panel
        uptime = int(time.time() - self.app.start_time)
        hrs  = uptime // 3600
        mins = (uptime % 3600) // 60
        secs = uptime % 60
        up_str = f"UP {hrs:02d}:{mins:02d}:{secs:02d}"
        draw.text((lp_l + 8, foot_t - 16), up_str, fill=white, font=self._f_small)

        # ════════════════════════════════════════════════════════════
        #  RIGHT PANEL  (x = 418 … 480)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((rp_l, hdr_b, rp_r, foot_t), fill=(6, 6, 6))
        draw.line((rp_l, hdr_b, rp_l, foot_t), fill=accent, width=1)

        # SCORE
        draw.text((rp_l + 8, hdr_b + 8), "SCORE", fill=lbl, font=self._f_label)
        sc_str = f"{score:02d}"
        ssw, _ = self._get_text_size(sc_str, self._f_score_big)
        score_x = rp_l + ((rp_r - rp_l) - ssw) // 2
        draw.text((score_x, hdr_b + 22), sc_str, fill=accent, font=self._f_score_big)

        sw99, _ = self._get_text_size("/99", self._f_score_sub)
        sub_x = rp_l + ((rp_r - rp_l) - sw99) // 2
        draw.text((sub_x, hdr_b + 58), "/99", fill=white, font=self._f_score_sub)

        # Vertical bar
        bar_x   = rp_l + 10
        bar_w   = (rp_r - rp_l) - 20
        bar_top = hdr_b + 80
        bar_bot = foot_t - 42
        bar_h   = bar_bot - bar_top
        draw.rectangle((bar_x, bar_top, bar_x + bar_w, bar_bot),
                       fill=(18, 18, 18), outline=self._dim(accent, 0.4), width=1)
        fill_h = int(bar_h * score / 99)
        if fill_h > 0:
            draw.rectangle((bar_x + 1, bar_bot - fill_h,
                            bar_x + bar_w - 1, bar_bot), fill=accent)

        # FPS
        fps_y = foot_t - 36
        draw.text((rp_l + 8, fps_y), "FPS", fill=lbl, font=self._f_fps_label)
        draw.text((rp_l + 8, fps_y + 14), f"{fps_val}", fill=accent, font=self._f_fps)

        # ════════════════════════════════════════════════════════════
        #  SPECTRUM  (x = 106 … 418, y = 44 … 232)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((spec_l, spec_t, spec_r, spec_b), fill=(3, 3, 3))

        s_top = spec_t + 18
        s_bot = spec_b - 4
        s_h   = s_bot - s_top
        s_w   = spec_r - spec_l

        # Horizontal grid + dB labels
        db_labels = [-40, -50, -60, -70, -80, -90]
        for db in db_labels:
            norm = (db + 90) / 50.0
            y = s_top + int((1.0 - norm) * s_h)
            draw.line((spec_l, y, spec_r, y), fill=grid, width=1)

        # Vertical grid
        for i in range(1, 7):
            x = spec_l + int(s_w * i / 7)
            draw.line((x, s_top, x, s_bot), fill=grid, width=1)

        # Centre freq marker
        cx = (spec_l + spec_r) // 2
        for y in range(s_top, s_bot, 4):
            draw.line((cx, y, cx, y + 2), fill=self._dim(accent, 0.30))

        # Noise floor dashed line
        nf_norm = (nf + 90) / 50.0
        nf_y = s_top + int((1.0 - nf_norm) * s_h)
        nf_y = max(s_top, min(s_bot, nf_y))
        for x in range(spec_l, spec_r, 4):
            draw.line((x, nf_y, x + 2, nf_y), fill=self._dim(accent, 0.35))
        draw.text((spec_l + 4, nf_y - 10), "NF", fill=lbl, font=self._f_label)

        # Spectrum curve
        pts = scale_points(power, nf, s_w, s_top, s_bot)
        pts_off = [(x + spec_l, y) for x, y in pts]

        if len(pts_off) > 2:
            sm = self._smooth(pts_off, s_w)
            if self._prev_smooth_y is not None and len(self._prev_smooth_y) == len(sm):
                a = 0.35
                sm = [(x, int(y * (1 - a) + py * a))
                      for (x, y), (_, py) in zip(sm, self._prev_smooth_y)]
            self._prev_smooth_y = sm

            poly = list(sm) + [(sm[-1][0], s_bot), (sm[0][0], s_bot)]
            draw.polygon(poly, fill=fill_c)
            draw.line(sm, fill=accent, width=2)
            draw.line(sm, fill=self._lerp(accent, white, 0.15), width=1)
        elif len(pts_off) > 1:
            draw.line(pts_off, fill=accent, width=2)

        # Peak hold
        if peak > nf:
            pk_norm = (peak + 90) / 50.0
            pk_y = s_top + int((1.0 - pk_norm) * s_h)
            pk_y = max(s_top, min(s_bot, pk_y))
            for x in range(spec_l, spec_r, 4):
                draw.line((x, pk_y, x + 2, pk_y), fill=self._dim(accent, 0.4))

        # Spectrum title
        draw.text((spec_l + 6, spec_t + 3),
                  f"SPECTRUM  1575.42MHz  +-{bw:.3f}MHz",
                  fill=lbl, font=self._f_label)

        # dB axis labels
        for db in db_labels:
            norm = (db + 90) / 50.0
            yp = s_top + int((1.0 - norm) * s_h)
            _, th = self._get_text_size(str(db), self._f_dblabel)
            draw.text((spec_l + 4, yp - th // 2), str(db),
                      fill=white, font=self._f_dblabel)

        draw.rectangle((spec_l, spec_t, spec_r, spec_b), outline=accent, width=1)

        # ════════════════════════════════════════════════════════════
        #  METRICS ROW  (y = 232 … 284)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((spec_l, met_t, spec_r, met_b), fill=(6, 6, 6))
        draw.line((spec_l, met_t, spec_r, met_t), fill=accent, width=1)

        col_w = (spec_r - spec_l) // 4
        met_data = [
            ("NOISE FLOOR", f"{nf:.1f}",          "dBFS"),
            ("PEAK",        f"{peak:.1f}",         "dBFS"),
            ("FLOOR RISE",  f"{rise:+.1f}",        "dB"),
            ("MARGIN",      f"{margin_val:+.1f}",  "dB"),
        ]
        for i, (mlabel, mval, munit) in enumerate(met_data):
            mx = spec_l + i * col_w + 10
            if i > 0:
                sx = spec_l + i * col_w
                draw.line((sx, met_t + 2, sx, met_b - 2),
                          fill=self._dim(accent, 0.50), width=1)
            draw.text((mx, met_t + 6),  mlabel, fill=lbl,    font=self._f_label)
            draw.text((mx, met_t + 20), mval,   fill=accent,  font=self._f_value)
            draw.text((mx, met_t + 42), munit,  fill=white,   font=self._f_unit)

        draw.rectangle((spec_l, met_t, spec_r, met_b), outline=accent, width=1)

        # ════════════════════════════════════════════════════════════
        #  BOTTOM BAR  (y = 284 … 320)
        # ════════════════════════════════════════════════════════════
        draw.rectangle((0, foot_t, W, foot_b), fill=(6, 6, 6))
        draw.line((0, foot_t, W, foot_t), fill=accent, width=1)

        pct_txt = f"{int(score * 100 / 99)}%"
        pw, _ = self._get_text_size(pct_txt, self._f_small)
        pct_x = W - pw - 10
        sig_y = foot_t + 6

        draw.text((8, sig_y), "SIG STR", fill=lbl, font=self._f_small)

        bar_sx = 62
        bar_ex = pct_x - 12
        bar_sw = bar_ex - bar_sx
        bar_sh = 8
        draw.rectangle((bar_sx, sig_y + 2, bar_sx + bar_sw, sig_y + bar_sh + 2),
                       fill=(18, 18, 18), outline=self._dim(accent, 0.3), width=1)
        sig_fill = int(bar_sw * score / 99)
        if sig_fill > 0:
            draw.rectangle((bar_sx + 1, sig_y + 3,
                            bar_sx + sig_fill, sig_y + bar_sh + 1), fill=accent)
            if sig_fill > 2:
                draw.line((bar_sx + 1, sig_y + 3, bar_sx + sig_fill, sig_y + 3),
                          fill=white, width=1)
        draw.text((pct_x, sig_y), pct_txt, fill=white, font=self._f_small)

        footer = "KMITL SPACE ENGINEERING  |  GNSS JAMMER DETECTOR v1.0"
        fw, _ = self._get_text_size(footer, self._f_footer)
        draw.text(((W - fw) // 2, foot_t + 18), footer, fill=white,
                  font=self._f_footer)

        # Outer border
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
            with self._spi_lock:
                self.app.device.display(self.app._img)

    # ════════════════════════════════════════════════════════════════
    #                     TOUCH  CONTROLLER
    # ════════════════════════════════════════════════════════════════
    def _init_touch(self):
        """Initialise XPT2046 using Hardware SPI but Manual CS on GPIO 22."""
        if spidev is None or GPIO is None:
            print("[TOUCH] spidev or RPi.GPIO not installed -- touch disabled")
            return

        self._T_CS_MANUAL = 22  # GPIO 22 (Pin 15)

        print(f"[TOUCH] Initializing SPI0.1 with Manual CS on GPIO {self._T_CS_MANUAL}...")
        try:
            # 1. Setup SPI for data (CLK, DIN, OUT)
            self._touch_spi = spidev.SpiDev()
            self._touch_spi.open(0, 1) # Still open 0.1, but we will toggle CS manually
            self._touch_spi.max_speed_hz = 100000
            self._touch_spi.mode = 0
            # Disable hardware CS toggling if possible (or just ignore it)
            self._touch_spi.no_cs = True 

            # 2. Setup Manual CS Pin
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self._T_CS_MANUAL, GPIO.OUT, initial=GPIO.HIGH)
            
            self._touch_ok = True
            t = threading.Thread(target=self._touch_worker, daemon=True)
            t.start()

        except FileNotFoundError:
            print("[TOUCH ERROR] /dev/spidev0.1 not found!")
            print("[TOUCH ERROR] Make sure SPI is enabled: sudo raspi-config -> Interface -> SPI")
            print("[TOUCH ERROR] You may also need: dtoverlay=spi0-2cs  in /boot/config.txt")
        except PermissionError:
            print("[TOUCH ERROR] Permission denied on /dev/spidev0.1")
            print("[TOUCH ERROR] Try: sudo chmod 666 /dev/spidev0.1")
        except Exception as e:
            print(f"[TOUCH ERROR] Unexpected init failure: {type(e).__name__}: {e}")

    def _read_xpt2046(self, command):
        """Read 12-bit value using Manual CS toggling (GPIO 22)."""
        with self._spi_lock:
            # Select chip
            GPIO.output(self._T_CS_MANUAL, GPIO.LOW)
            resp = self._touch_spi.xfer2([command, 0x00, 0x00])
            # Deselect chip
            GPIO.output(self._T_CS_MANUAL, GPIO.HIGH)
            return ((resp[1] << 8) | resp[2]) >> 3

    def _touch_worker(self):
        """Poll XPT2046 with manual CS logic."""
        X_MIN, X_MAX = 300, 3850
        Y_MIN, Y_MAX = 130, 3840
        print("[TOUCH] Manual CS worker started -- using GPIO 22")
        last_idle_time = time.time()
        while True:
            try:
                x_raw = self._read_xpt2046(0x94) # X
                y_raw = self._read_xpt2046(0xD4) # Y

                if 50 < x_raw < 4050 and 50 < y_raw < 4050:
                    # Map raw -> screen (Applying inversion based on calib data)
                    sx = int(np.clip(479 - ((x_raw - X_MIN) * 480 / (X_MAX - X_MIN)), 0, 479))
                    sy = int(np.clip(319 - ((y_raw - Y_MIN) * 320 / (Y_MAX - Y_MIN)), 0, 319))
                    print(f"[TOUCH] DETECTED! raw=({x_raw},{y_raw}) -> screen=({sx},{sy})")
                    self._handle_click(sx, sy)
                    time.sleep(0.4)
                else:
                    if time.time() - last_idle_time > 2.0:
                        print(f"[TOUCH DEBUG] Worker alive. Raw: X={x_raw}, Y={y_raw}")
                        last_idle_time = time.time()
                
                time.sleep(0.05)
            except Exception as e:
                # Suppress flood, show errors occasionally
                time.sleep(1)


    def _handle_click(self, x, y):
        for label, (x1, y1, x2, y2) in self._touch_zones.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                print(f"[TOUCH] >>> Button '{label}' pressed!")
                if label == "VIEW":
                    self.view_mode = (self.view_mode + 1) % 3
                    print(f"[TOUCH]     View mode -> {self.view_mode}")
                elif label == "MUTE":
                    self.app.toggle_mute()
                elif label == "CALIB":
                    self.app.recalibrate()
                elif label == "SNAP":
                    self.app.manual_capture()
                elif label == "GAIN+":
                    self.app.adjust_gain(2.0)
                elif label == "EXIT":
                    self.app.running = False
                return
        # If we get here no button matched
        print(f"[TOUCH] tap at ({x},{y}) -- no button hit")