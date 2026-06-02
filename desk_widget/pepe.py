# =============================================================================
# pepe.py — Pepe the Frog pixel art (80×80, RGB565)
# Classic "smug Pepe" face: green skin, big white eyes, red lips, brown outline
# =============================================================================
#
# Colour palette (RGB565):
#   TRANS = 0x0000  (background / transparent — filled with display BG)
#   DKGRN = 0x2940  dark green outline     #295000 → approx 0x2940
#   GREEN = 0x4CA0  mid green skin         #4CBF00 → approx 0x4CA0
#   LTGRN = 0x6760  light green highlight  #67C000 → approx 0x6760
#   WHITE = 0xFFFF  eye whites
#   BLACK = 0x0000  pupils / outline
#   RED   = 0xF800  mouth / lips
#   DKRED = 0x8000  lip shadow
#   CREAM = 0xFFE0  inner lip / teeth
#   BROWN = 0x8200  eyebrow / outline
#   GREY  = 0x8410  eyelid shadow
#
# Each row is 80 pixels wide; 80 rows total = 6400 pixels = 12800 bytes.
# The array is stored as a flat bytes literal (2 bytes per pixel, big-endian).
# =============================================================================

# Shorthand colour constants for the lookup table
_T = 0x0000   # transparent / bg
_K = 0x0000   # black
_G = 0x3DC0   # green skin   (approx #3BC800)
_D = 0x2940   # dark green outline
_L = 0x67E0   # light green
_W = 0xFFFF   # white
_R = 0xF800   # red
_r = 0xA000   # dark red
_C = 0xFF80   # cream / teeth
_B = 0x6200   # brown
_E = 0x8410   # grey eyelid

def _c(v):
    """Pack an RGB565 value into 2 big-endian bytes."""
    return bytes([(v >> 8) & 0xFF, v & 0xFF])

# ---------------------------------------------------------------------------
# 80×80 pixel art — row by row, 80 pixels per row
# Designed at 1× then stored directly.
# ---------------------------------------------------------------------------
# fmt: off
_ROW = [
    # row  0 — top of head
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  1
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  2
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  3
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  4
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  5
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  6 — eyebrow region
    [_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_B,_B,_B,_B,_B,_B,_B,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_B,_B,_B,_B,_B,_B,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  7
    [_T,_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_B,_B,_B,_B,_B,_B,_B,_B,_B,_B,_B,_B,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_B,_B,_B,_B,_B,_B,_B,_B,_B,_B,_B,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  8 — eye tops
    [_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row  9
    [_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 10
    [_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 11 — pupils
    [_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_E,_E,_E,_E,_W,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_E,_E,_E,_E,_W,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 12
    [_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_E,_K,_K,_K,_K,_E,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_W,_E,_K,_K,_K,_K,_E,_W,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 13
    [_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_E,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_E,_W,_W,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 14 — big pupil (dark)
    [_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_K,_K,_E,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_K,_K,_E,_W,_W,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 15
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_W,_W,_W,_K,_K,_K,_K,_E,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_W,_W,_W,_K,_K,_K,_K,_E,_W,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 16
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_E,_K,_K,_K,_W,_W,_W,_W,_W,_K,_K,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_W,_W,_W,_W,_W,_K,_K,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 17
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_W,_W,_W,_W,_W,_W,_W,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_W,_W,_W,_W,_W,_W,_W,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 18 — bottom of eyes
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_E,_K,_K,_K,_K,_K,_K,_K,_K,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_K,_K,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 19
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_K,_K,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 20
    [_D,_G,_G,_G,_G,_G,_G,_G,_K,_W,_K,_K,_E,_E,_E,_E,_E,_E,_E,_E,_K,_K,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_K,_W,_W,_E,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_E,_W,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 21 — closing eyelids
    [_D,_G,_G,_G,_G,_G,_G,_G,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_G,_G,_G,_G,_G,_G,_G,_G,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 22 — closed eye slits (smug half-closed look)
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 23 — cheek / lower face
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 24
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_L,_L,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_L,_L,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 25 — nose bridge
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_D,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 26
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_G,_G,_G,_G,_G,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 27 — nostrils
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_G,_K,_G,_G,_K,_G,_G,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 28
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_G,_G,_G,_G,_G,_G,_G,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 29 — philtrum / above lip
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_D,_D,_D,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 30
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 31 — top lip starts
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 32 — red upper lip
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 33
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 34 — mouth open / teeth
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_R,_R,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_r,_R,_R,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 35
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 36 — teeth row
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 37
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_C,_C,_C,_C,_D,_C,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 38
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_K,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 39 — lower lip
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 40
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_R,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 41
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # rows 42-47 — chin / lower face
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 48 — neck start
    [_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # rows 52-59: shirt collar / shoulders
    [_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_D,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_G,_D,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # row 60 — bottom/shoulders fade
    [_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_D,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T,_T],
    # rows 61-79: transparent padding
    [_T]*80, [_T]*80, [_T]*80, [_T]*80, [_T]*80,
    [_T]*80, [_T]*80, [_T]*80, [_T]*80, [_T]*80,
    [_T]*80, [_T]*80, [_T]*80, [_T]*80, [_T]*80,
    [_T]*80, [_T]*80, [_T]*80, [_T]*80,
]
# fmt: on

# Build flat bytearray once at import time
_PEPE_W = 80
_PEPE_H = 80

def _build_bitmap():
    buf = bytearray(_PEPE_W * _PEPE_H * 2)
    idx = 0
    for row in _ROW:
        for px in row:
            buf[idx]     = (px >> 8) & 0xFF
            buf[idx + 1] =  px       & 0xFF
            idx += 2
    return buf

PEPE_BITMAP = _build_bitmap()


def draw_pepe(display, x, y, bg=0x0000):
    """
    Draw the Pepe pixel art at screen position (x, y).
    Pixels with colour _T (0x0000 = black) are treated as transparent
    and replaced by `bg` (default: display background colour).

    Parameters
    ----------
    display : ILI9488   display driver instance
    x, y    : int       top-left corner on screen
    bg      : int       RGB565 colour to substitute for transparent pixels
    """
    # Re-build with correct bg substitution
    buf = bytearray(_PEPE_W * _PEPE_H * 2)
    idx = 0
    for row in _ROW:
        for px in row:
            colour = bg if px == _T else px
            buf[idx]     = (colour >> 8) & 0xFF
            buf[idx + 1] =  colour       & 0xFF
            idx += 2
    display.blit_rgb565(x, y, _PEPE_W, _PEPE_H, buf)
