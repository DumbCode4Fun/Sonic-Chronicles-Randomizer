"""Screenshot the Mod Pack Maker's Randomizer tab, unattended.

Tk cannot render itself to an image, so the window is shown for real and grabbed from
the screen. Two Windows details decide whether that works:

* **DPI awareness, set before Tk starts.** This display runs at 125%, so Tk reported a
  2048x1152 screen while the panel is physically 2560x1440. Tk's coordinates were
  logical and PIL's grab was physical, so every rectangle came out 1.25x off - the left
  edge pulled in the desktop behind the window and the bottom button bar fell outside
  the capture. Declaring the process per-monitor DPI aware makes the two agree.
* **DWMWA_EXTENDED_FRAME_BOUNDS, not GetWindowRect or winfo_rootx.** `winfo_rootx` is
  the *client* origin, so grabbing from it clips the title bar. `GetWindowRect` is the
  other extreme: since Vista it includes an invisible resize border a few pixels wide,
  which shows up as a strip of whatever is behind the window. DWM reports the bounds
  that are actually painted.
"""
import sys, os, time, ctypes, ctypes.wintypes, tkinter as tk

try:                                    # per-monitor aware; must precede Tk
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

sys.path[:0] = ['tools/gui', 'tools/build', 'tools/recon']
os.environ.setdefault('SONIC_CHRONICLES_ROM', '')
import modpack_maker as M
from PIL import ImageGrab

root = tk.Tk()
app = M.App(root)
root.geometry('1197x1059+80+30')
tab = os.environ.get('SHOT_TAB', 'random')
app.nb.select({'presets': app.tab_presets, 'chars': app.tab_chars,
               'game': app.tab_game, 'items': app.tab_items,
               'random': app.tab_random}[tab])
root.update_idletasks(); root.update()
root.lift(); root.attributes('-topmost', True)
for _ in range(60):
    root.update(); time.sleep(0.04)

hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
class R(ctypes.Structure):
    _fields_ = [('l', ctypes.c_long), ('t', ctypes.c_long),
                ('r', ctypes.c_long), ('b', ctypes.c_long)]
rect = R()
DWMWA_EXTENDED_FRAME_BOUNDS = 9
if ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.wintypes.HWND(hwnd), ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
img = ImageGrab.grab((rect.l, rect.t, rect.r, rect.b))
out = sys.argv[1] if len(sys.argv) > 1 else 'assets/mod-pack-maker.png'
img.save(out)
print('%dx%d -> %s' % (img.width, img.height, out))
root.destroy()
