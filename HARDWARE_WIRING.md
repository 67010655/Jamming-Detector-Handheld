# Jamming Detector Handheld - Hardware Wiring Guide

ไฟล์นี้สรุปการต่อสายไฟระหว่างแผงหน้าจอ (ILI9488 + XPT2046), เซ็นเซอร์ GY-9250, และโมดูลอื่นๆ เข้ากับ Raspberry Pi เพื่อใช้ในการตรวจสอบและต่อสายไฟใหม่

## 1. หน้าจอแสดงผล (ILI9488 TFT LCD)
เชื่อมต่อผ่านระบบ **SPI0**

| ขาบนโมดูลจอ (LCD) | ต่อเข้ากับ Raspberry Pi (ชื่อ GPIO) | หมายเลข Pin บน Pi (Physical) | หน้าที่ |
| :--- | :--- | :--- | :--- |
| **VCC** / **5V** | 5V หรือ 3.3V (ตามสเปคจอ) | Pin 2 หรือ Pin 4 (5V) / Pin 1 (3.3V) | ไฟเลี้ยงวงจร |
| **GND** | GND | Pin 6, 9, 14, 20, 25 (เลือกใช้ได้) | กราวด์ |
| **CS** / **LCD_CS** | GPIO 8 (SPI0 CE0) | Pin 24 | เลือกรับคำสั่งจอภาพ |
| **RESET** / **RST**| GPIO 25 | Pin 22 | รีเซ็ตจอภาพ |
| **DC** / **RS** | GPIO 24 | Pin 18 | แยกแยะ Data / Command |
| **SDI** / **MOSI** | GPIO 10 (SPI0 MOSI) | Pin 19 | รับข้อมูลภาพจาก Pi |
| **SCK** / **CLK** | GPIO 11 (SPI0 SCLK) | Pin 23 | สัญญาณนาฬิกา SPI |
| **LED** / **BL** | 3.3V | Pin 1 หรือ 17 | ไฟ Backlight หน้าจอ |

---

## 2. ทัชสกรีน (XPT2046)
วงจรทัชสกรีนมักจะอยู่บนแผงเดียวกับหน้าจอ และใช้ **SPI0** ร่วมกัน (แชร์สาย MOSI, MISO, SCK)

| ขาบนโมดูลจอ (Touch) | ต่อเข้ากับ Raspberry Pi (ชื่อ GPIO) | หมายเลข Pin บน Pi (Physical) | หน้าที่ |
| :--- | :--- | :--- | :--- |
| **T_CLK** | GPIO 11 (SPI0 SCLK) | Pin 23 | (ใช้ร่วมกับจอภาพ) |
| **T_CS** | **GPIO 22** | **Pin 15** | เลือกอ่านค่าจากทัชสกรีน |
| **T_DIN** | GPIO 10 (SPI0 MOSI) | Pin 19 | (ใช้ร่วมกับจอภาพ) |
| **T_DO** | GPIO 9 (SPI0 MISO) | Pin 21 | (ใช้ร่วมกับจอภาพ) |
| **T_IRQ** | - (ไม่ใช้) | - | โค้ดใช้วิธีอ่านวนลูป ไม่ต้องต่อก็ได้ |

> **⚠️ หมายเหตุสำคัญสำหรับการแก้ปัญหา "จอขาว + มีเสียงแตะรัวๆ":**
> ลอง **"ถอดสาย T_CS (Pin 15)"** ออกดูก่อนครับ เพื่อตัดการทำงานของทัชสกรีน ถ้าจอภาพกลับมาติด แปลว่าวงจรทัชสกรีนอาจจะช็อต หรือถูกเคสบีบอัดจนหน้าสัมผัสแตะกันตลอดเวลาครับ

---

## 3. เซ็นเซอร์ DS3231 (Real-Time Clock - RTC)
เชื่อมต่อผ่านระบบ **I2C1** (ที่อยู่ไอทูซี: `0x68`) เพื่อรักษานาฬิกาเวลาจริงสำหรับการทำงานแบบออฟไลน์

| ขาบนโมดูล DS3231 | ต่อเข้ากับ Raspberry Pi (ชื่อ GPIO) | หมายเลข Pin บน Pi (Physical) | หน้าที่ |
| :--- | :--- | :--- | :--- |
| **VCC** | 3.3V | Pin 1 หรือ Pin 17 | ไฟเลี้ยงโมดูล |
| **GND** | GND | Pin 6, Pin 9, Pin 14... | กราวด์ |
| **SCL** | GPIO 3 (I2C1 SCL) | Pin 5 | สัญญาณนาฬิกา I2C (แชร์บัส) |
| **SDA** | GPIO 2 (I2C1 SDA) | Pin 3 | สัญญาณข้อมูล I2C (แชร์บัส) |

> **💡 เทคนิคเชิงวิศวกรรมการแชร์สาย I2C1 (GY-9250 + DS3231):**
> เซ็นเซอร์ **GY-9250 (IMU)** และ **DS3231 (RTC)** ใช้สายบัส **I2C1** ร่วมกันได้ เพราะ address ไม่ซ้ำกัน: DS3231 อยู่ที่ `0x68` และ GY-9250 ต้องตั้งให้เป็น `0x69` โดยผูก AD0/ADO เข้ากับ 3.3V

---

## 4. GY-9250 / MPU9250 (9-axis IMU)
Use I2C1 with the fixed project address `0x69`.

| Pin on GY-9250 / MPU9250 | Connect to Raspberry Pi | Physical Pin | Purpose |
| :--- | :--- | :--- | :--- |
| **VCC** | 3.3V | Pin 1 or Pin 17 | Sensor power |
| **GND** | GND | Pin 6, 9, 14, 20... | Ground |
| **SCL** | GPIO 3 (I2C1 SCL) | Pin 5 | I2C clock, shared bus |
| **SDA** | GPIO 2 (I2C1 SDA) | Pin 3 | I2C data, shared bus |
| **AD0 / ADO** | 3.3V | Pin 1 or Pin 17 | Force main IMU address to `0x69` |

> **Critical:** DS3231 already occupies `0x68`. Most GY-9250 boards default to `0x68` when AD0/ADO is LOW or floating, so tie AD0/ADO to **3.3V only** before booting this build. Do **not** feed 5V into AD0/ADO.

Recommended smoke check after wiring:

```bash
i2cdetect -y 1
python test_sensors.py
```

Expected I2C devices: DS3231 at `0x68`, GY-9250 main IMU at `0x69`, and AK8963 magnetometer at `0x0c` after the driver enables bypass mode.

---

## 5. โมดูลระบุพิกัด (GPS Neo-M8N)
เชื่อมต่อผ่านระบบพอร์ตอนุกรม **UART (Serial)** ของ Raspberry Pi

| ขาบนโมดูล GPS | ต่อเข้ากับ Raspberry Pi | หมายเลข Pin บน Pi (Physical) | หน้าที่ |
| :--- | :--- | :--- | :--- |
| **VCC** | 3.3V หรือ 5V | Pin 1 หรือ Pin 2 | ไฟเลี้ยงโมดูล |
| **GND** | GND | Pin 6 หรือ Pin 9 | กราวด์ |
| **TX** | GPIO 15 (RXD) | Pin 10 | ส่งข้อมูลพิกัด (NMEA) ไปยัง Pi |
| **RX** | GPIO 14 (TXD) | Pin 8 | (ไม่จำเป็นต้องต่อสำหรับอ่านอย่างเดียว) |

---

## 6. สถานะไฟ LED, Buzzer และ ปุ่มปิดเสียงฮาร์ดแวร์

| โมดูล | ต่อเข้ากับ Raspberry Pi (ชื่อ GPIO) | หมายเลข Pin บน Pi (Physical) | รายละเอียด |
| :--- | :--- | :--- | :--- |
| **RED LED** (JAMMING) | GPIO 17 | Pin 11 | แจ้งเตือนสถานะตรวจพบสัญญาณกวน |
| **YELLOW LED** (WATCH) | GPIO 27 | Pin 13 | แจ้งเตือนสถานะเฝ้าระวังสัญญาณ |
| **GREEN LED** (SCANNING)| GPIO 26 | Pin 37 | แจ้งเตือนสถานะสแกนคลื่นวิทยุปกติ |
| **Buzzer (Active/Passive)**| GPIO 18 | Pin 12 | ส่งสัญญาณเสียงเตือน (PWM alert) |
| **Mute Switch (Physical Button)**| **GPIO 23** (แนะนำ) | **Pin 16** | ปุ่มกดปิดเสียงฮาร์ดแวร์ ต่อสวิตช์แบบกดติด-ปล่อยดับ/ลอค ระหว่างขานี้กับ GND (เพื่อเลี่ยงการกดปุ่มบนจอ LCD ที่กดยาก) |

---

## 💡 คำแนะนำในการต่อสายใหม่
1. **ปิดเครื่อง (Shutdown) และถอดสายไฟเลี้ยง Raspberry Pi ออกให้หมดก่อนทำการดึงหรือเสียบสาย Jumper เสมอ** ป้องกันไฟกระชากเข้าจอ (จอพังง่ายมากถ้าเสียบสาย SPI สลับกันตอนเครื่องเปิดอยู่)
2. สาย **MOSI, MISO, SCK** เป็นสายที่ความถี่สูงและแชร์กันระหว่างจอและทัชสกรีน ให้เสียบให้แน่นๆ ถ้าหลวมจอจะขาว
3. ลองเปิดใช้งานโดยยังไม่ต้องต่อสายกลุ่ม **T_... (ทัชสกรีน)** เพื่อดูว่าจอภาพทำงานได้ปกติก่อนหรือไม่ ถ้าภาพขึ้นปกติ ค่อยเสียบสาย T_CS, T_DIN, T_DO เพื่อเปิดใช้ทัชสกรีนครับ
4. **ปุ่ม Mute แบบบัดกรี:** เมื่อบัดกรีสายสัญญาณปุ่มกดทางกายภาพเข้าขา GPIO 23 และ GND แล้ว สามารถพัฒนาฟังก์ชันตรวจจับสัญญาณตก (Falling Edge) ด้วย `GPIO.add_event_detect` ใน Python เพื่อใช้คุมสถานะ `self.buzzer.toggle_mute()` ได้อย่างรวดเร็วและทนทานกว่าหน้าจอสัมผัสครับ


