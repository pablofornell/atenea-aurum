"""Quick diagnostic: captures MT4 and shows crop result side by side.

Run with:  python src/tools/test_screenshot_crop.py
Requires MT4 to be open with at least one chart active.
Saves two PNG files to tmp/screenshots/ for comparison:
  - mt4_full_<ts>.png  — full window (original behaviour)
  - mt4_crop_<ts>.png  — chart-only crop (new behaviour)
"""
import os
import sys
import logging
from datetime import datetime

# Allow running from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    try:
        import win32gui
        import win32ui
        import win32con
        from ctypes import windll
        from PIL import Image
        from src.mt4.screenshot import find_mt4_hwnd, _find_chart_bounds
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install pywin32 Pillow")
        sys.exit(1)

    save_dir = "data/screenshots"
    os.makedirs(save_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("Looking for MT4 window…")
    try:
        hwnd = find_mt4_hwnd("NMarkets")
        print(f"Found MT4 window: hwnd={hwnd}")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Restore if minimized
    try:
        if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            print("Restored minimized window.")
    except Exception:
        pass

    # Get window rect
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    print(f"Full window size: {w}×{h}px")

    # Capture full window
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
    bmpinfo = bmp.GetInfo()
    bmpstr = bmp.GetBitmapBits(True)
    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    full_img = Image.frombuffer("RGB", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                                 bmpstr, "raw", "BGRX", 0, 1)

    # Save full window
    full_path = os.path.join(save_dir, f"mt4_full_{ts}.png")
    full_img.save(full_path)
    print(f"Full window saved: {full_path}")

    # Detect chart bounds and crop
    crop_box = _find_chart_bounds(hwnd, left, top, w, h)
    l, t, r, b = crop_box
    print(f"Detected chart bounds: left={l} top={t} right={r} bottom={b} "
          f"({r-l}×{b-t}px)")

    if crop_box == (0, 0, w, h):
        print("WARNING: No chart area detected — crop equals full window.")
        print("  Make sure MT4 has at least one chart open and is not minimized.")
    else:
        crop_pct = round((r - l) * (b - t) / (w * h) * 100, 1)
        print(f"Chart is {crop_pct}% of the full window area.")

    cropped_img = full_img.crop(crop_box)
    crop_path = os.path.join(save_dir, f"mt4_crop_{ts}.png")
    cropped_img.save(crop_path)
    print(f"Cropped chart saved: {crop_path}")
    print()
    print("Open both PNGs to compare. The cropped version is what Claude receives.")


if __name__ == "__main__":
    main()
