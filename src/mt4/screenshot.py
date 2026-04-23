"""MT4 window screenshot capture using Win32 API.

Captures the MT4 window and auto-crops to the active chart area, removing
toolbars, menus, navigator panels, and terminal panels from the image sent
to Claude. Falls back to the full window if chart detection fails.
"""
import ctypes
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple

try:
    import win32gui
    import win32ui
    import win32con
    from ctypes import windll
    from PIL import Image
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

logger = logging.getLogger(__name__)

# WM_MDIGETACTIVE: ask MDI client which chart child is currently active
_WM_MDIGETACTIVE = 0x0229

# Minimum chart dimensions — anything smaller is probably not a real chart
_MIN_CHART_W = 300
_MIN_CHART_H = 200


class ScreenshotError(Exception):
    """Screenshot capture failed."""
    pass


def find_mt4_hwnd(partial_title: str = "NMarkets") -> int:
    """Find MT4 window handle by partial title match."""
    if not HAS_WIN32:
        raise ScreenshotError("pywin32 not installed. Install with: pip install pywin32")

    result = []

    def enum_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title.lower() in title.lower():
                result.append(hwnd)
        return True  # continue enumeration

    try:
        win32gui.EnumWindows(enum_callback, None)
    except Exception as e:
        raise ScreenshotError(f"Failed to enumerate windows: {e}")

    if not result:
        raise ScreenshotError(f"MT4 window not found (searched for '{partial_title}')")

    return result[0]


def _find_chart_bounds(
    hwnd: int,
    win_left: int,
    win_top: int,
    win_w: int,
    win_h: int,
) -> Tuple[int, int, int, int]:
    """Detect the active chart window bounds within the MT4 MDI frame.

    Strategy (highest to lowest precision):
      1. Find the MDIClient child of the MT4 main window.
      2. Ask it which MDI child is currently active (WM_MDIGETACTIVE).
      3. Use that chart window's rect → tightest possible crop.
      4. Fallback: use the MDIClient rect (removes toolbars/menu, keeps panels).
      5. Fallback: return full window bounds (no crop, current behaviour).

    All coordinates are returned relative to the top-left of the captured image.
    """
    full = (0, 0, win_w, win_h)

    try:
        # ── Step 1: find MDIClient ──────────────────────────────────────────
        mdi_clients: list = []

        def _visit(child_hwnd, _):
            try:
                if win32gui.GetClassName(child_hwnd) == "MDIClient":
                    mdi_clients.append(child_hwnd)
            except Exception:
                pass
            return True  # must return True to continue enumeration in pywin32

        win32gui.EnumChildWindows(hwnd, _visit, None)

        if not mdi_clients:
            logger.debug("MDIClient not found — using full window")
            return full

        mdi_hwnd = mdi_clients[0]

        # ── Step 2: get active MDI child (the focused chart) ────────────────
        SendMessage = ctypes.windll.user32.SendMessageW
        SendMessage.restype = ctypes.c_ssize_t
        active_chart = SendMessage(mdi_hwnd, _WM_MDIGETACTIVE, 0, 0)

        if active_chart:
            try:
                r = win32gui.GetWindowRect(active_chart)
                cw, ch = r[2] - r[0], r[3] - r[1]
                if cw >= _MIN_CHART_W and ch >= _MIN_CHART_H:
                    box = (
                        max(0, r[0] - win_left),
                        max(0, r[1] - win_top),
                        min(win_w, r[2] - win_left),
                        min(win_h, r[3] - win_top),
                    )
                    logger.debug(
                        f"Chart crop via active MDI child: {box} ({cw}×{ch}px)"
                    )
                    return box
            except Exception as e:
                logger.debug(f"Active MDI child rect failed: {e}")

        # ── Step 3: fallback — MDIClient rect (removes menus/toolbars) ──────
        try:
            mr = win32gui.GetWindowRect(mdi_hwnd)
            mw, mh = mr[2] - mr[0], mr[3] - mr[1]
            if mw >= _MIN_CHART_W and mh >= _MIN_CHART_H:
                box = (
                    max(0, mr[0] - win_left),
                    max(0, mr[1] - win_top),
                    min(win_w, mr[2] - win_left),
                    min(win_h, mr[3] - win_top),
                )
                logger.debug(f"Chart crop via MDIClient rect: {box}")
                return box
        except Exception as e:
            logger.debug(f"MDIClient rect failed: {e}")

    except Exception as e:
        logger.warning(f"Chart bounds detection failed entirely: {e}")

    logger.debug("Using full window (no crop)")
    return full


def capture_mt4(
    save_dir: str = "data/screenshots",
    partial_title: str = "NMarkets",
    restore_if_minimized: bool = True,
) -> str:
    """Capture the MT4 active chart as a PNG and return its absolute path.

    The image is automatically cropped to the chart area (removing toolbars,
    menus, navigator, and terminal panels) before being saved. If chart area
    detection fails at any step, the full window is saved instead.

    Args:
        save_dir: Directory to save the PNG file.
        partial_title: Partial MT4 window title (case-insensitive match).
        restore_if_minimized: Restore a minimized MT4 window before capturing.

    Returns:
        Absolute path to the saved PNG file.

    Raises:
        ScreenshotError on any capture failure.
    """
    if not HAS_WIN32:
        raise ScreenshotError("pywin32 not installed. Install with: pip install pywin32")

    # ── Find MT4 window ─────────────────────────────────────────────────────
    try:
        hwnd = find_mt4_hwnd(partial_title)
        logger.debug(f"Found MT4 window: hwnd={hwnd}")
    except ScreenshotError as e:
        raise ScreenshotError(f"Cannot find MT4 window: {e}")

    # ── Restore if minimized ────────────────────────────────────────────────
    if restore_if_minimized:
        try:
            if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED:
                logger.debug("Restoring minimized MT4 window…")
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception as e:
            logger.warning(f"Could not restore window: {e}")

    # ── Get full window rect ────────────────────────────────────────────────
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w, h = right - left, bottom - top
        if w <= 0 or h <= 0:
            raise ScreenshotError(f"Invalid window rect: {w}×{h}")
        logger.debug(f"Full window size: {w}×{h}")
    except ScreenshotError:
        raise
    except Exception as e:
        raise ScreenshotError(f"Failed to get window rect: {e}")

    # ── Capture full window via PrintWindow ─────────────────────────────────
    hwnd_dc = mfc_dc = save_dc = bmp = None
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)

        # PW_RENDERFULLCONTENT=2: renders GPU-accelerated content correctly
        result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        if result != 1:
            raise ScreenshotError(
                "PrintWindow failed — MT4 may be minimized or use incompatible rendering"
            )

        bmpinfo = bmp.GetInfo()
        bmpstr = bmp.GetBitmapBits(True)
    except ScreenshotError:
        raise
    except Exception as e:
        raise ScreenshotError(f"Window capture failed: {e}")
    finally:
        for obj in (bmp, save_dc, mfc_dc):
            try:
                if obj is not None:
                    obj.DeleteDC() if hasattr(obj, "DeleteDC") else win32gui.DeleteObject(obj.GetHandle())
            except Exception:
                pass
        try:
            if hwnd_dc is not None:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            pass

    # ── Convert bitmap to PIL Image ─────────────────────────────────────────
    try:
        img = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
        )
    except Exception as e:
        raise ScreenshotError(f"Failed to create PIL image: {e}")

    # ── Auto-crop to chart area ─────────────────────────────────────────────
    crop_box = _find_chart_bounds(hwnd, left, top, w, h)
    crop_l, crop_t, crop_r, crop_b = crop_box

    if crop_box != (0, 0, w, h):
        img = img.crop(crop_box)
        logger.info(
            f"Cropped to chart area: {crop_r - crop_l}×{crop_b - crop_t}px "
            f"(from {w}×{h}px full window)"
        )
    else:
        logger.info(f"No crop applied — using full window {w}×{h}px")

    # ── Save to file ────────────────────────────────────────────────────────
    try:
        os.makedirs(save_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(save_dir, f"mt4_{ts}.png")
        img.save(path)
        abs_path = os.path.abspath(path)
        logger.info(f"Screenshot saved: {abs_path} ({img.width}×{img.height}px)")
        return abs_path
    except Exception as e:
        raise ScreenshotError(f"Failed to save screenshot: {e}")
