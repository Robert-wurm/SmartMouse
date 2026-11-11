# SmartMouse – Smartphone als Maus

Am PC läuft ein kleines Programm, am Handy öffnet man eine Website. Eine App aus dem Store ist nicht nötig.

## Starten

**Variante A – mit Python:** `start.bat` doppelklicken. Beim ersten Start wird eine eigene Umgebung eingerichtet.

**Variante B – als einzelne .exe:** einmal `build.ps1` ausführen, danach liegt `dist\SmartMouse.exe` bereit. Die Datei läuft auch auf PCs ohne Python.

SmartMouse läuft ohne Fenster im Hintergrund. Unten rechts im Infobereich (neben der Uhr, eventuell unter dem Pfeil ^) erscheint ein Maus-Symbol: **grau** = kein Handy verbunden, **blau** = verbunden. Ein Rechtsklick darauf öffnet das Menü:

- **Handy koppeln (QR-Code)** – öffnet die Kopplungsseite (auch per Doppelklick aufs Symbol)
- **Mit Windows starten** – Haken setzen, dann läuft die Maus nach jedem Neustart automatisch
- **Beenden**

Solange noch nie ein Handy verbunden war, öffnet sich beim Start automatisch eine Seite mit QR-Code. Scanne ihn mit dem Handy, das im selben WLAN sein muss. Alternativ öffnest du am Handy die angezeigte Adresse (z. B. `http://192.168.1.2:8765`) und gibst den 6-stelligen Code ein.

**Beim ersten Start** fragt SmartMouse einmal nach dem Handy-Zugriff: im Hinweisfenster **OK**, danach in der Windows-Rückfrage **Ja**. Die App legt dann selbst eine Firewall-Freigabe an. Sie gilt nur für SmartMouse, nur für den eigenen Port und nur für Geräte im eigenen Netz, und sie funktioniert auch, wenn Windows das Netz als „öffentlich“ führt. Wer abgelehnt hat, findet die Frage später im Menü am Symbol unter **„Handy-Zugriff erlauben…“**.

## Bedienung

| Geste | Wirkung |
|---|---|
| Ein Finger wischen | Maus bewegen |
| Tippen auf der linken Seite | Linksklick |
| Tippen auf der rechten Seite | Rechtsklick |
| Zwei Finger wischen | Scrollen (auch seitwärts) |
| Zwei Finger tippen | Rechtsklick |
| Drei Finger tippen | Mittelklick |
| Lang drücken, dann bewegen | Ziehen (linke Taste gehalten) |

### Spracheingabe

Das große Feld oben (etwa ein Drittel des Bildschirms) startet bzw. beendet die Spracheingabe des PCs. Vorher am PC in ein Textfeld klicken, dann ins Handy-Feld tippen und lossprechen. Die Sprache nimmt das Mikrofon des PCs auf.

- **Windows:** sendet **Win+H** (Windows-Spracheingabe). Klappt nichts, einmal in den Windows-Einstellungen unter „Zeit und Sprache → Spracherkennung“ nachsehen.
- **Mac:** sendet **zweimal Ctrl**. Dafür einmal einrichten: Systemeinstellungen → Tastatur → Diktat einschalten → Kurzbefehl **„Ctrl zweimal drücken“**. Die Standard-Taste Fn bzw. 🌐 kann keine Software zuverlässig auslösen. Auf dem Mac braucht SmartMouse außerdem die Berechtigung unter Datenschutz & Sicherheit → **Bedienungshilfen**.
- **Linux:** keine einheitliche Spracheingabe, das Feld wird ausgeblendet.

Das Feld lässt sich unter ⚙ → „Spracheingabe-Feld anzeigen“ abschalten.

Unter ⚙ lässt sich einstellen: Geschwindigkeit, Beschleunigung, Scroll-Tempo und -Richtung, Breite und Höhe der Fläche, wo die Grenze zwischen links und rechts liegt, wie lange ein Tippen dauern darf, Ziehen per langem Druck, eine zusätzliche Tastenleiste (Links/Mitte/Rechts), Vibration, automatisches Vollbild und ob der Bildschirm anbleibt. Die Werte werden am Handy gespeichert.

## Als App aufs Handy

Im Browser-Menü (⋮) **„Zum Startbildschirm hinzufügen“** wählen. Danach startet die Maus über ein eigenes Symbol. Beim ersten Tippen schaltet sie in den Vollbildmodus, ohne Browserleiste.

**Echte App ohne Browser-Rahmen (optional):** Chrome erlaubt „richtige“ Web-Apps nur über HTTPS, die Verbindung im Heimnetz ist aber HTTP. So geht es trotzdem:

1. Am Handy in Chrome `chrome://flags/#unsafely-treat-insecure-origin-as-secure` öffnen.
2. Die PC-Adresse eintragen, z. B. `http://192.168.1.2:8765`, auf **Enabled** stellen und Chrome neu starten.
3. Seite öffnen, dann ⚙ → **„Als App installieren“**.

Damit funktioniert auch „Bildschirm anlassen“ zuverlässig.

## Sicherheit

- Nur Geräte mit dem Code dürfen die Maus steuern. Nach 10 falschen Versuchen wird die IP für eine Minute gesperrt.
- Der Code bleibt über Neustarts gleich, damit die installierte App weiter funktioniert. Neuen Code erzeugen: `start.bat --new-code`. Danach am Handy ⚙ → „Kopplung lösen“.
- Gespeichert ist der Code unter `%APPDATA%\SmartMouse\config.json`.
- Nur im vertrauenswürdigen Heimnetz verwenden, die Verbindung ist nicht verschlüsselt.

## Optionen

```
start.bat --port 9000     anderer Port
start.bat --no-browser    Kopplungsseite nicht automatisch öffnen
start.bat --new-code      neuen Kopplungscode erzeugen
start.bat --console       wie früher im Konsolenfenster laufen (zum Fehlersuchen)
```

Meldungen im Hintergrundbetrieb landen in `%APPDATA%\SmartMouse\log.txt`.

## Aufbau

- `server.py` – Webserver (aiohttp): liefert die Seite aus, nimmt per WebSocket die Gesten entgegen und zeigt die Kopplungsseite `/pair` (nur am PC selbst abrufbar).
- `firewall.py` – prüft die Firewall-Freigabe (`netsh`, ohne Adminrechte) und legt sie bei Bedarf nach einmaliger UAC-Bestätigung an (Regel „SmartMouse“).
- `tray.py` – Symbol im Infobereich (pystray) und Autostart-Eintrag (`HKCU\…\Run`).
- `mouse_backend.py` – bewegt die Maus über Windows `SendInput` (unter macOS/Linux über `pynput`).
- `static/` – die Handy-Seite (`index.html`, `app.js`) samt Manifest, Service Worker und Icons.
