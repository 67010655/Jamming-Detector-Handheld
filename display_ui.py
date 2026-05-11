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
        
        # In Normal Mode, the menu is on the left. In other modes, we might still want it.
        if self.view_mode == 1: self._render_search_mode(draw, metrics, accent)
        elif self.view_mode == 2: self._render_analytics_mode(draw, metrics, power, accent)
        else: self._render_normal_mode(draw, metrics, power, accent, fps_val)
        
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

        # Left Panel - CONTROL BUTTONS STACKED
        draw.rectangle((0, hdr_b, lp_r, 284), fill=(10,10,15))
        draw.line((lp_r, hdr_b, lp_r, 284), fill=accent)
        
        self._draw_side_menu(draw, accent, 5, hdr_b + 5, lp_r - 10)
        
        # Uptime at bottom of left panel
        uptime = int(time.time() - self.app.start_time)
        ut_str = f"UP: {uptime//3600:02d}:{(uptime%3600)//60:02d}:{uptime%60:02d}"
        draw.text((10, 268), ut_str, fill=(200,200,200), font=self._f_small)

        # Right Panel
        draw.rectangle((rp_l, hdr_b, W, 284), fill=(6,6,8)); draw.line((rp_l, hdr_b, rp_l, 284), fill=accent)
        draw.text((rp_l+8, hdr_b+5), "SCORE", fill=(200,200,200), font=self._f_label)
        draw.text((rp_l+10, hdr_b+18), f"{score:02d}", fill=accent, font=self._f_score_big)
        draw.text((rp_l+8, 255), f"FPS: {fps}", fill=(150,150,150), font=self._f_small)

        # Spectrum Area
        spec_w = rp_l - lp_r
        pts = scale_points(power, nf, spec_w, hdr_b+20, spec_b-5)
        pts_off = [(x + lp_r, y) for x, y in pts]
        if len(pts_off) > 1:
            draw.polygon(pts_off + [(pts_off[-1][0], spec_b), (pts_off[0][0], spec_b)], fill=self._dim(accent, 0.1))
            draw.line(pts_off, fill=accent, width=2)
        draw.rectangle((lp_r, hdr_b, rp_l, spec_b), outline=accent)

        # Metrics Row
        draw.rectangle((lp_r, spec_b, rp_l, met_b), fill=(12,12,20), outline=accent)
        draw.text((lp_r+10, spec_b+8), f"NF: {nf:.1f} dBFS   PEAK: {metrics['peak_p']:.1f} dBFS", fill=(255,255,255), font=self._f_value)

        # Footer
        draw.rectangle((0, 284, W, 320), fill=(5,5,5)); draw.line((0, 284, W, 284), fill=accent)
        draw.text((10, 290), "SIG STR", fill=(200,200,200), font=self._f_small)
        bar_w = int((W-120) * score/99)
        draw.rectangle((70, 294, 70+bar_w, 302), fill=accent)
        footer_txt = "KMITL SPACE ENGINEERING | GNSS JAMMER DETECTOR v1.0"
        draw.text((W//2 - 100, 308), footer_txt, fill=(150,150,150), font=self._f_footer)

    def _draw_side_menu(self, draw, accent, x, y, w):
        btns = ["VIEW", "SNAP", "CALIB", "MUTE", "GAIN+", "EXIT"]
        btn_h = 32
        gap = 5
        self._touch_zones = {} # Reset zones for this frame
        for i, label in enumerate(btns):
            by = y + i * (btn_h + gap)
            # Glassmorphism look for buttons
            draw.rectangle((x, by, x + w, by + btn_h), fill=(30, 30, 45), outline=accent, width=1)
            lw, lh = self._get_text_size(label, self._f_label)
            draw.text((x + (w - lw)//2, by + (btn_h - lh)//2), label, fill=(255,255,255), font=self._f_label)
            self._touch_zones[label] = (x, by, x + w, by + btn_h)

    def _render_search_mode(self, draw, metrics, accent):
        W, H = 480, 320
        cx, cy = W//2, H//2
        self._draw_polar(draw, accent, cx, cy, 110)
        draw.text((20, 20), "SEARCH MODE", fill=(255,255,255), font=self._f_status)
        self._draw_side_menu(draw, accent, 10, 60, 80) # Still show menu on side

    def _render_analytics_mode(self, draw, metrics, power, accent):
        W, H = 480, 320
        draw.text((20, 10), "ANALYTICS MODE", fill=(255,255,255), font=self._f_status)
        self._draw_side_menu(draw, accent, 10, 60, 80) # Still show menu on side
        pts = scale_points(power, metrics.get("noise_floor",-90), W-120, 60, H-100)
        pts_off = [(x+100, y) for x, y in pts]
        if len(pts_off)>1: draw.line(pts_off, fill=accent, width=2)

    def _draw_polar(self, draw, accent, cx, cy, r):
        dim_a = self._dim(accent, 0.2)
        for rad in [r//3, r*2//3, r]: draw.ellipse((cx-rad, cy-rad, cx+rad, cy+rad), outline=dim_a)
        for ang in range(0, 360, 45):
            rd = np.radians(ang-90)
            draw.line((cx, cy, int(cx+np.cos(rd)*r), int(cy+np.sin(rd)*r)), fill=dim_a)

    def _init_touch(self):
        print("[SYSTEM] Initializing Touch...")
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
                    sx = int(np.clip((xr - X_MIN) * 480 / (X_MAX - X_MIN), 0, 479))
                    sy = int(np.clip((yr - Y_MIN) * 320 / (Y_MAX - Y_MIN), 0, 319))
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