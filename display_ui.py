import numpy as np
from PIL import Image, ImageDraw
from luma.core.interface.serial import spi
from luma.lcd.device import ili9488
from dsp import scale_points

class DisplayUI:
    def __init__(self, app):
        self.app = app
        self._init_display()
        self._init_drawing()
        self._bearing_log = []

    def _init_display(self):
        print("[SYSTEM] Initializing Display...")

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

    def draw_ui(self, metrics, power):
        draw = self.app._draw

        draw.rectangle(
            (0, 0, self.app.w, self.app.h),
            fill=(0, 0, 0)
        )

        state = metrics["state"]

        if state == "JAMMING":
            header_color = (60, 8, 8)
            status_color = (255, 90, 90)
        elif state == "WATCH":
            header_color = (65, 45, 0)
            status_color = (255, 215, 70)
        else:
            header_color = (0, 42, 24)
            status_color = (0, 255, 150)

        draw.rectangle(
            (0, 0, self.app.w, 62),
            fill=header_color
        )

        draw.text((14, 10), "GNSS L1 JAMMER DETECTOR", fill=(255,255,255))
        draw.text((14, 34), f"1575.42MHz  G:{self.app.gain_db}dB", fill=(100,100,100))

        short = {"SCANNING": "SCAN", "WATCH": "WTCH", "JAMMING": "JAM!"}
        draw.text((340, 8), short.get(state, state), fill=status_color)

        graph_top = 62
        graph_bottom = 218
        graph_left = 100

        bear_str = self._draw_polar(draw, status_color)

        import time
        uptime = int(time.time() - self.app.start_time)
        up_str = f"{uptime//60:02d}:{uptime%60:02d}"
        draw.text((4,  72), "STATE",   fill=(0, 60, 30))
        draw.text((4,  84), short.get(state, state), fill=status_color)
        draw.text((4, 150), "BRG",      fill=(0, 60, 30))
        draw.text((4, 162), bear_str,    fill=status_color)
        draw.text((4, 195), up_str,     fill=(0, 150, 80))

        pts = scale_points(
            power,
            self.app.noise_floor,
            self.app.w - graph_left,
            graph_top,
            graph_bottom
        )
        pts_offset = [(x + graph_left, y) for x, y in pts]
        if len(pts_offset) > 1:
            draw.line(pts_offset, fill=status_color, width=2)

        draw.text((102, 68), "SPECTRUM  1575.42MHz", fill=(0, 50, 25))
        cx = (self.app.w + graph_left) // 2
        draw.line((cx, graph_top, cx, graph_bottom), fill=(20,20,20), width=1)
        nf_y = graph_bottom - 8
        draw.line((graph_left, nf_y, self.app.w, nf_y), fill=(0,50,25), width=1)
        draw.text((102, nf_y - 10), "NF", fill=(0, 50, 25))
            
        nf = self.app.noise_floor
        peak = metrics["peak_p"]
        floor_rise = metrics["floor_rise"]
        score = metrics.get("score", 0)

        draw.rectangle((0, 228, self.app.w, 310), fill=(5, 5, 5))

        draw.text((10,  232), "NF",         fill=(0, 80, 40))
        draw.text((10,  246), f"{nf:.1f}",  fill=status_color)

        draw.text((120, 232), "PEAK",          fill=(0, 80, 40))
        draw.text((120, 246), f"{peak:.1f}",   fill=status_color)

        draw.text((240, 232), "RISE",              fill=(0, 80, 40))
        draw.text((240, 246), f"{floor_rise:+.1f}", fill=status_color)

        draw.text((360, 232), "SCORE",          fill=(0, 80, 40))
        draw.text((360, 246), f"{score:02d}/99", fill=status_color)

        bar_x = 10
        bar_y = 272
        bar_w = 460
        bar_h = 12
        draw.rectangle((bar_x, bar_y, bar_x+bar_w, bar_y+bar_h), fill=(20,20,20))
        fill_w = int(bar_w * score / 99)
        if fill_w > 0:
            draw.rectangle((bar_x, bar_y, bar_x+fill_w, bar_y+bar_h), fill=status_color)

        draw.text((10, 288), f"MARGIN: {peak-(nf+self.app.warn_peak_threshold_db):+.1f}dB", fill=(0,60,30))
        self.app.device.display(self.app._img)
        
    def record_bearing(self, angle_deg, peak_dbfs):
        norm = float(np.clip((peak_dbfs + 90) / 30.0, 0.0, 1.0))
        self._bearing_log.append((int(angle_deg) % 360, norm))
        if len(self._bearing_log) > 8:
            self._bearing_log.pop(0)

    def get_best_bearing(self):
        if not self._bearing_log:
            return None
        return max(self._bearing_log, key=lambda x: x[1])[0]

    def _draw_polar(self, draw, color):
        cx = 50
        cy = 148
        r  = 36

        for radius in [12, 24, 36]:
            draw.ellipse(
                (cx-radius, cy-radius, cx+radius, cy+radius),
                outline=(20, 20, 20)
            )

        for angle in range(0, 360, 45):
            rad = np.radians(angle - 90)
            ex = int(cx + np.cos(rad) * r)
            ey = int(cy + np.sin(rad) * r)
            draw.line((cx, cy, ex, ey), fill=(20, 20, 20), width=1)

        draw.text((cx-3, cy-r-10), "N", fill=(0, 60, 30))
        draw.text((cx-3, cy+r+2),  "S", fill=(0, 60, 30))
        draw.text((cx-r-8, cy-4),  "W", fill=(0, 60, 30))
        draw.text((cx+r+2, cy-4),  "E", fill=(0, 60, 30))

        for angle_deg, norm in self._bearing_log:
            rad = np.radians(angle_deg - 90)
            px = int(cx + np.cos(rad) * r * norm)
            py = int(cy + np.sin(rad) * r * norm)
            draw.line((cx, cy, px, py), fill=color, width=1)
            draw.ellipse((px-3, py-3, px+3, py+3), fill=color)

        draw.ellipse((cx-2, cy-2, cx+2, cy+2), fill=color)

        best = self.get_best_bearing()
        bear_str = f"{best:03d}" if best is not None else "---"
        return bear_str