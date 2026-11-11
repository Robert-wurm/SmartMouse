"""SmartMouse – Smartphone als Maus.

Startet einen kleinen Webserver im Heimnetz. Das Handy öffnet die angezeigte
Adresse (oder scannt den QR-Code) und wird zum Touchpad.
"""
import argparse
import asyncio
import json
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from aiohttp import WSMsgType, web

import mouse_backend as mouse

APP_NAME = "SmartMouse"
DEFAULT_PORT = 8765


# ---------------------------------------------------------------- Pfade/Config
def resource_dir() -> Path:
    # PyInstaller entpackt Dateien nach sys._MEIPASS
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


STATIC = resource_dir() / "static"


def config_path() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(root) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p / "config.json"


def load_config() -> dict:
    p = config_path()
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    if not cfg.get("code"):
        cfg["code"] = f"{secrets.randbelow(10**6):06d}"
        save_config(cfg)
    return cfg


def save_config(cfg: dict):
    config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def lan_ips() -> list[str]:
    ips = []
    try:  # Adresse der Standardroute (ohne tatsächlich etwas zu senden)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    if not ips:
        return ["127.0.0.1"]
    default = ips[0]

    def rank(ip: str) -> int:
        a, b = (int(x) for x in ip.split(".")[:2])
        if a == 100 and 64 <= b <= 127:
            return 9          # Tailscale/CGNAT – nicht das Heim-WLAN
        bonus = 0 if ip == default else 1
        if a == 192 and b == 168:
            return 0 + bonus
        if a == 10:
            return 2 + bonus
        if a == 172 and 16 <= b <= 31:
            return 4 + bonus  # oft WSL/Hyper-V-Adapter
        return 6 + bonus

    return sorted(ips, key=rank)


# ------------------------------------------------------------------ Sicherheit
class RateLimiter:
    """Bremst Code-Raten aus: max. 10 Fehlversuche pro IP und Minute."""

    def __init__(self, limit=10, window=60):
        self.limit, self.window, self.fails = limit, window, {}

    def blocked(self, ip):
        now = time.monotonic()
        self.fails[ip] = [t for t in self.fails.get(ip, []) if now - t < self.window]
        return len(self.fails[ip]) >= self.limit

    def fail(self, ip):
        self.fails.setdefault(ip, []).append(time.monotonic())


# ------------------------------------------------------------- Mauszustand
class Session:
    def __init__(self):
        self.fx = self.fy = 0.0     # Nachkommareste der Bewegung
        self.sx = self.sy = 0.0     # Nachkommareste beim Scrollen
        self.held = set()

    def handle(self, m: dict):
        t = m.get("t")
        if t == "m":  # Bewegung
            self.fx += float(m.get("x", 0))
            self.fy += float(m.get("y", 0))
            ix, iy = int(self.fx), int(self.fy)
            if ix or iy:
                self.fx -= ix
                self.fy -= iy
                mouse.move(ix, iy)
        elif t == "s":  # Scrollen (Wheel-Einheiten, 120 = eine Raste)
            self.sy += float(m.get("y", 0))
            self.sx += float(m.get("x", 0))
            iy, ix = int(self.sy), int(self.sx)
            if iy or ix:
                self.sy -= iy
                self.sx -= ix
                mouse.scroll(iy, ix)
        elif t == "v":  # Spracheingabe des PCs starten/beenden
            mouse.dictate()
        elif t in ("c", "d", "u"):
            b = m.get("b", "left")
            if b not in mouse.BUTTONS:
                return
            if t == "c":
                mouse.click(b, max(1, min(int(m.get("n", 1)), 3)))
            elif t == "d" and b not in self.held:
                self.held.add(b)
                mouse.button(b, True)
            elif t == "u" and b in self.held:
                self.held.discard(b)
                mouse.button(b, False)

    def release_all(self):
        for b in list(self.held):
            mouse.button(b, False)
        self.held.clear()


# ------------------------------------------------------------------ Webserver
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}


def build_app(cfg: dict, urls: list[str], events=None) -> web.Application:
    """events: optionales Objekt mit connected(ip)/disconnected(ip) (z. B. das Tray-Symbol)."""
    code = cfg["code"]
    limiter = RateLimiter()
    app = web.Application()

    def serve(name: str) -> web.Response:
        path = STATIC / name
        if not path.is_file():
            raise web.HTTPNotFound()
        ctype = CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        return web.Response(
            body=path.read_bytes(),
            headers={"Content-Type": ctype, "Cache-Control": "no-cache"},
        )

    async def index(_):
        return serve("index.html")

    async def static_file(request):
        name = request.match_info["name"]
        if "/" in name or "\\" in name or name.startswith("."):
            raise web.HTTPNotFound()
        return serve(name)

    async def pair(request):
        # Kopplungsseite mit QR-Code – nur am PC selbst abrufbar
        if request.remote not in ("127.0.0.1", "::1"):
            raise web.HTTPForbidden()
        html = (STATIC / "pair.html").read_text(encoding="utf-8")
        main_url = f"{urls[0]}/?code={code}"
        block = (
            f'<div class="card"><div class="qr">{qr_svg(main_url)}</div>'
            f'<a href="{main_url}">{urls[0]}</a></div>'
        )
        others = ""
        if len(urls) > 1:
            items = "".join(f"<li>{u}/?code={code}</li>" for u in urls[1:])
            others = (
                '<details><summary>Klappt nicht? Andere Adressen dieses PCs</summary>'
                f"<ul>{items}</ul></details>"
            )
        html = (html.replace("{{CODE}}", code)
                    .replace("{{QRS}}", block)
                    .replace("{{OTHERS}}", others))
        return web.Response(text=html, content_type="text/html")

    async def ws_handler(request):
        ip = request.remote or "?"
        if limiter.blocked(ip):
            return web.Response(status=429, text="Zu viele Versuche")
        if request.query.get("code") != code:
            limiter.fail(ip)
            return web.Response(status=403, text="Falscher Code")

        ws = web.WebSocketResponse(heartbeat=15)
        await ws.prepare(request)
        print(f"  ✔ Verbunden: {ip}")
        if not cfg.get("ever_connected"):
            cfg["ever_connected"] = True
            save_config(cfg)
        if events:
            events.connected(ip)
        session = Session()
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    for m in data if isinstance(data, list) else [data]:
                        session.handle(m)
                except (ValueError, TypeError):
                    continue
        finally:
            session.release_all()
            print(f"  ✖ Getrennt:  {ip}")
            if events:
                events.disconnected(ip)
        return ws

    async def check(request):
        # Code-Prüfung für die Eingabemaske am Handy
        ip = request.remote or "?"
        if limiter.blocked(ip):
            return web.json_response({"ok": False, "error": "Zu viele Versuche"}, status=429)
        ok = request.query.get("code") == code
        if not ok:
            limiter.fail(ip)
            return web.json_response({"ok": False})
        # Infos für die Oberfläche: welches System, welche Spracheingabe
        os_name = {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")
        return web.json_response({"ok": True, "os": os_name, "dictation": mouse.DICTATION_HINT})

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/check", check)
    app.router.add_get("/pair", pair)
    app.router.add_get("/{name}", static_file)
    return app


def qr_svg(text: str) -> str:
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return "<p>(QR-Code: bitte 'pip install qrcode' ausführen)</p>"
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    return img.to_string(encoding="unicode")


def print_qr_terminal(text: str):
    try:
        import qrcode
    except ImportError:
        return
    q = qrcode.QRCode(border=1)
    q.add_data(text)
    q.make(fit=True)
    try:
        q.print_ascii(invert=True)
    except UnicodeEncodeError:
        pass


# -------------------------------------------------------------------- Start
def start_server_thread(app: web.Application, port: int) -> OSError | None:
    """Startet den Webserver im Hintergrund. Gibt einen Fehler zurück, falls der Port belegt ist."""
    ready = threading.Event()
    result: list = []

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        try:
            loop.run_until_complete(web.TCPSite(runner, "0.0.0.0", port).start())
        except OSError as e:
            result.append(e)
            ready.set()
            return
        ready.set()
        loop.run_forever()

    threading.Thread(target=run, name="webserver", daemon=True).start()
    ready.wait(10)
    return result[0] if result else None


def redirect_output_to_log():
    """Ohne Konsole (pythonw / .exe) gehen Meldungen in eine Logdatei."""
    if sys.stdout is None or sys.stderr is None:
        log = open(config_path().with_name("log.txt"), "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def main():
    ap = argparse.ArgumentParser(description="Smartphone als Maus")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true", help="Kopplungsseite nicht öffnen")
    ap.add_argument("--new-code", action="store_true", help="Neuen Kopplungscode erzeugen")
    ap.add_argument("--console", action="store_true", help="Im Konsolenfenster statt im Infobereich laufen")
    ap.add_argument("--autostart", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    redirect_output_to_log()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.new_code:
        config_path().unlink(missing_ok=True)
    cfg = load_config()
    urls = [f"http://{ip}:{args.port}" for ip in lan_ips()]
    pair_url = f"http://127.0.0.1:{args.port}/pair"

    if not args.console:
        run_tray(cfg, urls, pair_url, args)
        return

    print()
    print("  SmartMouse läuft")
    print("  ───────────────")
    print(f"  Am Handy öffnen:  {urls[0]}")
    print(f"  Code:             {cfg['code']}")
    print()
    print_qr_terminal(f"{urls[0]}/?code={cfg['code']}")
    print("  Beenden mit Strg+C\n")

    ensure_firewall(args)
    if not args.no_browser:
        webbrowser.open(pair_url)

    web.run_app(build_app(cfg, urls), host="0.0.0.0", port=args.port, print=None)


def ensure_firewall(args) -> bool:
    """Holt sich beim Start die Firewall-Freigabe (nicht beim stillen Autostart)."""
    if sys.platform != "win32":
        return True
    import firewall
    return firewall.ensure(args.port, interactive=not args.autostart)


def run_tray(cfg: dict, urls: list[str], pair_url: str, args):
    from tray import Tray, refresh_autostart

    access_ok = ensure_firewall(args)
    tray = Tray(pair_url, urls[0], args.port, access_ok)
    err = start_server_thread(build_app(cfg, urls, events=tray), args.port)
    if err:
        # Läuft schon (z. B. per Autostart) → einfach die Kopplungsseite zeigen
        print(f"Port {args.port} belegt: {err}")
        if not args.autostart:
            webbrowser.open(pair_url)
        return

    print(f"SmartMouse läuft im Infobereich: {urls[0]}  Code {cfg['code']}")
    refresh_autostart()
    # Kopplungsseite nur zeigen, solange noch nie ein Handy verbunden war
    if not (args.no_browser or args.autostart or cfg.get("ever_connected")):
        webbrowser.open(pair_url)
    tray.run()


if __name__ == "__main__":
    main()
