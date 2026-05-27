# GUNJAM — Senior Code Review
**Reviewer:** Claude (Anthropic)  
**Date:** 27 May 2026  
**Scope:** Full source review — `main.py`, `detector.py`, `config.py`, `dsp.py`, `database_manager.py`, `display_ui.py`, `web_server.py`, `buzzer.py`, `led_control.py`, `calibrate_touch.py`, `test_sensors.py`, `generate_previews.py`, `hardware/mpu6050.py`, `hardware/rtc_ds3231.py`, `web/index.html`, `web/script.js`, `web/style.css`

---

## 1. ภาพรวมสถาปัตยกรรม (Architecture Overview)

โปรเจกต์มีโครงสร้างที่ **อ่านออกและเข้าใจได้เร็ว** — แยก concern ออกเป็นโมดูลต่าง ๆ ได้ดีในระดับหนึ่ง:

```
main.py  ──►  detector.py (God Class)
                 ├── dsp.py
                 ├── display_ui.py  ◄──── touch thread (daemon)
                 ├── web_server.py  ◄──── Flask thread (daemon)
                 ├── database_manager.py
                 ├── buzzer.py      ◄──── buzzer thread (daemon)
                 ├── led_control.py
                 └── hardware/
                        ├── mpu6050.py
                        └── rtc_ds3231.py
```

**จุดแข็ง:** module ย่อยแต่ละตัว (buzzer, led, dsp) ทำหน้าที่ชัดเจน  
**จุดอ่อนหลัก:** `GPSJammerHandheld` ใน `detector.py` เป็น **God Class** ที่รู้เรื่องทุกอย่าง — เก็บ state ของ SDR, ของ IMU, ของ UI, ของ database, ของ web server ไว้หมด มีหน้าที่มากเกินไป ถ้าโปรเจกต์โตขึ้นจะแก้ยาก

อีกปัญหาหนึ่งคือ **ไม่มี unit test เลยแม้แต่ไฟล์เดียว** (test_sensors.py เป็น manual sensor test ไม่ใช่ automated test) — สำหรับโปรเจกต์ที่ใช้ตรวจจับสัญญาณแจมในโลกจริง ความมั่นใจว่าโค้ด logic ถูกต้องควรมากกว่านี้

---

## 2. คุณภาพโค้ด (Code Quality)

### 2.1 ปัญหา Thread Safety — อันตรายที่สุด

นี่คือปัญหาที่ร้ายแรงที่สุดในโค้ดทั้งหมด ระบบนี้มี **อย่างน้อย 4 threads** ทำงานพร้อมกัน:
- Main loop (อ่าน SDR, detect, วาด UI)
- Touch worker thread (`_touch_worker` ใน `display_ui.py`)
- Flask/werkzeug thread (`web_server.py`)
- Buzzer worker thread (`buzzer.py`)

**ปัญหาที่ 1: `_touch_zones` ถูก write จาก main thread และ read จาก touch thread พร้อมกัน โดยไม่มี lock**

```python
# display_ui.py — main thread เขียน dict นี้ทุก frame
self._touch_zones[label] = (bx, foot_t, bx + btn_w, H)

# display_ui.py — touch thread อ่าน dict นี้พร้อมกัน
for label, (x1, y1, x2, y2) in self._touch_zones.items():
```
Dict iteration ใน Python ไม่ thread-safe ถ้า dict ถูก modify ระหว่าง iterate จะ raise `RuntimeError: dictionary changed size during iteration` ที่แก้ยากมากเพราะเกิดแบบ race condition

**ปัญหาที่ 2: `ServerState` ใน `web_server.py` ไม่มี lock เลย**

```python
class ServerState:
    metrics = {}          # class-level! ไม่ใช่ instance-level
    power_spectrum = []
    uptime = 0
```
- `metrics` และ `power_spectrum` ถูก assign ใหม่จาก main thread ทุก 100ms
- Flask thread อ่านค่าพวกนี้เพื่อ serialize JSON พร้อมกัน
- ยิ่งไปกว่านั้น เป็น **class attribute** ไม่ใช่ instance attribute — ถ้ามีหลาย instance จะ share state กัน (แม้ตอนนี้จะมีแค่ตัวเดียว)

**ปัญหาที่ 3: `request_calibration`, `shutdown_requested`, `reboot_requested` ถูก set จาก touch thread และ read จาก main thread โดยไม่มี lock หรือ `threading.Event`**

**วิธีแก้:** ใช้ `threading.Lock()` หรือ `threading.Event()` สำหรับ flags และ `threading.RLock()` guard รอบ `_touch_zones`

### 2.2 `reboot_requested` ไม่ได้ initialize ใน `__init__`

```python
# detector.py — ไม่มีบรรทัดนี้ใน __init__!
# self.reboot_requested = False  ← หายไป

# แต่ใน run() เช็คผ่าน getattr แบบนี้
if getattr(self, 'reboot_requested', False):
```
เหตุผลที่ใช้ `getattr` defensive coding แบบนี้ คือปิดบังว่า attribute ถูกลืมใส่ใน `__init__` แทนที่จะแก้ให้ถูกต้อง ควรใส่ใน `__init__` ตรง ๆ

### 2.3 Magic Numbers กระจายอยู่ทั่วไป

`-89.9` ปรากฏใน **4 ที่** ที่ต่างกัน:
- `detector.py` line 47 (`calibrated_base_nf`)
- `detector.py` line 90 (preview mode)
- `detector.py` line 149 (`fixed_nf` branch)
- `detector.py` line 206 (fixed mode force)

ค่านี้ควรอยู่ใน `config.py` เป็น `DEFAULT_NOISE_FLOOR = -89.9` ที่เดียว

ค่า hardcode อื่น ๆ ที่ควรอยู่ใน config:
- `8.0` และ `5.0` (baseline guard thresholds ใน `_detect_jamming`)
- `480` และ `320` (screen dimensions — ปรากฏใน `detector.py`, `calibrate_touch.py`, `display_ui.py`)
- `24000000` (SPI clock speed)
- `1575.42e6` (center frequency — อยู่ใน config แต่ detector.py hardcode ซ้ำใน `__init__`)

### 2.4 Late Imports กระจัดกระจาย

```python
# detector.py — import อยู่ใน while loop ทุก iteration!
while self.running:
    try:
        if not self.preview:
            try:
                import sys          # ← ควรอยู่ข้างบนสุดของไฟล์
                if sys.platform == "win32":
                    import msvcrt   # ← ไม่มีปัญหาเรื่อง speed (cached) แต่อ่านยากมาก
```

`import sys` อยู่ข้างบนสุดของ `detector.py` อยู่แล้ว (line 1) แล้วยัง import ซ้ำข้างในลูปอีก

```python
# safe_power_off และ safe_reboot — import os, import subprocess, import sys
# ทั้งหมดนี้ควรอยู่ด้านบนไฟล์ตามมาตรฐาน PEP 8
```

### 2.5 `database_manager.py` — import ซ้ำและ signature ไม่ตรง

```python
import time  # line 4
...
import time  # line 84 — ซ้ำ! ลืมตรวจสอบ
```

Test call ด้านล่างไฟล์ signature ไม่ตรงกับ function จริง:
```python
# line 141 — เรียกแค่ 4 args
log_event("TEST", 50, -20.5, 5.2)

# แต่ function จริงต้องการ 7 args
def log_event(state, score, peak_p, floor_rise, noise_floor, uptime_sec, bearing_deg=0):
```
ถ้ารัน test block นี้จะ crash ทันที

### 2.6 Bare `except` ปิดบัง Error จริง

```python
# display_ui.py line 833
except: pass  # ← อะไรก็ได้ pass หมด

# display_ui.py line 906
except: time.sleep(1)  # ← touch thread ตายเงียบ ๆ

# calibrate_touch.py line 42
except Exception:
    pass  # ← ถ้า bus.close() fail ไม่รู้เลย
```

Bare `except:` จะจับแม้กระทั่ง `SystemExit`, `KeyboardInterrupt`, `MemoryError` ซึ่งไม่ควรถูก catch อย่างน้อยควรใช้ `except Exception:` และ log ด้วย

### 2.7 `display_ui.py` — coupling ที่ผิดปกติ

`DisplayUI._get_text_size` เข้าถึง `self.app._draw` แทนที่จะรับ `draw` parameter ที่ถูกส่งมาอยู่แล้ว:
```python
def _get_text_size(self, text, font):
    draw = self.app._draw  # ← ดึงจาก app — tight coupling
```
ทั้ง ๆ ที่ method นี้ถูกเรียกจากทุกที่ที่มี `draw` object อยู่แล้ว

### 2.8 `generate_previews.py` — ปลอม state แล้วไม่ restore

```python
# บังคับ state แล้ว detect ซ้ำ — ทำให้ noise floor เปลี่ยน
app.jammer_active = True
metrics = app._detect_jamming(power)  # ← side effect: เปลี่ยน noise_floor!
metrics["state"] = "JAMMING"          # ← override อีกที แต่ side effect ยังอยู่
```
`_detect_jamming` มี side effect ด้านใน (update `noise_floor`, `jammer_active`, `current_state`) แต่ generate_previews.py ไม่รู้เรื่องนี้

---

## 3. ความน่าเชื่อถือ / Reliability

### 3.1 Database — Path สัมพัทธ์ที่ไม่น่าไว้ใจ

```python
DB_NAME = "jamming_events.db"  # relative path!
```
ถ้า `systemd` รัน service จาก directory อื่น (เช่น `/`) ไฟล์ DB จะถูกสร้างผิดที่ และข้อมูลก่อนหน้าจะหาไม่เจอ ควรใช้ path เต็ม:
```python
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jamming_events.db")
```

### 3.2 Timestamp Format ไม่ใช่ ISO 8601

```python
local_time = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
# ผลลัพธ์: "27/05/2026 14:30:00"
```
- ไม่ sort ตามลำดับเวลาเมื่อเรียงแบบ string
- `get_filtered_history` ต้องใช้ `time.strptime` parse กลับ — เสี่ยง crash ถ้า format เปลี่ยน
- Excel/CSV ไม่ parse format นี้โดยอัตโนมัติ
- ควรใช้ ISO 8601: `'%Y-%m-%dT%H:%M:%S'`

### 3.3 `_calibrate()` ถูก call ระหว่าง main loop โดยไม่ lock SDR

```python
# detector.py run() — main loop
if getattr(self, 'request_calibration', False):
    self.ui.draw_ui(metrics, power)
    self._calibrate()  # ← อ่าน 30 samples จาก SDR
    ...
```
`_calibrate` เรียก `self.sdr.read_samples()` โดยตรง ถ้ามี race condition จาก thread อื่น (เช่น Flask thread เรียก endpoint ที่ trigger calibration) จะมีปัญหา

### 3.4 `safe_power_off` ลอง command หลายตัวแล้วไม่รู้ว่าตัวไหนสำเร็จ

```python
for cmd in try_cmds:
    res = subprocess.run(cmd, timeout=8, capture_output=True, text=True)
    # ← ไม่ break เมื่อ poweroff สำเร็จ! รัน sudo poweroff แล้วยัง run ต่ออีก 3 ตัว
```
ถ้า `sudo poweroff` ทำงานสำเร็จ ระบบกำลัง shutdown แต่โค้ดยังวน loop ต่อไปอีก 3 commands — อาจก่อให้เกิด side effect แปลก ๆ

### 3.5 `_touch_worker` ไม่มี stop mechanism ที่ชัดเจน

```python
def _touch_worker(self):
    self._load_touch_calibration()
    while True:  # ← วนตลอด ไม่มี self._running flag
        try:
            ...
        except: time.sleep(1)
```
Thread นี้หยุดได้แค่ตาย process แม้จะ `daemon=True` แต่ถ้า cleanup ต้องการหยุด touch thread ก่อนก็ทำไม่ได้

### 3.6 `MPU6050.calibrate()` ไม่มี timeout

```python
for _ in range(samples):
    val = self.read_raw_data(addr)
    if val is not None:
        sum_z += val
        valid_count += 1
    time.sleep(0.01)
```
ถ้า I2C อยู่ในสภาพที่ return `None` ตลอด จะรอจน valid_count = 0 และ print "Calibration FAILED" — แต่ไม่ raise exception ทำให้ main loop ดำเนินต่อโดยใช้ offset = 0 ซึ่งอาจทำให้ bearing เลื่อนไปเรื่อย ๆ

---

## 4. Performance

### 4.1 Database — เปิด/ปิด Connection ทุก call

```python
def log_event(...):
    conn = sqlite3.connect(DB_NAME)  # เปิด connection ใหม่
    ...
    conn.close()  # ปิด
```
บน Raspberry Pi Zero 2W ที่ SD card ช้า การ open/close SQLite connection ทุกครั้งที่ log (ทุก 1-30 วินาที) มีค่าใช้จ่ายที่วัดได้ ควรใช้ connection pool อย่างง่าย ๆ หรือ WAL mode:
```python
conn = sqlite3.connect(DB_NAME)
conn.execute("PRAGMA journal_mode=WAL")
```

### 4.2 Buzzer สร้าง `PWM` object ใหม่ทุกครั้งที่ buzz

```python
def _buzz(self, duration_s, frequency_hz=1200, duty_cycle=50):
    self.pwm = self.gpio.PWM(self.buzzer_pin, frequency_hz)  # ← สร้างใหม่ทุกครั้ง
    self.pwm.start(duty_cycle)
    time.sleep(duration_s)
    ...
    self.pwm.stop()
```
`RPi.GPIO.PWM` ควร create ครั้งเดียวแล้วเรียก `ChangeDutyCycle` / `ChangeFrequency` ตามต้องการ การสร้างใหม่ทุกครั้งมี overhead และอาจทำให้ GPIO glitch

### 4.3 Particle System บน Web Dashboard — O(n²)

```javascript
// script.js line 581-595
for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
        const dist = Math.sqrt(dx * dx + dy * dy);
        // ...
    }
}
```
65 particles = 65×64/2 = **2,080 distance calculations ทุก animation frame (~60fps)** = ~124,800 ops/sec บนมือถือหรือ browser ที่เปิดบน Pi Zero อาจทำให้ UI กระตุก ควรลด `PARTICLE_COUNT` หรือใช้ spatial hashing

### 4.4 Waterfall ใช้ `fillRect` ทีละ cell

```javascript
// script.js — 40 bins × 60 rows = 2,400 fillRect calls ต่อ render
for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
        ctx.fillStyle = wfColor(spectrum[c]);
        ctx.fillRect(c * colW, y, ...);
    }
}
```
`fillStyle` assignment ทุก iteration แพงมาก ควรใช้ `ImageData` / `putImageData` แทน ซึ่งเร็วกว่า 10-50x

### 4.5 Flask Development Server ใน Production

```python
# web_server.py
thread = threading.Thread(
    target=app.run,
    kwargs={"host": "0.0.0.0", "port": port, "debug": False, "use_reloader": False},
    daemon=True
)
```
Flask dev server (`app.run`) **ไม่ได้ออกแบบมาสำหรับ production** — single-threaded, ไม่มี request queuing, ไม่มี keepalive ที่ดี ควรใช้ `waitress` หรือ `gunicorn` แทน:
```python
# pip install waitress
from waitress import serve
serve(app, host="0.0.0.0", port=8080)
```

### 4.6 Spectrum FFT บน Pi Zero 2W

`np.fft.fft(8192 samples)` ทุก frame ที่ 10 FPS = 10 FFTs/sec บน Pi Zero 2W (ARM Cortex-A53) ไม่มี hardware FFT acceleration numpy ใช้ FFTPACK ซึ่งช้ากว่า FFTW การลอง `scipy.fft` หรือ `pyfftw` อาจช่วยได้มากถ้า CPU เป็น bottleneck

---

## 5. Security

### 5.1 Web Dashboard ไม่มี Authentication เลย

```python
@app.route('/api/clear', methods=['POST'])
def clear_history():
    success = database_manager.clear_db()
    return jsonify({"success": success})
```
ใครก็ตามที่อยู่บน network เดียวกัน (หรือถ้า Pi ต่อ internet) สามารถ:
- ดู live RF spectrum: `GET /api/status`
- Export ข้อมูลทั้งหมด: `GET /api/export`
- **ลบ database ทั้งหมด: `POST /api/clear`** ← ไม่ดีมาก

ควรเพิ่ม API key หรือ basic auth อย่างน้อย และ rate limit `/api/clear`

### 5.2 XSS ใน Log Table

```javascript
// script.js line 444-453
html += `<tr>
    <td>${time}</td>
    <td><span class="state-pill" data-state="${row.state}">${row.state}</span></td>
    ...
</tr>`;
tbody.innerHTML = html;
```
`row.state` มาจาก database โดยตรง ถ้า database ถูก inject ค่าแปลก ๆ (เช่น `<script>alert(1)</script>`) จะ execute ได้ ควรใช้ `textContent` หรือ escape HTML ก่อน:
```javascript
function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
```

### 5.3 `sudo poweroff` ต้องการ passwordless sudo

```python
try_cmds = [
    ["sudo", "poweroff"],
    ["sudo", "systemctl", "poweroff"],
    ...
]
```
Pi ต้องมี `/etc/sudoers` ที่อนุญาต user รัน poweroff โดยไม่ต้องใส่ password นี่คือ security tradeoff ที่ควร document ไว้ชัด ๆ และ limit ให้ specific commands เท่านั้น ไม่ใช่ `ALL=(ALL) NOPASSWD: ALL`

### 5.4 Touch Calibration ไม่ validate input

```python
# calibrate_touch.py — บันทึก JSON โดยตรงโดยไม่ validate range
calib_data = {
    "X_MIN": int(round(x_min)),
    "X_MAX": int(round(x_max)),
    ...
}
with open(calib_file, "w", encoding="utf-8") as f:
    json.dump(calib_data, f, indent=4)
```
ถ้า calibration data เสียหาย (เช่น X_MIN = X_MAX = 0) จะทำให้ touch พัง หรือหาร 0 ใน `_touch_worker` ซึ่งมีการป้องกันอยู่บ้างแต่ไม่ครบ

---

## 6. สิ่งที่ทำได้ดี (Commendations)

**Adaptive Noise Floor Algorithm** (`_detect_jamming`) ออกแบบมาดีมาก — มี baseline guard ที่ป้องกัน jammer ดึง baseline ขึ้น, มี hit/clear frame debounce, มี WATCH state เป็น buffer ก่อน JAMMING ตรรกะพวกนี้แสดงให้เห็นว่าเข้าใจ domain จริง ๆ

**MPU6050 — Frozen Sensor Recovery** โค้ดตรวจจับ sensor stuck และ reinit อัตโนมัติ เป็นการป้องกัน hardware fault ที่ดีมากสำหรับ embedded system:
```python
if raw_z == self.last_raw_z and raw_z != 0:
    self.frozen_count += 1
    if self.frozen_count > 40:
        self._init_sensor()
```

**Gyro Deadzone + Dynamic Drift Compensation** ใน `update_bearing`:
```python
if abs(gyro_rate) < 2.0:
    self.gyro_z_offset = (self.gyro_z_offset * 0.99) + (raw_z * 0.01)
```
เป็น adaptive calibration แบบง่ายที่ใช้ได้จริงในสนาม

**Touch Calibration Tool** (`calibrate_touch.py`) เป็น standalone utility ที่สมบูรณ์ — 4-point calibration, median filtering, axis swap/invert detection — professional-grade

**Preview Mode** สำหรับ UI development โดยไม่ต้องใช้ hardware จริง ช่วยให้ทดสอบ UI ได้บน PC — ความคิดดีมาก

**Database Pruning** ป้องกัน SD card wear เกินไป:
```python
DELETE FROM events WHERE state != 'STARTUP' AND id NOT IN (
    SELECT id FROM events WHERE state != 'STARTUP' ORDER BY id DESC LIMIT 1000
)
```

**Web Dashboard CSS** ออกแบบดีมาก — design tokens ชัดเจน, dark/light theme ครบ, responsive breakpoints ครบทุกขนาด, animation smooth ไม่รกตา

**`_spi_lock` ใน `display_ui.py`** ใช้ lock ป้องกัน SPI bus conflict ระหว่าง display และ touch controller ถูกต้อง

**`generate_previews.py`** ช่วย generate screenshot ทุก view mode เป็น documentation ที่มีชีวิต

**Schema Migration** ใน `database_manager.init_db()` ตรวจสอบ column ที่หายไปแล้ว ALTER TABLE ให้ compatibility — ดีมากสำหรับ deployed device ที่ update ได้ยาก

---

## 7. สิ่งที่ควรแก้ไขด่วน (Priority Fixes)

### 🔴 Priority 1 — Critical (แก้ก่อนใช้งาน production)

**[P1-1] Thread Safety: ใส่ Lock รอบ `_touch_zones` และ state flags**
```python
# detector.py __init__
self._state_lock = threading.Lock()
self.request_calibration = False
self.shutdown_requested = False
self.reboot_requested = False  # ← เพิ่ม initialize ที่หายไป!

# display_ui.py
self._zones_lock = threading.RLock()

# ทุกที่ที่ read/write _touch_zones ให้ใช้ with self._zones_lock:
```

**[P1-2] Thread Safety: `ServerState` ต้องมี Lock และเป็น instance attribute**
```python
class ServerState:
    def __init__(self):
        self._lock = threading.Lock()
        self.metrics = {}
        self.power_spectrum = []
        self.uptime = 0

    def update(self, metrics, power, uptime, bearing=0, gain=7.7):
        with self._lock:
            self.metrics = metrics
            ...

    def snapshot(self):
        with self._lock:
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
```

**[P1-3] Database: ใช้ absolute path สำหรับ DB_NAME**
```python
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jamming_events.db")
```

**[P1-4] Database: แก้ timestamp เป็น ISO 8601**
```python
local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
```
(ต้อง update `get_filtered_history` ให้ใช้ format ใหม่ด้วย)

---

### 🟠 Priority 2 — High (แก้ก่อน submit หรือ deploy จริง)

**[P2-1] เพิ่ม API Authentication** อย่างน้อย environment variable-based token:
```python
API_TOKEN = os.environ.get('GUNJAM_API_TOKEN', '')
# ถ้า token ตั้งไว้ ให้เช็คทุก request ที่ไม่ใช่ static file
```

**[P2-2] แก้ XSS ใน log table** ให้ escape HTML ก่อน inject ลง innerHTML

**[P2-3] เอา magic number `-89.9` เข้า config.py** เป็น `DEFAULT_NOISE_FLOOR_DB`

**[P2-4] แก้ `log_event` test call** ที่ signature ไม่ตรง ที่ท้าย `database_manager.py`

**[P2-5] แก้ `safe_power_off` ให้ break หลังจาก poweroff สำเร็จ**
```python
for cmd in try_cmds:
    res = subprocess.run(cmd, ...)
    if res.returncode == 0:
        break  # ← เพิ่มตรงนี้
```

---

### 🟡 Priority 3 — Medium (ปรับปรุงคุณภาพ)

**[P3-1] เปลี่ยน Flask dev server เป็น `waitress`**
```bash
pip install waitress
```
```python
from waitress import serve
serve(app, host="0.0.0.0", port=8080, threads=2)
```

**[P3-2] เปลี่ยน `RPi.GPIO.PWM` ใน `buzzer.py` ให้ create ครั้งเดียว**

**[P3-3] ย้าย import ทั้งหมดขึ้นไปด้านบนไฟล์** ตาม PEP 8

**[P3-4] ลบ duplicate `import time`** ใน `database_manager.py`

**[P3-5] เพิ่ม `self.running` flag ให้ `_touch_worker`** เพื่อ stop gracefully ตอน cleanup

**[P3-6] Waterfall: เปลี่ยนไปใช้ `ImageData`** แทน 2,400 fillRect calls

**[P3-7] ลด Particle count หรือ ปิด Particle บน mobile** สำหรับ performance

---

## สรุปภาพรวม

| หมวด | คะแนน | หมายเหตุ |
|------|--------|----------|
| สถาปัตยกรรม | 6/10 | God Class แต่ module แยกดี |
| คุณภาพโค้ด | 6/10 | Magic numbers, late imports, duplicate code |
| Reliability | 5/10 | **Thread safety เป็นปัญหาหลัก** |
| Performance | 7/10 | ดีในส่วน Python, JS ยังพัฒนาได้ |
| Security | 4/10 | ไม่มี auth, XSS potential |
| Domain Logic | 9/10 | RF detection algorithm ดีมาก |
| UI/UX | 8/10 | Dashboard สวยงาม, ใช้งานได้จริง |

**โปรเจกต์นี้มีพื้นฐาน domain knowledge ดีมาก** — อัลกอริทึมตรวจจับสัญญาณ, adaptive baseline, hardware recovery พวกนี้แสดงว่าเข้าใจปัญหาจริง สิ่งที่ต้องปรับหลักคือ **thread safety** ซึ่งถ้าปล่อยไว้จะทำให้เกิด crash แบบ intermittent ที่ reproduce ยากมากในสนาม แก้ตาม P1 ก่อนแล้วค่อยทำ P2-P3 ตามลำดับ
