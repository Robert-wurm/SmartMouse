'use strict';

// ------------------------------------------------------------ Einstellungen
const SETTINGS = [
  { key: 'speed',   label: 'Geschwindigkeit', type: 'range', min: 0.3, max: 6,   step: 0.1, def: 1.6, fmt: v => v.toFixed(1) + '×' },
  { key: 'accel',   label: 'Beschleunigung',  type: 'range', min: 0,   max: 3,   step: 0.1, def: 1.0, fmt: v => v.toFixed(1),
    hint: 'Schnelle Bewegungen bringen den Zeiger weiter' },
  { key: 'scroll',  label: 'Scroll-Tempo',    type: 'range', min: 0.2, max: 5,   step: 0.1, def: 1.0, fmt: v => v.toFixed(1) + '×' },
  { key: 'natural', label: 'Natürliches Scrollen', type: 'check', def: true, hint: 'Inhalt folgt dem Finger, wie am Handy' },
  { key: 'padW',    label: 'Breite der Fläche', type: 'range', min: 30, max: 100, step: 1, def: 100, fmt: v => v + ' %' },
  { key: 'padH',    label: 'Höhe der Fläche',   type: 'range', min: 25, max: 100, step: 1, def: 100, fmt: v => v + ' %' },
  { key: 'split',   label: 'Grenze Links/Rechts', type: 'range', min: 20, max: 80, step: 1, def: 50, fmt: v => v + ' %',
    hint: 'Tippen links davon = Linksklick, rechts davon = Rechtsklick' },
  { key: 'tapMs',   label: 'Tipp-Dauer max.', type: 'range', min: 120, max: 400, step: 10, def: 230, fmt: v => v + ' ms' },
  { key: 'longpress', label: 'Lang drücken = Ziehen', type: 'check', def: true, hint: 'Linke Taste halten, solange der Finger liegt' },
  { key: 'voice',   label: 'Spracheingabe-Feld anzeigen', type: 'check', def: true,
    hint: 'Großes Feld oben: startet die Spracheingabe am PC (Windows: Win+H, Mac: Ctrl 2×)' },
  { key: 'buttons', label: 'Tastenleiste anzeigen', type: 'check', def: false, hint: 'Extra-Tasten unter der Fläche (auch Mitte)' },
  { key: 'haptic',  label: 'Vibration bei Klick', type: 'check', def: true },
  { key: 'autofs',  label: 'Vollbild beim ersten Tippen', type: 'check', def: true },
  { key: 'wake',    label: 'Bildschirm anlassen', type: 'check', def: true, hint: 'Funktioniert nur, wenn der Browser es erlaubt' },
];
const DEFAULTS = Object.fromEntries(SETTINGS.map(s => [s.key, s.def]));

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};

let S = { ...DEFAULTS };
try { Object.assign(S, JSON.parse(store.get('pm_settings') || '{}')); } catch {}
const saveSettings = () => store.set('pm_settings', JSON.stringify(S));

const $ = id => document.getElementById(id);
const pad = $('pad');

// ------------------------------------------------------------ Kopplung
let code = new URLSearchParams(location.search).get('code') || store.get('pm_code');
if (code) store.set('pm_code', code);

let pcInfo = null;   // { os, dictation } vom PC

async function checkCode(c) {
  try {
    const r = await fetch('/check?code=' + encodeURIComponent(c), { cache: 'no-store' });
    const j = await r.json();
    if (j.ok) { pcInfo = j; applyLayout(); setVoice(voiceLive); return 'ok'; }
    return j.error || 'Falscher Code';
  } catch {
    return 'offline';
  }
}

function showPair(msg = '') {
  $('pairView').classList.add('on');
  $('pairErr').textContent = msg;
  $('codeInput').value = '';
  setTimeout(() => $('codeInput').focus(), 50);
}

$('pairBtn').onclick = async () => {
  const c = $('codeInput').value.trim();
  if (!/^\d{6}$/.test(c)) { $('pairErr').textContent = 'Bitte 6 Ziffern eingeben'; return; }
  const res = await checkCode(c);
  if (res === 'ok') {
    code = c; store.set('pm_code', c);
    $('pairView').classList.remove('on');
    connect();
  } else {
    $('pairErr').textContent = res === 'offline' ? 'PC nicht erreichbar' : res;
  }
};
$('codeInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('pairBtn').click(); });

// ------------------------------------------------------------ Verbindung
let ws = null, retry = 0, retryTimer = null;

function setStatus(state, text) {
  $('dot').className = 'dot ' + (state === 'ok' ? 'ok' : state === 'wait' ? 'wait' : '');
  $('status').textContent = text;
}

async function connect() {
  clearTimeout(retryTimer);
  if (!code) { showPair(); return; }
  setStatus('wait', 'Verbinde…');
  const res = await checkCode(code);
  if (res !== 'ok' && res !== 'offline') { store.del('pm_code'); code = null; showPair(res); setStatus('', 'Nicht gekoppelt'); return; }
  if (res === 'offline') { scheduleRetry(); return; }

  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  ws = new WebSocket(proto + location.host + '/ws?code=' + encodeURIComponent(code));
  ws.onopen = () => { retry = 0; setStatus('ok', 'Verbunden'); };
  ws.onclose = () => { ws = null; scheduleRetry(); };
  ws.onerror = () => { try { ws.close(); } catch {} };
}

function scheduleRetry() {
  setStatus('', 'Getrennt – neuer Versuch…');
  clearTimeout(retryTimer);
  retryTimer = setTimeout(connect, Math.min(500 * 2 ** retry++, 5000));
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    if (!ws || ws.readyState > 1) connect();
    requestWake();
  }
});

// ------------------------------------------------------------ Senden
let mx = 0, my = 0, sx = 0, sy = 0, rafPending = false;

function sendNow(msgs) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(msgs));
}
function flush() {
  rafPending = false;
  const out = [];
  if (mx || my) { out.push({ t: 'm', x: +mx.toFixed(2), y: +my.toFixed(2) }); mx = my = 0; }
  if (sx || sy) { out.push({ t: 's', x: Math.round(sx), y: Math.round(sy) }); sx -= Math.round(sx); sy -= Math.round(sy); }
  if (out.length) sendNow(out);
}
function schedule() { if (!rafPending) { rafPending = true; requestAnimationFrame(flush); } }
function sendButton(t, b, n) {
  flush(); // Reihenfolge erhalten: erst Bewegung, dann Klick
  const m = { t, b }; if (n) m.n = n;
  sendNow([m]);
}
function buzz(ms = 12) { if (S.haptic && navigator.vibrate) try { navigator.vibrate(ms); } catch {} }

// ------------------------------------------------------------ Touchpad
const pts = new Map();          // pointerId -> Zustand
let maxPts = 0, startT = 0, travel = 0, dragging = false, lpTimer = null, startX = 0, startY = 0;
const MOVE_SLOP = 9;            // px, bis wohin ein Tippen noch ein Tippen ist

function ripple(x, y) {
  const r = pad.getBoundingClientRect();
  const el = document.createElement('div');
  el.className = 'ripple';
  el.style.left = (x - r.left) + 'px';
  el.style.top = (y - r.top) + 'px';
  pad.appendChild(el);
  setTimeout(() => el.remove(), 400);
}

function cancelLongPress() { clearTimeout(lpTimer); lpTimer = null; }

pad.addEventListener('pointerdown', e => {
  e.preventDefault();
  try { pad.setPointerCapture(e.pointerId); } catch {}
  pad.classList.add('active');
  maybeFullscreen();
  pts.set(e.pointerId, { x: e.clientX, y: e.clientY, t: e.timeStamp });
  if (pts.size === 1) {
    maxPts = 1; startT = e.timeStamp; travel = 0; startX = e.clientX; startY = e.clientY;
    if (S.longpress) {
      lpTimer = setTimeout(() => {
        if (pts.size === 1 && travel < MOVE_SLOP && !dragging) {
          dragging = true; pad.classList.add('dragging');
          sendButton('d', 'left'); buzz(30);
        }
      }, 450);
    }
  } else {
    maxPts = Math.max(maxPts, pts.size);
    cancelLongPress();
  }
});

pad.addEventListener('pointermove', e => {
  const p = pts.get(e.pointerId);
  if (!p) return;
  const dx = e.clientX - p.x, dy = e.clientY - p.y, dt = Math.max(e.timeStamp - p.t, 1);
  p.x = e.clientX; p.y = e.clientY; p.t = e.timeStamp;
  travel = Math.max(travel, Math.hypot(e.clientX - startX, e.clientY - startY));
  if (travel >= MOVE_SLOP) cancelLongPress();

  if (pts.size === 1 && maxPts === 1) {
    const v = Math.hypot(dx, dy) / dt;                    // px pro ms
    const g = S.speed * (1 + S.accel * Math.min(v, 3));
    mx += dx * g; my += dy * g;
    schedule();
  } else if (pts.size >= 2) {
    // Scrollen: Mittelwert aller Finger, 1 px Finger ≈ 4 Wheel-Einheiten
    const k = 4 * S.scroll / pts.size;
    const dir = S.natural ? 1 : -1;
    sy += dy * k * dir;
    sx += -dx * k * dir;
    schedule();
  }
});

function endPointer(e) {
  const p = pts.get(e.pointerId);
  if (!p) return;
  pts.delete(e.pointerId);
  if (pts.size > 0) return;
  cancelLongPress();
  const quick = e.timeStamp - startT <= S.tapMs;
  if (dragging) {
    dragging = false; pad.classList.remove('dragging');
    sendButton('u', 'left');
  } else if (e.type === 'pointerup' && quick && travel < MOVE_SLOP) {
    if (maxPts === 1) {
      const r = pad.getBoundingClientRect();
      const left = startX < r.left + r.width * S.split / 100;
      sendButton('c', left ? 'left' : 'right');
      ripple(startX, startY);
      buzz();
    } else if (maxPts === 2) {
      sendButton('c', 'right'); buzz();
    } else if (maxPts >= 3) {
      sendButton('c', 'middle'); buzz();
    }
  }
}
pad.addEventListener('pointerup', endPointer);
pad.addEventListener('pointercancel', endPointer);
pad.addEventListener('contextmenu', e => e.preventDefault());

// Tastenleiste (unabhängig vom Touchpad – erlaubt Halten + Bewegen mit zweitem Finger)
document.querySelectorAll('#btnBar button').forEach(btn => {
  const b = btn.dataset.b;
  const up = () => { if (btn.classList.contains('down')) { btn.classList.remove('down'); sendButton('u', b); } };
  btn.addEventListener('pointerdown', e => {
    e.preventDefault(); maybeFullscreen();
    try { btn.setPointerCapture(e.pointerId); } catch {}
    btn.classList.add('down'); sendButton('d', b); buzz();
  });
  btn.addEventListener('pointerup', up);
  btn.addEventListener('pointercancel', up);
  btn.addEventListener('contextmenu', e => e.preventDefault());
});

// ------------------------------------------------------------ Layout
function applyLayout() {
  const box = $('padBox');
  box.style.width = S.padW + '%';
  box.style.height = S.padH + '%';
  $('split').style.left = S.split + '%';
  $('btnBar').classList.toggle('on', !!S.buttons);
  // Spracheingabe nur zeigen, wenn der PC eine kennt (Windows/Mac)
  $('voice').classList.toggle('on', !!S.voice && !!(pcInfo && pcInfo.dictation));
}

// ------------------------------------------------------------ Spracheingabe
let voiceLive = false;
function setVoice(live) {
  voiceLive = live;
  $('voice').classList.toggle('live', live);
  const hint = pcInfo && pcInfo.dictation ? ` (${pcInfo.dictation})` : '';
  $('voiceSub').textContent = live ? 'Hört zu – tippen zum Beenden' : 'Tippen zum Starten' + hint;
}
$('voice').addEventListener('click', () => {
  maybeFullscreen();
  sendButtonless({ t: 'v' });
  buzz(25);
  setVoice(!voiceLive);
});
function sendButtonless(m) { flush(); sendNow([m]); }

// ------------------------------------------------------------ Vollbild / Wachhalten
const isStandalone = () =>
  matchMedia('(display-mode: fullscreen)').matches || matchMedia('(display-mode: standalone)').matches;
const isFs = () => !!(document.fullscreenElement || document.webkitFullscreenElement);

function enterFs() {
  const el = document.documentElement;
  const fn = el.requestFullscreen || el.webkitRequestFullscreen;
  if (fn) try { const r = fn.call(el, { navigationUI: 'hide' }); if (r && r.catch) r.catch(() => {}); } catch {}
}
function toggleFs() {
  if (isFs()) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
  else enterFs();
}
function maybeFullscreen() { if (S.autofs && !isFs() && !isStandalone()) enterFs(); }
$('fsBtn').onclick = toggleFs;

let wakeLock = null;
async function requestWake() {
  if (!S.wake || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
  try { wakeLock = await navigator.wakeLock.request('screen'); } catch { wakeLock = null; }
}
function releaseWake() { if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; } }

// ------------------------------------------------------------ Einstellungs-Panel
function buildSettings() {
  const list = $('settingsList');
  list.innerHTML = '';
  for (const s of SETTINGS) {
    const row = document.createElement('div');
    row.className = 'row';
    const hint = s.hint ? `<small>${s.hint}</small>` : '';
    if (s.type === 'range') {
      row.innerHTML = `<label><span>${s.label}</span><span class="val"></span></label>${hint}
        <input type="range" min="${s.min}" max="${s.max}" step="${s.step}">`;
      const inp = row.querySelector('input'), val = row.querySelector('.val');
      inp.value = S[s.key]; val.textContent = s.fmt(+S[s.key]);
      inp.oninput = () => { S[s.key] = +inp.value; val.textContent = s.fmt(+inp.value); saveSettings(); applyLayout(); };
    } else {
      row.innerHTML = `<label><span>${s.label}${hint}</span><input type="checkbox"></label>`;
      const inp = row.querySelector('input');
      inp.checked = !!S[s.key];
      inp.onchange = () => {
        S[s.key] = inp.checked; saveSettings(); applyLayout();
        if (s.key === 'wake') S.wake ? requestWake() : releaseWake();
      };
    }
    list.appendChild(row);
  }
}

$('setBtn').onclick = () => { buildSettings(); updateInstallTip(); $('sheet').classList.add('on'); };
$('closeSheet').onclick = () => $('sheet').classList.remove('on');
$('sheet').addEventListener('click', e => { if (e.target.id === 'sheet') $('sheet').classList.remove('on'); });
$('resetBtn').onclick = () => { S = { ...DEFAULTS }; saveSettings(); applyLayout(); buildSettings(); };
$('unpairBtn').onclick = () => {
  store.del('pm_code'); code = null;
  if (ws) ws.close();
  $('sheet').classList.remove('on');
  history.replaceState(null, '', '/');
  showPair();
};

// ------------------------------------------------------------ Als App installieren
let installEvt = null;
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEvt = e; });

function updateInstallTip() {
  const tip = $('installTip');
  tip.innerHTML = '';
  if (isStandalone()) { tip.textContent = 'Läuft als App.'; return; }
  if (installEvt) {
    const b = document.createElement('button');
    b.className = 'primary'; b.textContent = 'Als App installieren';
    b.onclick = async () => { installEvt.prompt(); await installEvt.userChoice; installEvt = null; updateInstallTip(); };
    tip.appendChild(b);
  } else {
    tip.textContent = 'Als App: im Browser-Menü (⋮) „Zum Startbildschirm hinzufügen“ wählen.';
  }
}

if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}

// ------------------------------------------------------------ Start
applyLayout();
requestWake();
connect();
