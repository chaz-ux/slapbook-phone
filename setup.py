"""
SlapBook Phone Bridge — setup.py
Run once before server.py
"""
import sys, subprocess
from pathlib import Path

PACKAGES = ["pygame-ce", "websockets"]
SOUNDS_DIR = Path(__file__).parent / "sounds"
PACKS = ["yamete", "tsundere", "isekai", "mecha", "combo", "custom"]

def install():
    print("\n── Installing packages ───────────────────────────────────")
    MODULE_MAP = {"pygame-ce": "pygame"}
    for pkg in PACKAGES:
        mod = MODULE_MAP.get(pkg, pkg)
        try:
            __import__(mod)
            # If pygame installed but old pygame (not ce), swap it
            if pkg == "pygame-ce":
                import importlib.metadata as m
                try:
                    m.version("pygame")
                    print(f"  🔄 Old pygame found → replacing with pygame-ce...")
                    subprocess.run([sys.executable,"-m","pip","uninstall","pygame","-y"],capture_output=True)
                    raise ImportError
                except m.PackageNotFoundError:
                    print(f"  ✅ {pkg} already installed")
            else:
                print(f"  ✅ {pkg} already installed")
        except ImportError:
            print(f"  📦 Installing {pkg}...")
            r = subprocess.run([sys.executable,"-m","pip","install",pkg], capture_output=True, text=True)
            print(f"  {'✅' if r.returncode==0 else '❌'} {pkg}")
            if r.returncode != 0: print(r.stderr[:200])

def folders():
    print("\n── Creating sound folders ────────────────────────────────")
    for p in PACKS:
        d = SOUNDS_DIR / p
        d.mkdir(parents=True, exist_ok=True)
        note = d / "_ADD_MP3_FILES_HERE.txt"
        if not note.exists():
            note.write_text(f"Drop .mp3 or .wav files here for the '{p}' sound pack.\n")
        print(f"  ✅ sounds/{p}/")

def openssl_check():
    print("\n── Checking OpenSSL (for HTTPS cert) ────────────────────")
    try:
        import subprocess
        r = subprocess.run(["openssl","version"], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  ✅ {r.stdout.strip()}")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        print("  ⚠️  openssl not found — will use Python 'cryptography' library instead")
        try:
            import cryptography
            print(f"  ✅ cryptography {cryptography.__version__} already installed")
        except ImportError:
            print("  📦 Installing cryptography...")
            subprocess.run([sys.executable,"-m","pip","install","cryptography"])

def instructions():
    print("""
── How to use ────────────────────────────────────────────

  1. Add .mp3 or .wav files to the sounds/ subfolders
     (free sounds: myinstants.com → search 'yamete', 'nani', etc.)

  2. Make sure your phone and laptop are on the SAME WiFi

  3. Run the server:
       python server.py

  4. Open the URL shown (https://YOUR_IP:8443) on your phone

  5. Your phone will warn about the certificate — tap:
       Android Chrome: "Advanced" → "Proceed to site (unsafe)"
       iPhone Safari:  "Show Details" → "visit this website" → "Visit"
     (This is normal for local self-signed certs. It's safe.)

  6. Tap "Enable Motion Sensor" on the phone page

  7. Place your phone flat on your laptop and SLAP!

── Troubleshooting ───────────────────────────────────────

  Phone can't reach the URL?
    → Both devices must be on the same WiFi network
    → Check Windows Firewall: allow Python on port 8443
      (Windows will ask automatically the first time)

  No sound?
    → Add .mp3 files to sounds/yamete/

  iOS: motion sensor not working?
    → Must use Safari (not Chrome) on iPhone
    → Settings > Safari > Motion & Orientation Access must be ON

  Android: works in Chrome directly, no extra steps needed

─────────────────────────────────────────────────────────
""")

print("╔══════════════════════════════════════════╗")
print("║   SlapBook Phone Bridge — Setup          ║")
print("╚══════════════════════════════════════════╝")
install()
folders()
openssl_check()
instructions()
print("✅  Setup complete! Run: python server.py")
print()