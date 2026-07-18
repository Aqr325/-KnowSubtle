"""生成程序图标 程序图标.ico（32x32, 32bpp, 无外部依赖）。

设计：圆角方块 -> 外圈紫色 #A855F7，内圈品红 #EC4899，呼应品牌渐变。
输出：Release-Package/Install/程序图标.ico
"""
import math
import struct
from pathlib import Path

W = H = 32
pixels = bytearray()
cx = cy = 16.0
for y in range(H - 1, -1, -1):          # 倒序：ICO 位图自底向上
    for x in range(W):
        dx = x - cx + 0.5
        dy = y - cy + 0.5
        d = math.hypot(dx, dy)
        if d <= 15.0:
            edge = max(0.0, min(1.0, 15.5 - d))
            if d <= 9.0:
                inner = max(0.0, min(1.0, 9.5 - d))
                r, g, b = 236, 72, 153      # EC4899 品红
                a = int(255 * max(edge, inner))
            else:
                r, g, b = 168, 85, 247      # A855F7 紫色
                a = int(255 * edge)
        else:
            r = g = b = a = 0
        pixels += bytes((b, g, r, a))       # BGRA

and_mask = b"\x00" * (((W * H) + 7) // 8)   # 1bpp AND 掩码，全 0 = 不透明
bih = struct.pack("<IiiHHIIiiII",
                  40,        # biSize
                  W, H * 2,  # biWidth, biHeight（含 XOR+AND）
                  1,         # biPlanes
                  32,        # biBitCount
                  0,         # biCompression
                  0, 0, 0, 0, 0)  # biSizeImage, XPels, YPels, ClrUsed, ClrImportant
img = bih + bytes(pixels) + and_mask

icondir = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", W, H, 0, 0, 1, 32, len(img), 6 + 16)
ico = icondir + entry + img

out = Path(__file__).resolve().parent.parent / "Release-Package" / "Install" / "程序图标.ico"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(ico)
print(f"wrote {out} ({len(ico)} bytes)")
