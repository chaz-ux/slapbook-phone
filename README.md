# SlapBook Phone Bridge 🎌📱

> Your phone becomes the accelerometer. No drivers, no hardware, no mic tricks.

## Why this works better than microphone mode

| Problem with mic mode | Phone bridge solution |
|---|---|
| Triggers on voice, claps, snaps | Phone accelerometer only feels **physical contact with the device** |
| Left/right side sensitivity difference | Phone sensor is uniform — same G-reading wherever you slap |
| Wall taps in same room trigger it | Wall is not connected to your phone. Not your problem. |
| Touchpad touch fires it | Touchpad vibration doesn't travel to the phone |
| Can't tell slap from environmental noise | Accelerometer literally measures force. No ambiguity. |

## How it works

```
[Phone] accelerometer reads G-force spike
    → browser sends data over WebSocket (WiFi)
        → laptop server receives spike
            → plays anime sound 🔊
```

The phone page is served **by the laptop** — you don't install anything on the phone. Just open a browser.

## Setup

### 1. Run setup once
```
python setup.py
```

### 2. Add sounds
Drop `.mp3` or `.wav` files into `sounds/yamete/` (or any other pack folder).  
Free sounds: **myinstants.com** → search `yamete`, `nani`, `baka`

### 3. Start the server
```
python server.py
```

### 4. Open on your phone
The server prints a URL like `https://192.168.1.42:8443`  
Open that in your phone browser. **Both devices must be on the same WiFi.**

### 5. Accept the certificate warning
This is a self-signed local cert — it's safe, just not signed by a big CA.
- **Android Chrome**: tap "Advanced" → "Proceed to site (unsafe)"
- **iPhone Safari**: tap "Show Details" → "visit this website" → "Visit"

You only do this once per device.

### 6. Tap "Enable Motion Sensor"
- **Android**: works immediately in Chrome
- **iPhone**: must use **Safari** (not Chrome). iOS Settings → Safari → Motion & Orientation Access must be ON.

### 7. Place phone on laptop and slap
Lay the phone flat on the laptop palm rest. Slap the laptop. The phone feels it.

## Sensitivity tuning

Edit `~/.slapbook/config.json` and change `"sensitivity"`:
- `1.0` = hair trigger (light taps)
- `1.5` = default
- `2.5` = only hard slaps

The phone page shows live delta G readings so you can see exactly what each slap produces.

## Firewall

Windows will ask to allow Python through the firewall the first time. Click **Allow**.  
If it doesn't ask, manually: Windows Defender Firewall → Allow an app → add Python, allow port 8443.

## Sounds folder structure

```
sounds/
├── yamete/    ← yamete kudasai, dame, yadda
├── tsundere/  ← baka, urusai, hmph
├── isekai/    ← nani, sugoi, kawaii
├── mecha/     ← impact SFX, explosions
├── combo/     ← plays on combos (optional)
└── custom/    ← anything
```