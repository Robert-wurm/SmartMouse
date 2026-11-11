"""Maussteuerung des Betriebssystems.

Windows: direkt über SendInput (ctypes, keine Zusatzpakete).
Andere Systeme: Fallback über pynput, falls installiert.
"""
import sys

BUTTONS = ("left", "right", "middle")


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    _INPUT_MOUSE = 0
    _MOVE = 0x0001
    _WHEEL = 0x0800
    _HWHEEL = 0x1000
    _FLAGS = {
        ("left", True): 0x0002, ("left", False): 0x0004,
        ("right", True): 0x0008, ("right", False): 0x0010,
        ("middle", True): 0x0020, ("middle", False): 0x0040,
    }

    _user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    _user32.SendInput.restype = wintypes.UINT

    def _send(flags, dx=0, dy=0, data=0):
        inp = _INPUT(type=_INPUT_MOUSE)
        inp.u.mi = _MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def move(dx: int, dy: int):
        _send(_MOVE, dx, dy)

    def button(name: str, down: bool):
        _send(_FLAGS[(name, down)])

    def scroll(dy: int, dx: int = 0):
        # dy > 0 = nach oben (Windows-Konvention), Einheit: 120 = eine Raste
        if dy:
            _send(_WHEEL, data=dy)
        if dx:
            _send(_HWHEEL, data=dx)

    _INPUT_KEYBOARD = 1
    _KEYUP = 0x0002
    _EXTENDED = 0x0001
    _VK_LWIN, _VK_H = 0x5B, 0x48

    def _key(vk: int, down: bool, extended: bool = False):
        flags = (0 if down else _KEYUP) | (_EXTENDED if extended else 0)
        inp = _INPUT(type=_INPUT_KEYBOARD)
        inp.u.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    DICTATION_HINT = "Win+H"

    def dictate():
        """Windows-Spracheingabe ein-/ausschalten (Win+H)."""
        _key(_VK_LWIN, True, extended=True)
        _key(_VK_H, True)
        _key(_VK_H, False)
        _key(_VK_LWIN, False, extended=True)

else:
    try:
        from pynput.mouse import Button, Controller
    except ImportError:  # pragma: no cover
        sys.exit("Auf diesem System bitte zuerst 'pip install pynput' ausführen.")

    _m = Controller()
    _B = {"left": Button.left, "right": Button.right, "middle": Button.middle}

    def move(dx: int, dy: int):
        _m.move(dx, dy)

    def button(name: str, down: bool):
        (_m.press if down else _m.release)(_B[name])

    def scroll(dy: int, dx: int = 0):
        _m.scroll(dx / 120, dy / 120)

    if sys.platform == "darwin":
        import time
        from pynput.keyboard import Controller as _KController, Key as _Key

        _kb = _KController()
        DICTATION_HINT = "Ctrl 2×"

        def dictate():
            """macOS-Diktat: Kurzbefehl in den Systemeinstellungen auf „Ctrl zweimal drücken“ stellen."""
            for _ in range(2):
                _kb.press(_Key.ctrl)
                _kb.release(_Key.ctrl)
                time.sleep(0.08)
    else:
        DICTATION_HINT = None  # Linux: keine einheitliche Systemspracheingabe

        def dictate():
            pass


def click(name: str, count: int = 1):
    for _ in range(count):
        button(name, True)
        button(name, False)
