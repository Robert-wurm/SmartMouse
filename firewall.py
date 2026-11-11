"""Firewall-Freigabe, die sich SmartMouse selbst holt.

Beim ersten Start fragt die App einmal nach (eigene Erklärung + Windows-UAC „Ja“).
Freigegeben wird nur dieses Programm, nur der eigene Port und nur für Geräte
im lokalen Netz – unabhängig davon, ob Windows das Netz als „öffentlich“ führt.
"""
import base64
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes

RULE = "SmartMouse"
_NO_WINDOW = 0x08000000

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
_k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)


def own_exe() -> str:
    """Tatsächliche Programmdatei dieses Prozesses (bei venv: das echte pythonw.exe)."""
    buf = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buf))
    if _k32.QueryFullProcessImageNameW(_k32.GetCurrentProcess(), 0, buf, ctypes.byref(size)):
        return buf.value
    return sys.executable


def allowed(port: int) -> bool:
    """Gibt es schon eine SmartMouse-Freigabe für genau dieses Programm und diesen Port?"""
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE}", "verbose"],
            capture_output=True, creationflags=_NO_WINDOW, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False
    out = r.stdout.decode("oem", errors="ignore").lower()
    # Regeln stehen als Blöcke hintereinander – einer muss Programm UND Port passen
    for block in out.split("\r\n\r\n"):
        if own_exe().lower() in block and f" {port}\r\n" in block + "\r\n":
            return True
    return False


def ask() -> bool:
    text = (
        "Damit sich dein Handy mit SmartMouse verbinden kann, braucht die App "
        "einmalig deine Erlaubnis für Zugriffe aus deinem WLAN.\n\n"
        "Windows fragt gleich, ob du Änderungen zulassen möchtest – bitte mit „Ja“ bestätigen.\n\n"
        "Freigegeben wird nur SmartMouse und nur für Geräte in deinem eigenen Netz."
    )
    MB_OKCANCEL, MB_ICONINFORMATION, MB_SETFOREGROUND, MB_TOPMOST = 0x1, 0x40, 0x10000, 0x40000
    res = ctypes.windll.user32.MessageBoxW(
        None, text, "SmartMouse – Handy-Zugriff erlauben",
        MB_OKCANCEL | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST)
    return res == 1


def info(text: str):
    ctypes.windll.user32.MessageBoxW(None, text, "SmartMouse", 0x40 | 0x10000 | 0x40000)


class _SEI(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def grant(port: int) -> bool:
    """Legt die Freigabe mit Administratorrechten an (Windows fragt per UAC)."""
    exe = own_exe().replace("'", "''")
    script = f"""
$p = '{exe}'
# Alte Regeln dieses Programms (auch von Windows angelegte Sperren, die Vorrang hätten) ersetzen
Get-NetFirewallApplicationFilter | Where-Object {{ $_.Program -eq $p }} |
  Get-NetFirewallRule | Where-Object {{ $_.Direction -eq 'Inbound' }} | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName '{RULE}' -Description 'Smartphone als Maus' -Direction Inbound `
  -Action Allow -Protocol TCP -LocalPort {int(port)} -RemoteAddress LocalSubnet -Program $p -Profile Any | Out-Null
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    sei = _SEI()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = ps
    sei.lpParameters = f"-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {encoded}"
    sei.nShow = 0
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return False  # z. B. bei UAC auf „Nein“ geklickt
    if sei.hProcess:
        _k32.WaitForSingleObject(sei.hProcess, 60_000)
        _k32.CloseHandle(sei.hProcess)
    return allowed(port)


def ensure(port: int, interactive: bool = True) -> bool:
    """Prüft die Freigabe und fragt bei Bedarf nach. Gibt True zurück, wenn freigegeben."""
    if allowed(port):
        return True
    if not interactive or not ask():
        return False
    if grant(port):
        return True
    info("Die Freigabe hat nicht geklappt. Du kannst es später über das SmartMouse-Symbol "
         "unten rechts erneut versuchen („Handy-Zugriff erlauben…“).")
    return False
