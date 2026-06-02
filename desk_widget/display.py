# =============================================================================
# display.py — ILI9488 SPI driver for ESP32-S3 (MicroPython)
# Resolution: 480 x 320, 18-bit colour (RGB666) over 4-wire SPI
# =============================================================================

from machine import Pin, SPI, PWM
import ustruct
import time
import config

# ILI9488 command bytes
_CMD_NOP        = 0x00
_CMD_SWRESET    = 0x01
_CMD_SLPOUT     = 0x11
_CMD_NORON      = 0x13
_CMD_INVOFF     = 0x20
_CMD_INVON      = 0x21
_CMD_DISPON     = 0x29
_CMD_CASET      = 0x2A
_CMD_PASET      = 0x2B
_CMD_RAMWR      = 0x2C
_CMD_MADCTL     = 0x36
_CMD_COLMOD     = 0x3A
_CMD_PGAMCTRL   = 0xE0
_CMD_NGAMCTRL   = 0xE1
_CMD_PWCTRL1    = 0xC0
_CMD_PWCTRL2    = 0xC1
_CMD_VMCTRL1    = 0xC5
_CMD_IFMODE     = 0xB0
_CMD_FRMCTR1    = 0xB1
_CMD_DISCTRL    = 0xB6
_CMD_ETMOD      = 0xB7
_CMD_IFCTL      = 0xF7


class ILI9488:
    """Minimal ILI9488 driver — pixel, fill, blit, and text rendering."""

    def __init__(self):
        self._spi = SPI(
            config.SPI_ID,
            baudrate=config.SPI_BAUDRATE,
            polarity=0,
            phase=0,
            sck=Pin(config.PIN_SCK),
            mosi=Pin(config.PIN_MOSI),
            miso=Pin(config.PIN_MISO),
        )
        self._cs  = Pin(config.PIN_CS,  Pin.OUT, value=1)
        self._dc  = Pin(config.PIN_DC,  Pin.OUT, value=0)
        self._rst = Pin(config.PIN_RST, Pin.OUT, value=1)
        self._bl  = PWM(Pin(config.PIN_BL), freq=1000, duty=1023)
        self.width  = config.DISPLAY_WIDTH
        self.height = config.DISPLAY_HEIGHT
        self._init_display()

    # ------------------------------------------------------------------ #
    #  Low-level helpers                                                   #
    # ------------------------------------------------------------------ #

    def _cs_lo(self):  self._cs.value(0)
    def _cs_hi(self):  self._cs.value(1)
    def _dc_lo(self):  self._dc.value(0)   # command
    def _dc_hi(self):  self._dc.value(1)   # data

    def _write_cmd(self, cmd):
        self._dc_lo()
        self._cs_lo()
        self._spi.write(bytes([cmd]))
        self._cs_hi()

    def _write_data(self, data):
        self._dc_hi()
        self._cs_lo()
        self._spi.write(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        self._cs_hi()

    def _write_cmd_data(self, cmd, *data_bytes):
        self._write_cmd(cmd)
        if data_bytes:
            self._write_data(bytes(data_bytes))

    # ------------------------------------------------------------------ #
    #  Initialisation sequence                                             #
    # ------------------------------------------------------------------ #

    def _init_display(self):
        # Hardware reset
        self._rst.value(0); time.sleep_ms(50)
        self._rst.value(1); time.sleep_ms(120)

        self._write_cmd(_CMD_SWRESET); time.sleep_ms(120)
        self._write_cmd(_CMD_SLPOUT);  time.sleep_ms(120)

        # Pixel format: 18-bit / 3 bytes per pixel (0x66)
        self._write_cmd_data(_CMD_COLMOD, 0x66)

        # Power control
        self._write_cmd_data(_CMD_PWCTRL1, 0x17, 0x15)
        self._write_cmd_data(_CMD_PWCTRL2, 0x41)
        self._write_cmd_data(_CMD_VMCTRL1, 0x00, 0x12, 0x80)

        # Memory access: landscape (MX+MV bits), BGR order
        self._write_cmd_data(_CMD_MADCTL, 0x48)

        # Frame rate: ~60 Hz
        self._write_cmd_data(_CMD_FRMCTR1, 0xA0)

        # Inversion off, normal display
        self._write_cmd(_CMD_INVOFF)
        self._write_cmd(_CMD_NORON)

        # Positive / negative gamma (ILI9488 typical values)
        self._write_cmd(_CMD_PGAMCTRL)
        self._write_data(bytes([
            0x00, 0x03, 0x09, 0x08, 0x16, 0x0A, 0x3F, 0x78,
            0x4C, 0x09, 0x0A, 0x08, 0x16, 0x1A, 0x0F
        ]))
        self._write_cmd(_CMD_NGAMCTRL)
        self._write_data(bytes([
            0x00, 0x16, 0x19, 0x03, 0x0F, 0x05, 0x32, 0x45,
            0x46, 0x04, 0x0E, 0x0D, 0x35, 0x37, 0x0F
        ]))

        self._write_cmd(_CMD_DISPON)
        time.sleep_ms(20)

    # ------------------------------------------------------------------ #
    #  Drawing primitives                                                  #
    # ------------------------------------------------------------------ #

    def _set_window(self, x0, y0, x1, y1):
        self._write_cmd(_CMD_CASET)
        self._write_data(ustruct.pack(">HH", x0, x1))
        self._write_cmd(_CMD_PASET)
        self._write_data(ustruct.pack(">HH", y0, y1))
        self._write_cmd(_CMD_RAMWR)

    @staticmethod
    def _rgb565_to_rgb666(color565):
        """Convert RGB565 → 3-byte RGB666 for ILI9488."""
        r = (color565 >> 11) & 0x1F
        g = (color565 >>  5) & 0x3F
        b =  color565        & 0x1F
        # Expand to 6 bits each (shift left)
        return bytes([r << 3, g << 2, b << 3])

    def fill(self, color):
        """Fill the entire screen with a RGB565 colour."""
        self.fill_rect(0, 0, self.width, self.height, color)

    def fill_rect(self, x, y, w, h, color):
        """Fill a rectangle with a RGB565 colour (fast chunked write)."""
        self._set_window(x, y, x + w - 1, y + h - 1)
        pixel = self._rgb565_to_rgb666(color)
        chunk = pixel * 64          # 64 pixels per write
        total = w * h
        self._dc_hi(); self._cs_lo()
        for _ in range(total // 64):
            self._spi.write(chunk)
        rem = total % 64
        if rem:
            self._spi.write(pixel * rem)
        self._cs_hi()

    def pixel(self, x, y, color):
        self._set_window(x, y, x, y)
        self._write_data(self._rgb565_to_rgb666(color))

    def hline(self, x, y, w, color):
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x, y, h, color):
        self.fill_rect(x, y, 1, h, color)

    def rect(self, x, y, w, h, color):
        self.hline(x, y,         w, color)
        self.hline(x, y + h - 1, w, color)
        self.vline(x,         y, h, color)
        self.vline(x + w - 1, y, h, color)

    def blit_rgb565(self, x, y, w, h, data):
        """
        Blit a raw RGB565 bytearray (2 bytes per pixel, big-endian).
        The ILI9488 needs RGB666 so each pixel is expanded on the fly.
        """
        self._set_window(x, y, x + w - 1, y + h - 1)
        self._dc_hi(); self._cs_lo()
        buf = bytearray(w * h * 3)
        idx = 0
        for i in range(0, len(data), 2):
            c = (data[i] << 8) | data[i + 1]
            r = (c >> 11) & 0x1F
            g = (c >>  5) & 0x3F
            b =  c        & 0x1F
            buf[idx]     = r << 3
            buf[idx + 1] = g << 2
            buf[idx + 2] = b << 3
            idx += 3
        self._spi.write(buf)
        self._cs_hi()

    # ------------------------------------------------------------------ #
    #  Font rendering (5×7 built-in bitmap font)                          #
    # ------------------------------------------------------------------ #

    # Compact 5×7 ASCII font (printable chars 0x20–0x7E, 5 bytes each)
    _FONT5X7 = (
        b'\x00\x00\x00\x00\x00'  # space
        b'\x00\x00\x5F\x00\x00'  # !
        b'\x00\x07\x00\x07\x00'  # "
        b'\x14\x7F\x14\x7F\x14'  # #
        b'\x24\x2A\x7F\x2A\x12'  # $
        b'\x23\x13\x08\x64\x62'  # %
        b'\x36\x49\x55\x22\x50'  # &
        b'\x00\x05\x03\x00\x00'  # '
        b'\x00\x1C\x22\x41\x00'  # (
        b'\x00\x41\x22\x1C\x00'  # )
        b'\x14\x08\x3E\x08\x14'  # *
        b'\x08\x08\x3E\x08\x08'  # +
        b'\x00\x50\x30\x00\x00'  # ,
        b'\x08\x08\x08\x08\x08'  # -
        b'\x00\x60\x60\x00\x00'  # .
        b'\x20\x10\x08\x04\x02'  # /
        b'\x3E\x51\x49\x45\x3E'  # 0
        b'\x00\x42\x7F\x40\x00'  # 1
        b'\x42\x61\x51\x49\x46'  # 2
        b'\x21\x41\x45\x4B\x31'  # 3
        b'\x18\x14\x12\x7F\x10'  # 4
        b'\x27\x45\x45\x45\x39'  # 5
        b'\x3C\x4A\x49\x49\x30'  # 6
        b'\x01\x71\x09\x05\x03'  # 7
        b'\x36\x49\x49\x49\x36'  # 8
        b'\x06\x49\x49\x29\x1E'  # 9
        b'\x00\x36\x36\x00\x00'  # :
        b'\x00\x56\x36\x00\x00'  # ;
        b'\x08\x14\x22\x41\x00'  # <
        b'\x14\x14\x14\x14\x14'  # =
        b'\x00\x41\x22\x14\x08'  # >
        b'\x02\x01\x51\x09\x06'  # ?
        b'\x32\x49\x79\x41\x3E'  # @
        b'\x7E\x11\x11\x11\x7E'  # A
        b'\x7F\x49\x49\x49\x36'  # B
        b'\x3E\x41\x41\x41\x22'  # C
        b'\x7F\x41\x41\x22\x1C'  # D
        b'\x7F\x49\x49\x49\x41'  # E
        b'\x7F\x09\x09\x09\x01'  # F
        b'\x3E\x41\x49\x49\x7A'  # G
        b'\x7F\x08\x08\x08\x7F'  # H
        b'\x00\x41\x7F\x41\x00'  # I
        b'\x20\x40\x41\x3F\x01'  # J
        b'\x7F\x08\x14\x22\x41'  # K
        b'\x7F\x40\x40\x40\x40'  # L
        b'\x7F\x02\x0C\x02\x7F'  # M
        b'\x7F\x04\x08\x10\x7F'  # N
        b'\x3E\x41\x41\x41\x3E'  # O
        b'\x7F\x09\x09\x09\x06'  # P
        b'\x3E\x41\x51\x21\x5E'  # Q
        b'\x7F\x09\x19\x29\x46'  # R
        b'\x46\x49\x49\x49\x31'  # S
        b'\x01\x01\x7F\x01\x01'  # T
        b'\x3F\x40\x40\x40\x3F'  # U
        b'\x1F\x20\x40\x20\x1F'  # V
        b'\x3F\x40\x38\x40\x3F'  # W
        b'\x63\x14\x08\x14\x63'  # X
        b'\x07\x08\x70\x08\x07'  # Y
        b'\x61\x51\x49\x45\x43'  # Z
        b'\x00\x7F\x41\x41\x00'  # [
        b'\x02\x04\x08\x10\x20'  # backslash
        b'\x00\x41\x41\x7F\x00'  # ]
        b'\x04\x02\x01\x02\x04'  # ^
        b'\x40\x40\x40\x40\x40'  # _
        b'\x00\x01\x02\x04\x00'  # `
        b'\x20\x54\x54\x54\x78'  # a
        b'\x7F\x48\x44\x44\x38'  # b
        b'\x38\x44\x44\x44\x20'  # c
        b'\x38\x44\x44\x48\x7F'  # d
        b'\x38\x54\x54\x54\x18'  # e
        b'\x08\x7E\x09\x01\x02'  # f
        b'\x0C\x52\x52\x52\x3E'  # g
        b'\x7F\x08\x04\x04\x78'  # h
        b'\x00\x44\x7D\x40\x00'  # i
        b'\x20\x40\x44\x3D\x00'  # j
        b'\x7F\x10\x28\x44\x00'  # k
        b'\x00\x41\x7F\x40\x00'  # l
        b'\x7C\x04\x18\x04\x78'  # m
        b'\x7C\x08\x04\x04\x78'  # n
        b'\x38\x44\x44\x44\x38'  # o
        b'\x7C\x14\x14\x14\x08'  # p
        b'\x08\x14\x14\x18\x7C'  # q
        b'\x7C\x08\x04\x04\x08'  # r
        b'\x48\x54\x54\x54\x20'  # s
        b'\x04\x3F\x44\x40\x20'  # t
        b'\x3C\x40\x40\x20\x7C'  # u
        b'\x1C\x20\x40\x20\x1C'  # v
        b'\x3C\x40\x30\x40\x3C'  # w
        b'\x44\x28\x10\x28\x44'  # x
        b'\x0C\x50\x50\x50\x3C'  # y
        b'\x44\x64\x54\x4C\x44'  # z
        b'\x00\x08\x36\x41\x00'  # {
        b'\x00\x00\x7F\x00\x00'  # |
        b'\x00\x41\x36\x08\x00'  # }
        b'\x10\x08\x08\x10\x08'  # ~
    )

    def _draw_char(self, x, y, ch, fg, bg, scale=1):
        """Draw a single character at (x,y) with optional scale."""
        code = ord(ch)
        if code < 0x20 or code > 0x7E:
            code = 0x3F  # '?' for unsupported chars
        idx = (code - 0x20) * 5
        for col in range(5):
            line = self._FONT5X7[idx + col]
            for row in range(7):
                if line & (1 << row):
                    if scale == 1:
                        self.pixel(x + col, y + row, fg)
                    else:
                        self.fill_rect(x + col * scale, y + row * scale,
                                       scale, scale, fg)
                elif bg is not None:
                    if scale == 1:
                        self.pixel(x + col, y + row, bg)
                    else:
                        self.fill_rect(x + col * scale, y + row * scale,
                                       scale, scale, bg)

    def text(self, s, x, y, fg=0xFFFF, bg=None, scale=1):
        """
        Draw a string starting at (x, y).
        scale=1 → 5×7 px chars,  scale=2 → 10×14 px chars, etc.
        Returns the x position after the last character.
        """
        cx = x
        for ch in s:
            self._draw_char(cx, y, ch, fg, bg, scale)
            cx += (5 + 1) * scale   # 5 wide + 1 gap
        return cx

    def text_centered(self, s, cx, y, fg=0xFFFF, bg=None, scale=1):
        """Draw text horizontally centered around cx."""
        w = len(s) * (5 + 1) * scale
        self.text(s, cx - w // 2, y, fg, bg, scale)

    def backlight(self, duty):
        """Set backlight brightness 0–1023."""
        self._bl.duty(max(0, min(1023, duty)))
