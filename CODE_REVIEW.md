# Code Review — GUNJAM Handheld GNSS Jamming Detector

**ผู้ review:** Senior Software Engineer  
**วันที่:** 27 พฤษภาคม 2569  
**สโคป:** ทุกไฟล์ใน codebase — `main.py`, `detector.py`, `config.py`, `dsp.py`, `database_manager.py`, `display_ui.py`, `web_server.py`, `buzzer.py`, `led_control.py`, `calibrate_touch.py`, `test_sensors.py`, `generate_previews.py`, `hardware/mpu6050.py`, `hardware/rtc_ds3231.py`, `web/index.html`, `web/script.js`

---

## 1. ภาพรวมสถาปัตยกรรม

ระบบแบ่งเป็น 3 ชั้นหลักที่เห็นได้ชัด:

- **Signal Processing Layer** — `dsp.py` + `detector.py` (main loop)
- **Presentation Layer** — `display_ui.py` (LCD) + `web_server.py` + `web/`
- **Hardware Abstraction Layer** — `hardware/mpu6050.py`, `hardware/rtc_ds3231.py`, `buzzer.py`, `led_control.py`

**ภาพรวมที่ดี:** การแยก DSP utilities ออกไปใน `dsp.py` สะอาด, web server ทำงานบน daemon thread แยกจาก main loop, buzzer/LED ใช้ threading + queue อย่างถูกต้อง

**ปัญหาหลักด้านสถาปัตยกรรม:** `GPSJammerHandheld` ใน `detector.py` เป็น God Class — รับผิดชอบ SDR I/O, DSP, state machine, database logging, keyboard handling, shutdown sequence และ process management ในคลาสเดียว ไม่มี separation of concerns ที่ชัดเจน เมื่อโปรเจกต์ขยายต่อจะ maintain ยาก

ปัญหาสำคัญอีกอย่าง: `DisplayUI` ถือ reference ถึง `app` object แบบ bidirectional — `app.ui` ชี้ไปที่ `DisplayUI`, และ `DisplayUI.app` ชี้กลับมาที่ `app` สร้าง tight coupling ที่ทำให้ทดสอบแยกไม่ได้เลย นอกจากนี้ `DisplayUI` ยังเขียน attribute `_img` และ `_draw` ทับลงบน `app` object โดยตรง (`self.app._img`, `self.app._draw`) ซึ่งผิดหลัก OOP อย่างมาก — state ของ display ควรอยู่ใน `DisplayUI` เอง ไม่ใช่ inject กลับไปที่ parent

---

## 2. คุณภาพโค้ด

### 2.1 ความไม่สม่ำเสมอในการเข้าถึง config

`detector.py` ผสม pattern การเรียก config อย่างไม่สม่ำเสมอ:

```python
# บรรทัด 26: เรียกตรงๆ
self.sample_rate_hz = config.SAMPLE_RATE

# บรรทัด 40: ใช้ getattr กับ fallback
self.hit_frames_required = getattr(config, 'HIT_FRAMES', 3)
```

ค่า `HIT_FRAMES = 3` และ `CLEAR_FRAMES = 10` มีอยู่ใน `config.py` บรรทัด 27-28 เรียบร้อยแล้ว แต่ใช้ `getattr()` กับ fallback ราวกับกลัวว่า key จะไม่มี ควรเลือก pattern เดียว ถ้า config พัง ให้พังเร็วๆ ตั้งแต่ start ดีกว่า silent fallback ที่ debug ยาก

นอกจากนี้ `detector.py` ยังประกาศ `self.sample_count = 8192` บรรทัด 23 ซ้ำกับ `config.SAMPLE_COUNT = 8192` ทั้งที่บรรทัดถัดไป (26) ก็เรียก `config.SAMPLE_RATE` โดยตรงอยู่แล้ว ควรใช้ `config.SAMPLE_COUNT` แทน magic number

### 2.2 โค้ดซ้ำ: Keyboard Input Handler

`detector.py` บรรทัด 263–308 เป็น if/else สำหรับ Windows vs Unix โดยมีบล็อก `if line == 'v': ... elif line == 'm': ...` เหมือนกันทุกตัวอักษร ซ้ำกัน ~25 บรรทัด ควร extract เป็น method เดียว:

```python
def _handle_keyboard_input(self, line):
    if line == 'v':
        self.ui.toggle_view_mode()
    elif line == 'm':
        self.toggle_mute()
    # ...
```

แล้วให้ Windows/Unix branch เรียก `self._handle_keyboard_input(line)` แทน

### 2.3 Comment ภาษาไทยโดดๆ ใน codebase ที่เขียน English

`detector.py` บรรทัด 551:
```python
# อันนี้เพิ่มมาไว้ทดสอบโหมดพรีวิวโดยไม่ต้องใช้ฮาร์ดแวร์จริง
def _generate_preview_samples(self):
```
Comment ภาษาไทยตัวเดียวในไฟล์ที่เหลือทั้งหมดเป็น English ดูแปลกตา ควรเลือก convention เดียว (แนะนำ English เพื่อ maintainability ระยะยาว)

### 2.4 Hard-code ขนาดหน้าจอใน _touch_worker

`display_ui.py` บรรทัด 891-892:
```python
sx = (x_raw - x_min) * 480.0 / dx
sy = (y_raw - y_min) * 320.0 / dy
```
ตัวเลข `480.0` และ `320.0` ควรใช้ `self.app.w` และ `self.app.h` แทน ซึ่งถูกนิยามไว้แล้วใน `detector.py` บรรทัด 21-22

### 2.5 Placeholder ในโค้ด Production

`detector.py` บรรทัด 424-426:
```python
database_manager.log_event(
    "MANUAL_SNAP",
    99,
    -50.0, # Dummy peak or use real metrics  ← placeholder
```
Comment นี้บอกชัดว่าไม่ได้ใช้ข้อมูลจริง ขัดกับกฎใน `agent.md` ที่ระบุ "ห้ามใช้ Placeholder" `manual_capture()` ถูกเรียกจาก main loop ซึ่งมี `metrics` object อยู่แล้ว ควรเก็บ `self.last_metrics` ไว้แล้วส่งค่าจริงแทน

### 2.6 getattr() กับ field ที่มีอยู่แล้วใน \_\_init\_\_

`detector.py` บรรทัด 188, 195, 201, 202:
```python
if not getattr(self, 'baseline_guard_active', False):
```
`baseline_guard_active` ถูก initialize ใน `__init__` บรรทัด 49 อยู่แล้ว การใช้ `getattr()` กับ fallback ที่นี่ไม่จำเป็น และทำให้โค้ดอ่านยากโดยไม่มีเหตุผล ใช้ `self.baseline_guard_active` ตรงๆ ได้เลย

### 2.7 generate\_previews.py: เขียนแล้วอ่านกลับมาโดยไม่จำเป็น

`generate_previews.py` บรรทัด 62:
```python
app.ui.draw_ui(metrics, power)
Image.open("preview.png").save(os.path.join(out_dir, "mode_normal_clean.png"))
```
`draw_ui()` ใน preview mode save ลง `preview.png` ก่อน แล้วโค้ดนี้เปิดไฟล์นั้นขึ้นมาอีกครั้งเพื่อ save ใหม่ — เสีย disk I/O สองรอบ ควรบันทึกโดยตรงจาก `app._img`:
```python
app.ui.draw_ui(metrics, power)
app._img.save(os.path.join(out_dir, "mode_normal_clean.png"))
```

---

## 3. Reliability / Error Handling

### 3.1 SQLite ไม่ได้เปิด WAL Mode — อันตรายมาก

`database_manager.py` ไม่เคย set `PRAGMA journal_mode=WAL` เลย default mode ของ SQLite คือ DELETE (rollback journal) ซึ่งมีปัญหาใหญ่: main loop และ web server thread อ่าน/เขียน database พร้อมกัน ใน DELETE mode การเขียนจะ lock ทั้ง database ทำให้ `get_history()` จาก web request อาจ block หรือ throw `OperationalError: database is locked` ได้ บน Pi Zero ที่ใช้ SD card ช้าปัญหานี้ยิ่งเห็นชัด

แก้ง่ายมาก เพิ่มใน `init_db()` หลัง connect:
```python
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
```

### 3.2 Calibration ขณะมี Jammer แต่ไม่แจ้ง User บน LCD

`detector.py` `_calibrate()` บรรทัด 143-145:
```python
if (nf_max - nf_min) > 5.0:
    print("[WARN]  Wide NF range detected - possible jammer during calibration")
    print("[WARN]  Recommend restarting without jammer nearby")
```
Warning พิมพ์ลง terminal เฉยๆ แต่ไม่แสดงบน LCD ซึ่ง operator ในสนามไม่ได้เห็น ถ้า calibrate ขณะมี jammer ค่า `self.noise_floor` จะสูงกว่าความจริง ทำให้ detector blind ทันที ควรอย่างน้อย `self.ui.show_toast("WARN: NOISY CALIB", 3.0)` ด้วย

### 3.3 \_calibrate() เรียกบน Main Loop Thread — Block นานถึง ~3 วินาที

`detector.py` บรรทัด 311-316 เรียก `self._calibrate()` ตรงในลูป:
```python
if self.request_calibration:
    self.ui.draw_ui(metrics, power)
    self._calibrate()  # อ่าน SDR 30 รอบ!
```
`_calibrate()` วน 30 รอบอ่าน SDR ซึ่งใช้เวลา ~3 วินาที ระหว่างนี้ main loop หยุดทั้งหมด — touch input ไม่ตอบสนอง, web server ไม่ได้รับ metrics ใหม่ ควรทำใน background thread หรืออย่างน้อย yield ให้ UI refresh ระหว่าง warmup samples

### 3.4 Exception Swallowing ใน Main Loop ไม่มี SDR Recovery

`detector.py` บรรทัด 374-378:
```python
except Exception as exc:
    import traceback
    print(f"[ERROR] Runtime loop: {exc}")
    traceback.print_exc()
    time.sleep(0.2)
```
ถ้า `self.sdr.read_samples()` throw exception เพราะ USB disconnect ระบบจะวน loop ต่อไปเรื่อยๆ โดยพิมพ์ error ซ้ำทุก 0.2 วินาที ควรมี consecutive error counter และถ้า error เกิน N ครั้งติดกัน ให้ attempt SDR re-init หรือ trigger `self.reboot_requested = True`

### 3.5 DS3231 (RTC) — Dead Code ที่ไม่มีใคร Import

`hardware/rtc_ds3231.py` มีโค้ดครบ แต่ตรวจสอบทุกไฟล์แล้วไม่มี `import DS3231` ที่ไหนเลย `test_sensors.py` บรรทัด 12 comment ว่า "RTC is handled by Kernel now" หมายความว่าไฟล์นี้เป็น dead code ควร document ในไฟล์นั้นเองว่า "ไม่ใช้งานในเวอร์ชันปัจจุบัน" หรือลบออกเพื่อไม่ให้คน maintain งงว่า import ที่ไหน

### 3.6 MPU6050 Frozen Detection: Edge Case ที่ Raw = 0

`hardware/mpu6050.py` บรรทัด 110:
```python
if raw_z == self.last_raw_z and raw_z != 0:
    self.frozen_count += 1
```
เงื่อนไข `raw_z != 0` หมายความว่าถ้า sensor ค้างอยู่ที่ค่า 0 จะไม่ detect ว่า frozen ในทางปฏิบัติ offset drift ทำให้ค่า 0 แท้ๆ หายากมาก แต่ควรมี comment อธิบายเจตนาไว้

### 3.7 Buzzer Worker: Queue Draining มี TOCTOU Race เล็กน้อย

`buzzer.py` บรรทัด 74-79:
```python
while not self._queue.empty():
    try:
        self._queue.get_nowait()
        self._queue.task_done()
    except queue.Empty:
        break
```
มี TOCTOU race ระหว่าง `.empty()` check กับ `get_nowait()` — สามารถเกิดได้ในทางทฤษฎีแม้ในทางปฏิบัติจะไม่ crash เพราะมีแค่ consumer เดียว ควรลบ `.empty()` check ออกแล้วใช้ `get_nowait()` + catch `Empty` อย่างเดียว:
```python
while True:
    try:
        self._queue.get_nowait()
        self._queue.task_done()
    except queue.Empty:
        break
```

---

## 4. Performance

### 4.1 Database: เปิด-ปิด Connection ทุก Query

`database_manager.py` ทุก function (`log_event`, `get_history`, `get_filtered_history`, `clear_db`) ทำ `sqlite3.connect()` และ `conn.close()` ทุกครั้ง บน Pi Zero ที่ใช้ SD card filesystem open overhead นี้สะสมได้ โดยเฉพาะเมื่อ `get_history` ถูกเรียกจาก web server ทุก 5 วินาที

วิธีแก้ที่เหมาะสมสำหรับ embedded: ใช้ module-level connection พร้อม `check_same_thread=False` (ปลอดภัยเมื่อใช้ WAL mode) เพื่อลด open/close overhead

### 4.2 get\_filtered\_history: Python Loop แทนที่ควรเป็น SQL

`database_manager.py` บรรทัด 84-115: ดึงแถวมาทั้งหมด 5,000 แถว แล้ว parse timestamp ใน Python loop เพื่อ filter SCANNING ทุก 30 วินาที การ parse timestamp ใน Python ทุก call เปลืองทั้ง CPU และ memory ควร filter ใน SQL ด้วย subquery หรือ GROUP BY + MIN/MAX

### 4.3 Particle System ใน Web Dashboard ทำงาน 60 FPS ตลอดเวลา

`web/script.js` บรรทัด 567-621: `animateParticles()` ใช้ `requestAnimationFrame` วนทุก frame ตลอดชีวิต และมีการคำนวณ distance ระหว่าง particle ทุกคู่ O(n²) โดย n=65 ทุก frame — 2,080 sqrt calls ต่อ frame แม้ main dashboard ใช้ event-driven rendering อย่างชาญฉลาด แต่ particle system กลับ run 60 FPS เต็ม ควร pause เมื่อ tab ไม่ active:
```javascript
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) requestAnimationFrame(animateParticles);
});
```

### 4.4 Radar Draw: np.radians() เรียกซ้ำใน Render Loop ทุก Frame

`display_ui.py` `_draw_radar()`: เรียก `np.radians()` หลายสิบครั้งต่อ frame ภายใน for loop (tick marks 12 จุด, crosshairs 4 จุด, cardinal labels 8 จุด, bearing log lines สูงสุด 24 เส้น) ที่ FPS 10 บน Pi Zero Zero ส่วนนี้กินเวลา CPU พอสมควร สามารถ precompute lookup table `sin[angle] / cos[angle]` สำหรับ 0-359 ที่ init ได้

---

## 5. Security

### 5.1 Web Dashboard ไม่มี Authentication โดย Default

`web_server.py` บรรทัด 23:
```python
API_TOKEN = os.environ.get('GUNJAM_API_TOKEN', '')
```
บรรทัด 69-71:
```python
def check_auth():
    if not API_TOKEN:
        return  # ← skip auth ทั้งหมด
```
ถ้าไม่ set environment variable `GUNJAM_API_TOKEN` (ซึ่งไม่มีใน README หรือ startup script ที่ไหนเลย) ทุก endpoint รวมถึง `POST /api/clear` จะ public หมด ใครที่เชื่อมต่อกับ Wi-Fi Hotspot ของอุปกรณ์สามารถลบ database ทิ้งได้ทันที ควรอย่างน้อย warn อย่างชัดเจนขณะ startup:
```python
if not API_TOKEN:
    print("[WEB] WARNING: No API token set. Dashboard is OPEN to all connections.")
```
หรือ generate default token ใส่ใน startup log

### 5.2 `POST /api/clear` ไม่มี Destructive Action Guard เมื่อมี Token

`check_auth()` protect `/api/*` ทุก path ด้วย token เดียวกัน ไม่ได้แยก read-only กับ write endpoint ออกจากกัน ถ้า token หลุดออกไป ทุก operation รวมถึงการล้างข้อมูลสามารถทำได้ ควรพิจารณา require `{"confirm": true}` ใน POST body สำหรับ destructive operations

### 5.3 Web Dashboard โหลด Google Fonts จาก CDN

`web/index.html` บรรทัด 9-13 โหลด Inter, JetBrains Mono, Prompt จาก `fonts.googleapis.com` ซึ่งต้องการ internet connectivity อุปกรณ์นี้สร้าง Wi-Fi Hotspot ของตัวเอง ไม่มี internet → fonts ไม่โหลด → browser ใช้ fallback font ซึ่ง layout อาจเพี้ยน ควร self-host fonts ไว้ใน `web/fonts/`

### 5.4 ไม่มี HTTPS

ทุก traffic ระหว่าง browser กับ dashboard เป็น plaintext HTTP ใน field operation ที่ใช้ open Wi-Fi Hotspot ถ้ามีคนดักฟัง passive scan จะเห็น API token ใน header ได้เลย สำหรับ prototype ที่ใช้ในพื้นที่จำกัดอาจยอมรับได้ แต่ควร document ไว้ใน README อย่างชัดเจน

---

## 6. สิ่งที่ทำได้ดี

**DSP Pipeline สะอาดและถูกต้อง:** `dsp.py` เล็กกระทัดรัด ฟังก์ชันทุกตัวทำสิ่งเดียว ชัดเจน การใช้ Hanning window + FFT + fftshift + dB conversion ทำถูกต้อง การทำ max-pooling ระหว่าง downsample ใน `scale_points()` เพื่อ preserve jammer bands เป็น engineering decision ที่ดีมาก ไม่ใช่แค่ average ซึ่งจะทำให้สัญญาณ narrow-band จางหายได้

**Adaptive Noise Floor + Baseline Guard:** Algorithm ใน `_detect_jamming()` ที่ใช้ alpha ต่างกันระหว่าง SCANNING กับ WATCH state และ freeze noise floor เมื่อ floor rise เกิน threshold เพื่อกัน jammer จาก "dragging up" baseline เป็น design ที่ฉลาด เห็นได้ชัดว่า developer เข้าใจ adversarial RF environment จริงๆ ไม่ใช่แค่เขียนตาม tutorial

**Hardware Graceful Degradation:** `BuzzerController` และ `LEDController` ทั้งคู่ gracefully degrade เมื่อ GPIO ไม่พร้อมใช้ (`self.enabled = False`) ทำให้ preview mode และ development บน Windows/Linux ทำงานได้โดยไม่ต้องมี hardware จริง

**Touch Calibration Tool (`calibrate_touch.py`):** ครบถ้วน professional มากสำหรับ embedded — มี median filtering, axis swap detection, linear extrapolation, JSON persistence และ visual feedback บน LCD ระหว่าง process ทุกขั้นตอน ดีกว่าโปรเจกต์ส่วนใหญ่ที่ hardcode calibration ไว้เลย

**Web Dashboard Event-Driven Rendering:** การที่ `drawSpectrum()`, `drawMarginTrend()`, `drawWaterfall()` เรียกผ่าน `requestAnimationFrame()` เฉพาะเมื่อมีข้อมูลใหม่มา และไม่ใช้ `setInterval` ที่ 60 FPS บวกกับ DOM value differencing (`domCache`) ที่ป้องกัน unnecessary DOM write ทำให้ browser บน device client ประหยัด CPU อย่างมาก

**IMU Frozen Sensor Recovery (`hardware/mpu6050.py`):** `frozen_count > 40` แล้ว attempt `_init_sensor()` เป็น production-grade resilience สำหรับ I2C bus ที่ไม่เสถียร ป้องกัน bearing หยุดนิ่งโดยไม่มีใครรู้

**`os.execv()` สำหรับ Restart:** การ replace process image แทนที่จะ `subprocess` spawn หรือ reboot ทั้งเครื่องเป็น technique ที่เหมาะมากสำหรับ Pi Zero ที่ boot ช้า ทำให้ restart เร็วกว่า 10x และ clear I2C state ของ MPU6050 ได้

**`ServerState` Thread Safety ใน `web_server.py`:** ใช้ `threading.Lock` ครอบทุก read/write บน shared state ระหว่าง main loop และ waitress threads ถูกต้องตามหลัก concurrent programming ไม่มี data race

**`agent.md` — Outstanding Documentation:** Hardware constraints, I²C voltage warnings, SPI pin rules, database I/O limits ถูก document ครบและชัดเจน เป็น practice ที่ควรทำในทุกโปรเจกต์ embedded และเป็นประโยชน์อย่างยิ่งสำหรับ AI-assisted development

---

## 7. สิ่งที่ควรแก้ไข เรียงตามความสำคัญ

### 🔴 Critical — แก้ทันที

**[C1] เปิด SQLite WAL Mode ใน `database_manager.init_db()`**  
เพิ่ม 2 บรรทัดหลัง `conn = sqlite3.connect(DB_NAME)`:
```python
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
```
ป้องกัน `OperationalError: database is locked` เมื่อ web server thread อ่านในขณะ main loop thread เขียน ความเสี่ยงสูงมากบน Pi Zero ที่ SD card ช้า แก้ครั้งเดียวป้องกันได้ทั้งหมด

**[C2] Warning Calibration ต้องแสดงบน LCD ไม่ใช่แค่ Terminal**  
`detector.py` บรรทัด 143: เพิ่ม `self.ui.show_toast("WARN: NOISY CALIB!", 4.0)` เมื่อ NF range > 5 dB operator ในสนามไม่ได้เห็น terminal

**[C3] แก้ Dummy Peak ใน `manual_capture()`**  
`detector.py` บรรทัด 424: เพิ่ม `self.last_metrics: dict = {}` ใน `__init__` และ update มันใน `run()` หลัง `_detect_jamming()` แล้ว `manual_capture()` ใช้ `self.last_metrics.get('peak_p', -50.0)` แทน hardcode

---

### 🟡 Important — แก้ใน sprint ถัดไป

**[I1] เพิ่ม Consecutive Error Counter ใน `run()` loop**  
เมื่อ `sdr.read_samples()` fail ต่อเนื่อง > 10 ครั้ง ให้ set `self.reboot_requested = True` แทนที่จะวน loop สร้าง error ซ้ำๆ ป้องกัน CPU spike และ log spam บน SD card

**[I2] Extract `_handle_keyboard_input()` method**  
`detector.py` บรรทัด 263-308: ตัด duplicate keyboard dispatch block ~25 บรรทัด ออก แล้วให้ทั้ง Windows และ Unix branch เรียก method เดียวกัน

**[I3] ใช้ `config.SAMPLE_COUNT` แทน magic number**  
`detector.py` บรรทัด 23: `self.sample_count = 8192` → `self.sample_count = config.SAMPLE_COUNT`

**[I4] Self-host Google Fonts**  
`web/index.html` บรรทัด 9-13: download Inter + JetBrains Mono ใส่ใน `web/fonts/` แล้วแก้ CSS เป็น `@font-face` local ป้องกัน layout พัง และทำให้ dashboard ใช้งานได้ offline

**[I5] ลบ `getattr()` ที่ไม่จำเป็นใน `_detect_jamming()`**  
`detector.py` บรรทัด 188, 195, 201, 202: เปลี่ยน `getattr(self, 'baseline_guard_active', False)` → `self.baseline_guard_active` ทุกที่

**[I6] Document Dead Code ใน `hardware/rtc_ds3231.py`**  
เพิ่ม docstring หรือ comment ที่ top ของไฟล์ว่า "ปัจจุบัน RTC ถูก handle โดย Linux kernel driver — module นี้ไม่ได้ใช้งาน reserve ไว้สำหรับ fallback กรณี hwclock ไม่พร้อม"

**[I7] แก้ `_touch_worker` ใช้ `self.app.w / self.app.h` แทน hardcode**  
`display_ui.py` บรรทัด 891-892: `* 480.0` → `* float(self.app.w)`, `* 320.0` → `* float(self.app.h)`

---

### 🟢 Nice to Have — Backlog

**[N1] แก้ `generate_previews.py`: บันทึก Image object ตรงๆ**  
แทน `Image.open("preview.png").save(...)` ให้ใช้ `app._img.save(...)` ลด disk I/O ฟุ่มเฟือย

**[N2] Throttle Particle Animation เมื่อ Tab ไม่ Active**  
`web/script.js`: เพิ่ม `visibilitychange` listener pause `animateParticles()` เมื่อ user switch tab

**[N3] แทนที่ Python timestamp filter ด้วย SQL ใน `get_filtered_history()`**  
ลด memory footprint และ CPU time สำหรับ CSV export บน Pi

**[N4] แก้ Comment ภาษาไทยโดดๆ ใน `detector.py` บรรทัด 551 เป็น English**  
ให้ codebase มี language convention เดียวกัน

**[N5] Precompute sin/cos table สำหรับ Radar rendering**  
`display_ui.py` `_draw_radar()`: cache lookup table ที่ init แทน `np.radians()` ทุก frame

---

## สรุป

GUNJAM เป็นโปรเจกต์ embedded ที่มีคุณภาพสูงกว่า average prototype อย่างชัดเจน — DSP algorithm ถูกต้องและ production-ready, hardware abstraction ทำดี, web dashboard มี performance optimization ที่จริงจัง และ `agent.md` แสดงให้เห็นว่า developer เข้าใจ hardware constraints อย่างลึกซึ้ง

จุดเสี่ยงที่ใหญ่ที่สุดตอนนี้คือ **SQLite WAL mode ที่ขาดหายไป [C1]** ซึ่งอาจทำให้ database lock ใน field ได้จริง และ **security ของ `/api/clear` [C2 ร่วมกับ 5.1]** ที่ควรปิดก่อน deploy ให้ใครใช้ ทั้งสองอย่างแก้ได้ใน 10 นาที

ส่วน God Class ใน `detector.py` เป็น technical debt ที่ยอมรับได้สำหรับ embedded project ขนาดนี้ แต่ถ้าจะต่อยอดเป็น product เต็มรูปแบบ ควรวางแผน refactor ออกเป็น `SignalProcessor`, `StateManager`, `DataLogger` แยกกันในอนาคต
