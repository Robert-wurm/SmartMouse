"""Symbol im Infobereich (unten rechts neben der Uhr) samt Autostart."""
import sys
import threading
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

APP_NAME = "SmartMouse"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

IDLE = (150, 156, 172, 255)        # grau: kein Handy verbunden
ACTIVE = (111, 143, 255, 255)      # blau: Handy verbunden


def make_icon(color) -> Image.Image:
    s = 64
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((14, 2, 50, 62), radius=18, fill=color)
    clear = (0, 0, 0, 0)  # ImageDraw überschreibt Pixel direkt → transparente Linien
    d.line((32, 4, 32, 26), fill=clear, width=4)
    d.line((14, 26, 50, 26), fill=clear, width=4)
    return img


# ------------------------------------------------------------------ Autostart
def _autostart_command() -> str:
    if getattr(sys, "frozen", False):  # gebaute .exe
        return f'"{sys.executable}" --autostart'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve().with_name("server.py")
    return f'"{pyw}" "{script}" --autostart'


def autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(on: bool):
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def refresh_autostart():
    """Falls der Ordner verschoben wurde: Autostart-Eintrag auf aktuellen Pfad setzen."""
    if autostart_enabled():
        set_autostart(True)


# ------------------------------------------------------------------ Tray
class Tray:
    def __init__(self, pair_url: str, phone_url: str, port: int, access_ok: bool = True):
        self.pair_url = pair_url
        self.phone_url = phone_url
        self.port = port
        self.access_ok = access_ok
        self.clients = 0
        self._lock = threading.Lock()
        self._icons = {False: make_icon(IDLE), True: make_icon(ACTIVE)}
        menu = pystray.Menu(
            pystray.MenuItem(lambda _: self._status(), None, enabled=False),
            pystray.MenuItem(
                "Handy-Zugriff erlauben…", self._grant_access,
                visible=lambda _: not self.access_ok,
            ),
            pystray.MenuItem("Handy koppeln (QR-Code)", self._open_pair, default=True),
            pystray.MenuItem(
                "Mit Windows starten",
                self._toggle_autostart,
                checked=lambda _: autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", self._quit),
        )
        self.icon = pystray.Icon(APP_NAME, self._icons[False], self._title(), menu)

    # --- Anzeige
    def _status(self) -> str:
        if not self.access_ok and self.clients == 0:
            return "Handy-Zugriff noch nicht erlaubt"
        if self.clients == 0:
            return "Kein Handy verbunden"
        return "1 Handy verbunden" if self.clients == 1 else f"{self.clients} Handys verbunden"

    def _title(self) -> str:
        return f"SmartMouse – {self._status()}\n{self.phone_url}"

    def _refresh(self):
        self.icon.icon = self._icons[self.clients > 0]
        self.icon.title = self._title()
        self.icon.update_menu()

    # --- vom Server aufgerufen (anderer Thread)
    def connected(self, ip: str):
        with self._lock:
            self.clients += 1
        self._refresh()

    def disconnected(self, ip: str):
        with self._lock:
            self.clients = max(0, self.clients - 1)
        self._refresh()

    # --- Menü
    def _grant_access(self, *_):
        import firewall
        threading.Thread(target=lambda: self._after_grant(firewall.ensure(self.port)), daemon=True).start()

    def _after_grant(self, ok: bool):
        self.access_ok = ok
        self._refresh()

    def _open_pair(self, *_):
        webbrowser.open(self.pair_url)

    def _toggle_autostart(self, *_):
        set_autostart(not autostart_enabled())
        self.icon.update_menu()

    def _quit(self, *_):
        self.icon.stop()

    def run(self):
        self.icon.run()  # blockiert bis „Beenden“
