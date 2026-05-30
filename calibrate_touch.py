#!/usr/bin/env python3
import time
import json
import os
import sys
import numpy as np

try:
    import spidev
    import RPi.GPIO as GPIO
except ImportError:
    spidev = None
    GPIO = None

from PIL import Image, ImageDraw, ImageFont
import config

# XPT2046 touch-controller SPI command bytes (single-ended, 12-bit)
_XPT2046_CMD_X = 0xD4   # channel 5 — X position (datasheet convention)
_XPT2046_CMD_Y = 0x94   # channel 1 — Y position (datasheet convention)

# Screen Dimensions
W, H = config.WIDTH, config.HEIGHT

class TouchCalibrator:
    def __init__(self):
        self.device = None
        self._touch_spi = None
        self._T_CS_MANUAL = 22
        
        self._init_display()
        self._init_touch()
        self._load_fonts()
        
    def _init_display(self):
        print("[SYSTEM] Initializing ILI9488 Display for Calibration...")
        try:
            from luma.core.interface.serial import spi
            from luma.lcd.device import ili9488
            # Same SPI setup as display_ui.py
            serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, bus_speed_hz=config.SPI_CLOCK_HZ)
            self.device = ili9488(serial, width=W, height=H, rotate=0)
            self._img = Image.new("RGB", (W, H), "black")
            self._draw = ImageDraw.Draw(self._img)
        except Exception as e:
            print(f"[ERROR] Display init failed: {e}")
            sys.exit(1)

    def _init_touch(self):
        if spidev is None or GPIO is None:
            print("[ERROR] GPIO or spidev not available. Make sure to run on Raspberry Pi.")
            sys.exit(1)
        
        try:
            self._touch_spi = spidev.SpiDev()
            self._touch_spi.open(0, 1)
            self._touch_spi.max_speed_hz, self._touch_spi.mode, self._touch_spi.no_cs = 100000, 0, True
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self._T_CS_MANUAL, GPIO.OUT, initial=GPIO.HIGH)
            print("[TOUCH] Touch controller (XPT2046) initialized successfully.")
        except Exception as e:
            print(f"[ERROR] Touch init failed: {e}")
            sys.exit(1)

    def _load_fonts(self):
        bold_paths = [
            "DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf"
        ]
        
        def _try(paths, size):
            for p in paths:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
            return ImageFont.load_default()
            
        self._font_title = _try(bold_paths, 18)
        self._font_desc = _try(bold_paths, 12)
        self._font_btn = _try(bold_paths, 14)

    def _read_xpt2046(self, cmd):
        GPIO.output(self._T_CS_MANUAL, 0)
        resp = self._touch_spi.xfer2([cmd, 0, 0])
        GPIO.output(self._T_CS_MANUAL, 1)
        return ((resp[1] << 8) | resp[2]) >> 3

    def _get_clean_touch(self, samples_count=15):
        """Reads raw values and applies median filtering for robust ADC filtering."""
        xs, ys = [], []
        start = time.time()
        while len(xs) < samples_count:
            x_raw = self._read_xpt2046(_XPT2046_CMD_Y)
            y_raw = self._read_xpt2046(_XPT2046_CMD_X)
            
            # XPT2046 active range checks
            if 50 < x_raw < 4050 and 50 < y_raw < 4050:
                xs.append(x_raw)
                ys.append(y_raw)
            
            if time.time() - start > 5.0: # Timeout
                return None
            time.sleep(0.01)
            
        # Return median to eliminate noise spike issues
        return int(np.median(xs)), int(np.median(ys))

    def _draw_screen(self, title, desc, target_pos=None):
        self._draw.rectangle((0, 0, W, H), fill=(8, 12, 16))
        
        # Draw frame border
        self._draw.rectangle((2, 2, W-2, H-2), outline=(0, 255, 140), width=2)
        
        # Render Texts
        tw, th = self._draw.textbbox((0, 0), title, font=self._font_title)[2:4] if hasattr(self._draw, "textbbox") else (len(title)*10, 20)
        self._draw.text(((W - tw)//2, 40), title, fill=(0, 255, 140), font=self._font_title)
        
        dw, dh = self._draw.textbbox((0, 0), desc, font=self._font_desc)[2:4] if hasattr(self._draw, "textbbox") else (len(desc)*6, 14)
        self._draw.text(((W - dw)//2, 80), desc, fill=(255, 255, 255), font=self._font_desc)

        # Draw Calibration Target (Crosshair & circle)
        if target_pos:
            tx, ty = target_pos
            # Crosshair lines
            self._draw.line((tx - 25, ty, tx + 25, ty), fill=(255, 50, 50), width=2)
            self._draw.line((tx, ty - 25, tx, ty + 25), fill=(255, 50, 50), width=2)
            # Outer ring
            self._draw.ellipse((tx - 12, ty - 12, tx + 12, ty + 12), outline=(255, 255, 255), width=2)
            # Inner solid circle
            self._draw.ellipse((tx - 4, ty - 4, tx + 4, ty + 4), fill=(255, 50, 50))
            
        self.device.display(self._img)

    def run_calibration(self):
        targets = [
            ("TOP-LEFT (มุมบนซ้าย)", (30, 30)),
            ("TOP-RIGHT (มุมบนขวา)", (W - 30, 30)),
            ("BOTTOM-RIGHT (มุมล่างขวา)", (W - 30, H - 30)),
            ("BOTTOM-LEFT (มุมล่างซ้าย)", (30, H - 30))
        ]
        
        raw_points = []
        
        for i, (name, pos) in enumerate(targets):
            self._draw_screen(
                f"POINT {i+1}/4: {name}", 
                "ใช้ปากกา Stylus กดค้างไว้ตรงกลางเป้าสีแดงจนกว่าจะเลื่อนจุด", 
                target_pos=pos
            )
            
            # Wait until screen is released first
            time.sleep(0.3)
            
            print(f"[CALIB] Waiting for touch at target {i+1}: {pos}...")
            # Loop until we get stable touched coordinates
            while True:
                touched = self._get_clean_touch(samples_count=10)
                if touched:
                    x_raw, y_raw = touched
                    raw_points.append((x_raw, y_raw))
                    print(f"[CALIB] Point {i+1} Raw ADC -> X: {x_raw}, Y: {y_raw}")
                    
                    # Short highlight chime / flash
                    self._draw_screen(f"POINT {i+1}/4: OK!", "บันทึกพิกัดสำเร็จ! ปล่อยนิ้วมือได้", target_pos=pos)
                    time.sleep(0.6)
                    break
                time.sleep(0.05)
                
        # Analyze points
        # raw_points order: 0: TL, 1: TR, 2: BR, 3: BL
        x_tl, y_tl = raw_points[0]
        x_tr, y_tr = raw_points[1]
        x_br, y_br = raw_points[2]
        x_bl, y_bl = raw_points[3]
        
        # 1. Swap XY Axis Detection
        # Compare horizontal raw variance vs vertical raw variance
        x_diff_h = abs(x_tr - x_tl)
        y_diff_h = abs(y_tr - y_tl)
        
        swap_xy = y_diff_h > x_diff_h
        print(f"[CALIB] Analyzing: x_diff_h={x_diff_h}, y_diff_h={y_diff_h} -> SwapXY={swap_xy}")
        
        if swap_xy:
            # If swapped, swap raw point coordinates so math below is aligned with screen layout
            raw_points = [(y, x) for (x, y) in raw_points]
            x_tl, y_tl = raw_points[0]
            x_tr, y_tr = raw_points[1]
            x_br, y_br = raw_points[2]
            x_bl, y_bl = raw_points[3]
            
        # 2. Compute Left, Right, Top, Bottom Averages
        x_left = (x_tl + x_bl) / 2.0
        x_right = (x_tr + x_br) / 2.0
        y_top = (y_tl + y_tr) / 2.0
        y_bottom = (y_bl + y_br) / 2.0
        
        # 3. Linear Extrapolation
        # Targets are 30px offset from the edges. Total W=480, H=320.
        # Target distance horizontal = 480 - 30 - 30 = 420px
        # Target distance vertical = 320 - 30 - 30 = 260px
        x_width = 420.0
        y_height = 260.0
        
        x_raw_per_px = (x_right - x_left) / x_width
        y_raw_per_px = (y_bottom - y_top) / y_height
        
        # Extrapolate to 0 and W / H limits
        x_min = x_left - (30.0 * x_raw_per_px)
        x_max = x_right + (30.0 * x_raw_per_px)
        y_min = y_top - (30.0 * y_raw_per_px)
        y_max = y_bottom + (30.0 * y_raw_per_px)
        
        # 4. Inversion Flags calculation
        invert_x = False
        invert_y = False
        
        if x_min > x_max:
            x_min, x_max = x_max, x_min
            invert_x = True
            
        if y_min > y_max:
            y_min, y_max = y_max, y_min
            invert_y = True
            
        # Convert to integers for JSON compatibility
        calib_data = {
            "X_MIN": int(round(x_min)),
            "X_MAX": int(round(x_max)),
            "Y_MIN": int(round(y_min)),
            "Y_MAX": int(round(y_max)),
            "SWAP_XY": swap_xy,
            "INVERT_X": invert_x,
            "INVERT_Y": invert_y
        }
        
        print(f"[CALIB] Final calculated parameters: {calib_data}")
        
        # Save to file
        calib_file = "touch_calibration.json"
        try:
            with open(calib_file, "w", encoding="utf-8") as f:
                json.dump(calib_data, f, indent=4)
            print(f"[CALIB] Parameters successfully saved to '{calib_file}'")
            
            # Show completed splash screen
            self._draw_screen(
                "CALIBRATION COMPLETE!", 
                f"บันทึกค่าลง {calib_file} เรียบร้อยแล้ว! กรุณารันโปรแกรมหลักใหม่", 
                target_pos=None
            )
            time.sleep(3.0)
        except Exception as e:
            print(f"[ERROR] Failed to save calibration file: {e}")
            self._draw_screen("SAVE FAILED!", f"เกิดข้อผิดพลาดในการบันทึก: {e}", target_pos=None)
            time.sleep(3.0)

def main():
    print("=========================================")
    print("    Jamming Detector - Screen Calibrator ")
    print("=========================================")
    calibrator = TouchCalibrator()
    calibrator.run_calibration()
    print("[SYSTEM] Calibrator program finished successfully.")

if __name__ == "__main__":
    main()
