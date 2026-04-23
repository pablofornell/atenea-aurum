"""MT4 window screenshot capture using Win32 API."""
import os
import logging
from datetime import datetime
from pathlib import Path

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


class ScreenshotError(Exception):
    """Screenshot capture failed."""
    pass


def find_mt4_hwnd(partial_title: str = "NMarkets") -> int:
    """Find MT4 window handle by partial title match.

    Args:
        partial_title: Partial window title to search for (case-insensitive)

    Returns:
        Window handle (hwnd)

    Raises:
        ScreenshotError if window not found
    """
    if not HAS_WIN32:
        raise ScreenshotError("pywin32 not installed. Install with: pip install pywin32")

    result = []

    def enum_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title.lower() in title.lower():
                result.append(hwnd)

    try:
        win32gui.EnumWindows(enum_callback, None)
    except Exception as e:
        raise ScreenshotError(f"Failed to enumerate windows: {e}")

    if not result:
        raise ScreenshotError(f"MT4 window not found (searched for '{partial_title}')")

    return result[0]  # Return first match


def capture_mt4(
    save_dir: str = "tmp/screenshots",
    partial_title: str = "NMarkets",
    restore_if_minimized: bool = True
) -> str:
    """Capture MT4 window screenshot using Win32 PrintWindow API.

    This method works even when MT4 is behind other windows, as it renders
    the window content directly from the process buffer (not screen capture).

    Args:
        save_dir: Directory to save screenshot PNG
        partial_title: Partial window title to match
        restore_if_minimized: Automatically restore minimized window

    Returns:
        Absolute path to saved PNG file

    Raises:
        ScreenshotError if capture fails
    """
    if not HAS_WIN32:
        raise ScreenshotError("pywin32 not installed. Install with: pip install pywin32")

    try:
        hwnd = find_mt4_hwnd(partial_title)
        logger.debug(f"Found MT4 window: hwnd={hwnd}")
    except ScreenshotError as e:
        raise ScreenshotError(f"Cannot find MT4 window: {e}")

    # Restore if minimized
    if restore_if_minimized:
        try:
            placement = win32gui.GetWindowPlacement(hwnd)
            if placement[1] == win32con.SW_SHOWMINIMIZED:
                logger.debug("MT4 window is minimized, restoring...")
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception as e:
            logger.warning(f"Could not restore window: {e}")

    # Get window rect
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w = right - left
        h = bottom - top
        if w <= 0 or h <= 0:
            raise ScreenshotError(f"Invalid window rect: ({w}x{h})")
        logger.debug(f"Window size: {w}x{h}")
    except Exception as e:
        raise ScreenshotError(f"Failed to get window rect: {e}")

    # Create device context for screenshot
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bmp)
    except Exception as e:
        raise ScreenshotError(f"Failed to create device context: {e}")

    # PrintWindow with PW_RENDERFULLCONTENT=2 (for GPU-rendered charts)
    # This flag tells MT4 to render itself to the memory buffer, independent
    # of whether it's covered by other windows.
    try:
        result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
        if result != 1:
            raise ScreenshotError(
                "PrintWindow failed (MT4 may be minimized or use incompatible rendering)"
            )
    except Exception as e:
        raise ScreenshotError(f"PrintWindow call failed: {e}")
    finally:
        # Cleanup device contexts
        try:
            bmpinfo = bmp.GetInfo()
            bmpstr = bmp.GetBitmapBits(True)
        except Exception as e:
            raise ScreenshotError(f"Failed to get bitmap data: {e}")
        finally:
            try:
                win32gui.DeleteObject(bmp.GetHandle())
                save_dc.DeleteDC()
                mfc_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                pass

    # Convert bitmap to PIL Image
    try:
        img = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1
        )
    except Exception as e:
        raise ScreenshotError(f"Failed to create image: {e}")

    # Save to file
    try:
        os.makedirs(save_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(save_dir, f"mt4_{ts}.png")
        img.save(path)
        abs_path = os.path.abspath(path)
        logger.info(f"Screenshot saved: {abs_path}")
        return abs_path
    except Exception as e:
        raise ScreenshotError(f"Failed to save screenshot: {e}")
