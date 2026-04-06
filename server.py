"""
SlapBook Phone Bridge — server.py
Runs on your laptop. Your phone opens the URL shown and becomes the accelerometer.

Install:
    pip install pygame-ce websockets

How it works:
    1. This script generates a self-signed HTTPS cert (first run only)
    2. Serves a webpage + WebSocket on https://YOUR_IP:8443
    3. Phone opens that URL, taps Enable, gets accelerometer access
    4. Phone streams G-force spikes → laptop plays anime sounds
"""

import asyncio
import json
import math
import os
import random
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

# ── Lazy imports (checked at runtime) ──────────────────────────
try:
    import websockets
except ImportError:
    print("❌  Missing: pip install websockets")
    sys.exit(1)

try:
    import pygame
    import pygame.mixer
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.mixer.init()
except ImportError:
    print("❌  Missing: pip install pygame-ce")
    sys.exit(1)

# ── Paths ───────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
SOUNDS_DIR = BASE_DIR / "sounds"
CERT_FILE  = BASE_DIR / "cert.pem"
KEY_FILE   = BASE_DIR / "key.pem"
CONFIG_FILE = Path.home() / ".slapbook" / "config.json"

DEFAULT_CONFIG = {
    "sensitivity":   0.2,   # G-spike above gravity to trigger (lower = easier)
    "cooldown":      1.0,
    "volume":        0.85,
    "pack":          "yamete",
    "combo_enabled": True,
    "combo_window":  2.5,
}

COMBO_NAMES = ["DOUBLE BAKA", "TRIPLE NANI", "QUAD SUGOI", "ULTRA COMBO!!", "YARE YARE..."]

# ── State ───────────────────────────────────────────────────────
class State:
    total     = 0
    session   = 0
    max_combo = 0
    combo     = 0
    last_time = 0.0
    clients   = set()   # connected websocket clients

state  = State()
config = {}

# ── Config ──────────────────────────────────────────────────────
def load_config():
    global config
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            config = {**DEFAULT_CONFIG, **saved}
            return
        except Exception:
            pass
    config = DEFAULT_CONFIG.copy()

def save_config():
    try:
        CONFIG_FILE.write_text(json.dumps(config, indent=2))
    except Exception:
        pass

def get_available_packs():
    """Scan the sounds folder and return list of available packs."""
    if not SOUNDS_DIR.exists():
        return ["yamete"]
    packs = [d.name for d in SOUNDS_DIR.iterdir() if d.is_dir()]
    return packs if packs else ["yamete"]

# ── Audio ───────────────────────────────────────────────────────
_cache: dict = {}

def get_sounds(pack: str) -> list:
    if pack in _cache:
        return _cache[pack]
    d = SOUNDS_DIR / pack
    if not d.exists():
        d = SOUNDS_DIR / "yamete"
    sounds = []
    for f in list(d.glob("*.mp3")) + list(d.glob("*.wav")):
        try:
            sounds.append(pygame.mixer.Sound(str(f)))
        except Exception:
            pass
    _cache[pack] = sounds
    return sounds

def play(intensity: float):
    sounds = get_sounds(config["pack"])
    if not sounds:
        print(f"  ⚠️  No sounds in sounds/{config['pack']}/ — add .mp3 files")
        return
    s = random.choice(sounds)
    vol = min(1.0, 0.35 + 0.65 * intensity) * config["volume"]
    s.set_volume(vol)
    s.play()

# ── Slap handler ────────────────────────────────────────────────
def handle_slap(g_spike: float):
    now   = time.time()
    intensity = min(1.0, g_spike / (config["sensitivity"] * 2.5))

    if config["combo_enabled"] and (now - state.last_time) < config["combo_window"]:
        state.combo += 1
    else:
        state.combo  = 1

    state.total    += 1
    state.session  += 1
    state.last_time = now
    state.max_combo = max(state.max_combo, state.combo)

    combo_name = ""
    if state.combo >= 2:
        combo_name = COMBO_NAMES[min(state.combo - 2, len(COMBO_NAMES) - 1)]

    play(intensity)

    bar = "█" * int(intensity * 20)
    tag = f"  💥 {combo_name}" if combo_name else ""
    print(f"  SLAP! {g_spike:.2f}G  [{bar:<20}]  #{state.session}{tag}")

    # Push stats update to all connected phone clients
    msg = json.dumps({
        "type":     "stats",
        "total":    state.total,
        "session":  state.session,
        "combo":    state.combo,
        "maxCombo": state.max_combo,
        "intensity": round(intensity, 3),
        "comboName": combo_name,
    })
    asyncio.get_event_loop().call_soon_threadsafe(
        lambda: asyncio.ensure_future(_broadcast(msg))
    )

async def _broadcast(msg: str):
    dead = set()
    for ws in state.clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    state.clients -= dead

# ── SSL cert (auto-generated, self-signed) ──────────────────────
def ensure_cert():
    if CERT_FILE.exists() and KEY_FILE.exists():
        return
    print("🔐  Generating self-signed HTTPS cert (first run only)...")
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE),
            "-out",    str(CERT_FILE),
            "-days",   "3650",
            "-nodes",
            "-subj",   "/CN=slapbook",
        ], check=True, capture_output=True)
        print("✅  Cert generated.")
    except FileNotFoundError:
        # openssl not available — use Python's cryptography module
        _gen_cert_python()
    except subprocess.CalledProcessError as e:
        print(f"❌  openssl failed: {e.stderr.decode()[:200]}")
        _gen_cert_python()

def _gen_cert_python():
    """Fallback: generate cert using cryptography library."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
    except ImportError:
        print("❌  Install openssl OR: pip install cryptography")
        sys.exit(1)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "slapbook")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("slapbook")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    KEY_FILE.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print("✅  Cert generated via Python cryptography library.")

# ── Phone webpage ────────────────────────────────────────────────
def build_html(ip: str, port: int) -> str:
    ws_url = f"wss://{ip}:{port}/ws"
    
    # Generate the dropdown options based on actual folders
    packs = get_available_packs()
    current_pack = config.get("pack", "yamete")
    pack_options = "".join(
        f'<option value="{p}" {"selected" if p == current_pack else ""}>{p.upper()}</option>' 
        for p in packs
    )
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>SlapBook Remote</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0f0f1a;
    color: #e8e8f0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 16px;
    -webkit-user-select: none;
  }}

  h1 {{ color: #ff5079; font-size: 2rem; margin-bottom: 4px; }}
  .sub {{ color: #6b6b8a; font-size: 0.85rem; margin-bottom: 28px; }}

  .pack-selector {{
    margin-bottom: 24px;
    text-align: center;
    width: 100%;
    max-width: 320px;
  }}
  .pack-selector label {{
    display: block;
    color: #6b6b8a;
    font-size: 0.8rem;
    margin-bottom: 5px;
    font-weight: bold;
  }}
  .pack-selector select {{
    width: 100%;
    padding: 10px;
    background: #1a1a2e;
    color: #ff5079;
    border: 2px solid #ff5079;
    border-radius: 10px;
    font-size: 1rem;
    font-weight: bold;
    text-align: center;
    outline: none;
  }}

  #enableBtn {{
    background: #ff5079;
    color: white;
    border: none;
    border-radius: 16px;
    font-size: 1.1rem;
    font-weight: 700;
    padding: 18px 40px;
    cursor: pointer;
    width: 100%;
    max-width: 320px;
    margin-bottom: 24px;
    transition: opacity .15s;
    -webkit-tap-highlight-color: transparent;
  }}
  #enableBtn:active {{ opacity: .75; }}
  #enableBtn:disabled {{ background: #333355; cursor: default; opacity: 1; }}

  .status-pill {{
    display: inline-block;
    padding: 6px 16px;
    border-radius: 99px;
    font-size: 0.8rem;
    font-weight: 700;
    margin-bottom: 24px;
    background: #1a1a2e;
    color: #6b6b8a;
  }}
  .status-pill.connected {{ background: #0a2a1a; color: #50ff90; }}
  .status-pill.ready     {{ background: #1a1a2e; color: #7eb8ff; }}
  .status-pill.error     {{ background: #2a0a0a; color: #ff5050; }}

  .stats-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 10px;
    width: 100%;
    max-width: 380px;
    margin-bottom: 20px;
  }}
  .stat-card {{
    background: #1a1a2e;
    border-radius: 14px;
    padding: 14px 8px;
    text-align: center;
  }}
  .stat-card .label {{ color: #6b6b8a; font-size: 0.65rem; margin-bottom: 4px; font-weight: 700; letter-spacing: .05em; }}
  .stat-card .value {{ font-size: 1.8rem; font-weight: 800; color: #ff5079; }}
  .stat-card .value.blue {{ color: #7eb8ff; }}
  .stat-card .value.gold {{ color: #ffd700; }}

  #bar-wrap {{
    width: 100%;
    max-width: 380px;
    background: #111122;
    border-radius: 10px;
    height: 18px;
    overflow: hidden;
    margin-bottom: 8px;
  }}
  #bar {{
    height: 100%;
    width: 0%;
    background: #ff5079;
    border-radius: 10px;
    transition: width .08s, background .08s;
  }}

  #combo-msg {{
    font-size: 1.1rem;
    font-weight: 800;
    color: #ffd700;
    min-height: 1.6rem;
    text-align: center;
    margin-bottom: 16px;
  }}

  .tip {{
    color: #444466;
    font-size: 0.78rem;
    text-align: center;
    max-width: 320px;
    line-height: 1.6;
    margin-top: auto;
    padding-top: 24px;
  }}

  #g-display {{
    color: #6b6b8a;
    font-size: 0.78rem;
    margin-bottom: 16px;
    font-variant-numeric: tabular-nums;
    min-height: 1.2em;
  }}
</style>
</head>
<body>

<h1>SlapBook</h1>
<p class="sub">Phone Accelerometer Bridge</p>

<div class="pack-selector">
  <label for="packSelect">CURRENT SOUND PACK</label>
  <select id="packSelect" onchange="changePack()">
    {pack_options}
  </select>
</div>

<button id="enableBtn" onclick="enable()">Enable Motion Sensor</button>
<div id="status" class="status-pill">Not connected</div>

<div class="stats-grid">
  <div class="stat-card">
    <div class="label">TOTAL</div>
    <div class="value" id="total">0</div>
  </div>
  <div class="stat-card">
    <div class="label">SESSION</div>
    <div class="value blue" id="session">0</div>
  </div>
  <div class="stat-card">
    <div class="label">MAX COMBO</div>
    <div class="value gold" id="maxCombo">0</div>
  </div>
</div>

<div id="bar-wrap"><div id="bar"></div></div>
<div id="g-display"></div>
<div id="combo-msg"></div>

<p class="tip">
  Place your phone flat on your laptop.<br>
  Slap the laptop — the phone's accelerometer detects the impact<br>
  and your laptop plays the sound.<br><br>
  Voice, claps and snaps won't trigger it — only physical contact with the device.
</p>

<script>
const WS_URL = "{ws_url}";
const THRESHOLD  = {config.get('sensitivity', 0.2)};  // G-spike to trigger
const COOLDOWN   = {config.get('cooldown', 1.0) * 1000};  // ms

let ws           = null;
let lastTrigger  = 0;
let motionActive = false;
let wsReady      = false;

// ── UI helpers ─────────────────────────────────────────────────
function setStatus(text, cls) {{
  const el = document.getElementById('status');
  el.textContent = text;
  el.className = 'status-pill ' + (cls || '');
}}

function updateStats(d) {{
  document.getElementById('total').textContent    = d.total;
  document.getElementById('session').textContent  = d.session;
  document.getElementById('maxCombo').textContent = d.maxCombo;

  const bar = document.getElementById('bar');
  const pct = Math.min(100, Math.round(d.intensity * 100));
  bar.style.width = pct + '%';
  bar.style.background = d.intensity < 0.5 ? '#ff5079'
                       : d.intensity < 0.85 ? '#ffd700' : '#ff0040';

  const gEl = document.getElementById('g-display');
  gEl.textContent = ''; // cleared — info comes from motion event

  if (d.comboName) {{
    const msg = document.getElementById('combo-msg');
    msg.textContent = d.comboName;
    clearTimeout(window._comboTimer);
    window._comboTimer = setTimeout(() => msg.textContent = '', 2000);
  }}
}}

// ── Pack selector ──────────────────────────────────────────────
function changePack() {{
  const newPack = document.getElementById('packSelect').value;
  if (ws && ws.readyState === WebSocket.OPEN) {{
    ws.send(JSON.stringify({{ type: 'set_pack', pack: newPack }}));
  }}
}}

// ── WebSocket ──────────────────────────────────────────────────
function connectWS() {{
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {{
    wsReady = true;
    if (motionActive) setStatus('🟢 Connected & Ready', 'connected');
    else               setStatus('WS connected — tap Enable', 'ready');
  }};

  ws.onclose = () => {{
    wsReady = false;
    setStatus('Reconnecting...', 'error');
    setTimeout(connectWS, 2000);
  }};

  ws.onerror = () => {{
    wsReady = false;
    setStatus('Connection error', 'error');
  }};

  ws.onmessage = (evt) => {{
    try {{
      const d = JSON.parse(evt.data);
      if (d.type === 'stats') updateStats(d);
      if (d.type === 'config') {{
        // Server can push updated config (threshold etc.)
        if (d.sensitivity) window._threshold = d.sensitivity;
      }}
    }} catch(e) {{}}
  }};
}}

// ── Motion ─────────────────────────────────────────────────────
function startMotion() {{
  window.addEventListener('devicemotion', onMotion);
  motionActive = true;
  if (wsReady) setStatus('🟢 Connected & Ready', 'connected');
  else          setStatus('Motion on — connecting...', 'ready');
  document.getElementById('enableBtn').textContent = '✅ Motion Active';
  document.getElementById('enableBtn').disabled = true;
}}

let _lastX = 0, _lastY = 0, _lastZ = 0;

function onMotion(e) {{
  // Use accelerationIncludingGravity — more widely supported, non-null on more devices
  const a = e.accelerationIncludingGravity || e.acceleration;
  if (!a) return;

  const x = a.x || 0, y = a.y || 0, z = a.z || 0;

  // Delta acceleration (change from last frame) — gravity cancels out
  // A resting phone has constant gravity vector; a slap creates a sudden spike
  const dx = x - _lastX, dy = y - _lastY, dz = z - _lastZ;
  _lastX = x; _lastY = y; _lastZ = z;

  const spike = Math.sqrt(dx*dx + dy*dy + dz*dz);

  // Update live G display
  document.getElementById('g-display').textContent =
    `Δ ${{spike.toFixed(2)}} m/s²  |  threshold: ${{(window._threshold||THRESHOLD).toFixed(1)}}`;

  const now = Date.now();
  const thresh = (window._threshold || THRESHOLD) * 9.81; // convert G to m/s²

  if (spike > thresh && (now - lastTrigger) > COOLDOWN) {{
    lastTrigger = now;
    if (ws && ws.readyState === WebSocket.OPEN) {{
      ws.send(JSON.stringify({{
        type:  'slap',
        spike: parseFloat((spike / 9.81).toFixed(3)), // send as G
      }}));
    }}
  }}
}}

// ── Permission flow ────────────────────────────────────────────
function enable() {{
  if (typeof DeviceMotionEvent !== 'undefined' &&
      typeof DeviceMotionEvent.requestPermission === 'function') {{
    // iOS 13+: must request permission
    DeviceMotionEvent.requestPermission()
      .then(state => {{
        if (state === 'granted') startMotion();
        else setStatus('Permission denied — check iOS Settings > Safari', 'error');
      }})
      .catch(err => setStatus('Permission error: ' + err, 'error'));
  }} else if (typeof DeviceMotionEvent !== 'undefined') {{
    // Android / other: no permission needed
    startMotion();
  }} else {{
    setStatus('DeviceMotion not supported on this browser', 'error');
  }}
}}

// ── Boot ───────────────────────────────────────────────────────
window._threshold = THRESHOLD;
connectWS();
</script>
</body>
</html>
"""

# ── WebSocket handler ────────────────────────────────────────────
async def ws_handler(websocket):
    state.clients.add(websocket)
    path = getattr(websocket, 'request', None)
    print(f"  📱  Phone connected: {websocket.remote_address[0]}")
    try:
        # Send current config so phone uses up-to-date threshold
        await websocket.send(json.dumps({
            "type":        "config",
            "sensitivity": config["sensitivity"],
            "cooldown":    config["cooldown"],
        }))
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                
                # Handle pack change from phone
                if msg.get("type") == "set_pack":
                    config["pack"] = msg.get("pack")
                    save_config()
                    print(f"  🗂️  Sound pack changed to: {config['pack']}")

                if msg.get("type") == "slap":
                    spike = float(msg.get("spike", 0))
                    if spike > config["sensitivity"]:
                        handle_slap(spike)
            except Exception:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        state.clients.discard(websocket)
        print("  📵  Phone disconnected")

# ── HTTP handler (serves the phone webpage) ──────────────────────
import websockets.http11
import websockets.datastructures

async def http_handler(connection, request):
    """Serve the phone HTML on GET /  everything else → 404."""
    
    # 1. Let websocket connections pass through
    if request.path == "/ws":
        return None  

    # 2. Serve the webpage
    if request.path in ("/", "/index.html"):
        ip   = get_local_ip()
        port = 8443
        html = build_html(ip, port).encode("utf-8")
        
        # Wrap the list in a proper Headers object so the library can modify it!
        headers = websockets.datastructures.Headers([
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(html))),
            ("Cache-Control", "no-store")
        ])
        
        return websockets.http11.Response(
            status_code=200,
            reason_phrase="OK",
            headers=headers,
            body=html,
        )
        
    # 3. Reject anything else
    return websockets.http11.Response(
        status_code=404,
        reason_phrase="Not Found",
        headers=websockets.datastructures.Headers(),
        body=b"Not found"
    )

# ── Network helpers ──────────────────────────────────────────────
def get_local_ip() -> str:
    """Get the LAN IP so the phone URL is correct."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

# ── Main ─────────────────────────────────────────────────────────
async def main():
    load_config()
    ensure_cert()

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(CERT_FILE, KEY_FILE)

    ip   = get_local_ip()
    port = 8443

    print()
    print("=" * 56)
    print("  SlapBook Phone Bridge  🎌")
    print("=" * 56)
    print()
    print(f"  📱  Open this on your phone:")
    print()
    print(f"        https://{ip}:{port}")
    print()
    print("  ⚠️   Your phone will warn about the certificate.")
    print("       Tap 'Advanced' → 'Proceed' (or 'Visit site').")
    print("       This is normal for local self-signed certs.")
    print()
    print(f"  🔊  Sounds folder:  {SOUNDS_DIR}")
    print(f"  ⚙️   Config:         {CONFIG_FILE}")
    print()
    print("  Waiting for phone to connect...")
    print("-" * 56)

    async with websockets.serve(
        ws_handler,
        "0.0.0.0",
        port,
        ssl=ssl_ctx,
        process_request=http_handler,
    ):
        await asyncio.Future()   # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        save_config()
        print("\n  Bye! 👋")