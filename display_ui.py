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
        self.show_menu = True # Always show menu buttons for now
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
        print("[SYSTEM] Initializing Display (ILI9488)...")
        from luma.core.interface.serial import spi
        from luma.lcd.device import ili9488
        try:
            serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, bus_speed_hz=32000000)
            self.app.device = ili9488(serial, width=self.app.w, height=self.app.h, rotate=0)
        except Exception as e:
            print(f"[ERROR] Display init failed: {e}")

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
        self._f_title = _try(bold, 12); self._f_subtitle = _try(regular, 10); self._f_status = _try(bold, 20)
        self._f_state_big = _try(bold, 26); self._f_score_big = _try(mono, 36); self._f_score_sub = _try(regular, 12)
        self._f_label = _try(regular, 9); self._f_value = _try(bold, 22); self._f_unit = _try(regular, 9)
        self._f_brg = _try(bold, 16); self._f_compass = _try(regular, 9); self._f_small = _try(bold, 9)
        self._f_footer = _try(bold, 8); self._f_fps = _try(bold, 16); self._f_fps_label = _try(regular, 9); self._f_dblabel = _try(regular, 8)

    @staticmethod
    def _dim(c, f): return tuple(max(0, min(255, int(v * f))) for v in c)
    @staticmethod
    def _lerp(c1, c2, t): return tuple(int(a + (b - a) * max(0, min(1, t))) for a, b in zip(c1, c2))
    def _smooth(self, pts, n):
        if len(pts) < 3: return pts
        xs, ys = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
        x_new = np.linspace(xs[0], xs[-1], n)
        y_new = np.interp(x_new, xs, ys)
        k = 9; pad = k//2
        y_padded = np.pad(y_new, pad_width=pad, mode='edge')
        y_s = np.convolve(y_padded, np.ones(k)/k, mode='valid')
        return list(zip(x_new.astype(int), y_s.astype(int)))

    def draw_ui(self, metrics, power):
        draw = self.app._draw
        W, H = self.app.w, self.app.h
        self._fps_count += 1
        now = time.time()
        if now - self._fps_time >= 1.0:
            self._fps_display = self._fps_count
            self._fps_count = 0; self._fps_time = now
        fps_val = self._fps_display if self._fps_display > 0 else self.app.target_fps
        state = metrics["state"]
        accent = (255, 80, 90) if state=="JAMMING" else ((255, 220, 50) if state=="WATCH" else (0, 255, 136))
        
        draw.rectangle((0, 0, W, H), fill=(3, 3, 3))
        if self.view_mode == 1: self._render_search_mode(draw, metrics, accent)
        elif self.view_mode == 2: self._render_analytics_mode(draw, metrics, power, accent)
        else: self._render_normal_mode(draw, metrics, power, accent, fps_val)
        
        self._draw_overlay_menu(draw, accent)
        if self.preview:
            self.app._img.save("preview.png")
            if not self._preview_shown:
                try: self.app._img.show(); self._preview_shown = True
                except: pass
        else: self.app.device.display(self.app._img)

    def _render_normal_mode(self, draw, metrics, power, accent, fps):
        W, H = 480, 320
        hdr_b, lp_r, rp_l, spec_b, met_b = 44, 106, 418, 232, 284
        state, nf, score = metrics["state"], metrics.get("noise_floor", -90), metrics.get("score", 0)
        
        # Header
        hdr_bg = (40, 8, 10) if state=="JAMMING" else ((45, 40, 10) if state=="WATCH" else (10, 35, 20))
        draw.rectangle((0, 0, W, hdr_b), fill=hdr_bg)
        draw.line((0, hdr_b, W, hdr_b), fill=accent, width=1)
        draw.text((10, 5), "GNSS L1 JAMMING DETECTOR", fill=(255,255,255), font=self._f_title)
        draw.text((10, 23), f"1575.42 MHz | GAIN: {self.app.gain_db}dB", fill=accent, font=self._f_subtitle)
        draw.text((W-100, 10), state, fill=accent, font=self._f_status)

        # Panels
        draw.rectangle((0, hdr_b, lp_r, 284), fill=(6,6,8)); draw.line((lp_r, hdr_b, lp_r, 284), fill=accent)
        draw.rectangle((rp_l, hdr_b, W, 284), fill=(6,6,8)); draw.line((rp_l, hdr_b, rp_l, 284), fill=accent)
        
        draw.text((8, hdr_b+5), "DIRECTION", fill=(200,200,200), font=self._f_label)
        self._draw_polar(draw, accent, 53, hdr_b+100, 40)
        
        draw.text((rp_l+8, hdr_b+5), "SCORE", fill=(200,200,200), font=self._f_label)
        draw.text((rp_l+10, hdr_b+18), f"{score:02d}", fill=accent, font=self._f_score_big)
        draw.text((rp_l+8, 255), f"FPS: {fps}", fill=(150,150,150), font=self._f_small)

        # Spectrum
        spec_w = rp_l - lp_r
        pts = scale_points(power, nf, spec_w, hdr_b+20, spec_b-5)
        pts_off = [(x + lp_r, y) for x, y in pts]
        if len(pts_off) > 1:
            draw.polygon(pts_off + [(pts_off[-1][0], spec_b), (pts_off[0][0], spec_b)], fill=self._dim(accent, 0.1))
            draw.line(pts_off, fill=accent, width=2)
        draw.rectangle((lp_r, hdr_b, rp_l, spec_b), outline=accent)

        # Metrics
        draw.rectangle((lp_r, spec_b, rp_l, met_b), fill=(12,12,20), outline=accent)
        draw.text((lp_r+10, spec_b+10), f"NF: {nf:.1f} dBFS   PEAK: {metrics['peak_p']:.1f} dBFS", fill=(255,255,255), font=self._f_value)

        # Footer
        draw.rectangle((0, 284, W, 320), fill=(5,5,5)); draw.line((0, 284, W, 284), fill=accent)
        draw.text((10, 290), "SIG STR", fill=(200,200,200), font=self._f_small)
        bar_w = int((W-120) * score/99)
        draw.rectangle((70, 294, 70+bar_w, 302), fill=accent)

    def _render_search_mode(self, draw, metrics, accent):
        W, H = 480, 320
        cx, cy = W//2, H//2 - 10
        self._draw_polar(draw, accent, cx, cy, 110)
        draw.text((W//2-60, 10), "SEARCH MODE", fill=(255,255,255), font=self._f_status)
        draw.text((20, 50), f"SCORE: {metrics['score']:02d}", fill=accent, font=self._f_score_big)

    def _render_analytics_mode(self, draw, metrics, power, accent):
        W, H = 480, 320
        draw.text((20, 10), "SPECTRUM ANALYTICS", fill=(255,255,255), font=self._f_status)
        pts = scale_points(power, metrics.get("noise_floor",-90), W-40, 60, H-80)
        pts_off = [(x+20, y) for x, y in pts]
        if len(pts_off)>1: draw.line(pts_off, fill=accent, width=2)

    def _draw_polar(self, draw, accent, cx, cy, r):
        dim_a = self._dim(accent, 0.2)
        for rad in [r//3, r*2//3, r]: draw.ellipse((cx-rad, cy-rad, cx+rad, cy+rad), outline=dim_a)
        for ang in range(0, 360, 45):
            rd = np.radians(ang-90)
            draw.line((cx, cy, int(cx+np.cos(rd)*r), int(cy+np.sin(rd)*r)), fill=dim_a)
        for ang_deg, norm in self._bearing_log:
            rd = np.radians(ang_deg-90)
            px, py = int(cx+np.cos(rd)*r*norm), int(cy+np.sin(rd)*r*norm)
            draw.line((cx, cy, px, py), fill=accent, width=2)
            draw.ellipse((px-3, py-3, px+3, py+3), fill=accent)

    def _draw_overlay_menu(self, draw, accent):
        W, H = 480, 320; btn_w, btn_h, gap = 66, 30, 5
        btns = ["VIEW", "SNAP", "CALIB", "MUTE", "GAIN+", "EXIT"]
        start_x = (W - (len(btns)*(btn_w+gap)))//2; y = H - btn_h - 4
        for i, label in enumerate(btns):
            bx = start_x + i*(btn_w+gap)
            draw.rectangle((bx, y, bx+btn_w, y+btn_h), fill=(30,30,45), outline=accent)
            lw, lh = self._get_text_size(label, self._f_footer)
            draw.text((bx+(btn_w-lw)//2, y+(btn_h-lh)//2), label, fill=(255,255,255), font=self._f_footer)
            self._touch_zones[label] = (bx, y, bx+btn_w, y+btn_h)

    def _init_touch(self):
        print("[SYSTEM] Initializing Touch (XPT2046)...")
        try:
            self._touch_spi = spidev.SpiDev(); self._touch_spi.open(0, 1)
            self._touch_spi.max_speed_hz = 1000000
            threading.Thread(target=self._touch_worker, daemon=True).start()
        except Exception as e: print(f"[ERROR] Touch init: {e}")

    def _touch_worker(self):
        X_MIN, X_MAX, Y_MIN, Y_MAX = 200, 3800, 300, 3900
        while True:
            try:
                rx, ry = self._touch_spi.xfer2([0x90,0,0]), self._touch_spi.xfer2([0xD0,0,0])
                xr, yr = ((rx[1]<<8)|rx[2])>>3, ((ry[1]<<8)|ry[2])>>3
                if xr > 150 and yr > 150:
                    # DEBUG: Print RAW values to help calibration
                    print(f"[TOUCH DEBUG] Raw: X={xr}, Y={yr}")
                    sx = int(np.clip((xr - X_MIN) * 480 / (X_MAX - X_MIN), 0, 479))
                    sy = int(np.clip((yr - Y_MIN) * 320 / (Y_MAX - Y_MIN), 0, 319))
                    print(f"[TOUCH DEBUG] Mapped: X={sx}, Y={sy}")
                    self._handle_click(sx, sy)
                    time.sleep(0.4)
                time.sleep(0.05)
            except: time.sleep(1)

    def _handle_click(self, x, y):
        for label, (x1, y1, x2, y2) in self._touch_zones.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                print(f"[TOUCH] {label} Pressed")
                if label == "VIEW": self.view_mode = (self.view_mode + 1) % 3
                elif label == "MUTE": self.app.toggle_mute()
                elif label == "CALIB": self.app.recalibrate()
                elif label == "SNAP": self.app.manual_capture()
                elif label == "GAIN+": self.app.adjust_gain(2.0)
                elif label == "EXIT": self.app.running = False
                return
    def record_bearing(self, ang, p):
        self._bearing_log.append((int(ang)%360, float(np.clip((p+90)/30,0,1))))
        if len(self._bearing_log)>12: self._bearing_log.pop(0)