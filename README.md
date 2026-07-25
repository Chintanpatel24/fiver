<pre align=center>

      ___                                  ___           ___     
     /  /\      ___           ___         /  /\         /  /\    
    /  /:/_    /  /\         /__/\       /  /:/_       /  /::\   
   /  /:/ /\  /  /:/         \  \:\     /  /:/ /\     /  /:/\:\  
  /  /:/ /:/ /__/::\          \  \:\   /  /:/ /:/_   /  /:/~/:/  
 /__/:/ /:/  \__\/\:\__   ___  \__\:\ /__/:/ /:/ /\ /__/:/ /:/___
 \  \:\/:/      \  \:\/\ /__/\ |  |:| \  \:\/:/ /:/ \  \:\/:::::/
  \  \::/        \__\::/ \  \:\|  |:|  \  \::/ /:/   \  \::/~~~~ 
   \  \:\        /__/:/   \  \:\__|:|   \  \:\/:/     \  \:\     
    \  \:\       \__\/     \__\::::/     \  \::/       \  \:\    
     \__\/                     ~~~~       \__\/         \__\/    

</pre>

# fiver

**fiver** is a simple terminal tool (Python) that runs a local server on your
computer so you can see and control **your** Android phone from the desktop.

```text
fiver --start     # start server
# plug phone, allow debugging once -> live control window
fiver --stop      # stop server
```

| | |
|---|---|
| License | MIT |
| Language | Python 3.9+ |
| Phone | Android 5.0+ |
| Host | Linux (any distro), macOS, Windows |
| Engine | scrcpy + adb |

## Important: Offline Operation & Beginner Options

### Offline & Auto-Reconnect
- **Zero Internet Required:** `fiver` connects directly over your local USB cable or local Wi-Fi router. It never needs an internet connection.
- **Offline Auto-Reconnect:** If your internet or Wi-Fi network drops, `fiver` continuously attempts background reconnection and immediately restores screen control when network connectivity returns.

### Phone Authorization & Beginner Options

Android security **does not allow** full remote screen control without one of two options:

1. **Option A (Built-in / Official - Recommended):** One-time USB debugging / Wireless setup.
   - Run `fiver --easy` for an interactive beginner wizard.
   - Enable USB Debugging once on phone -> Tap "Allow" on phone screen -> Wireless or USB control works instantly.
2. **Option B (Companion App / No Developer Mode):**
   - If you do not want to enable Developer options, install a local screen streaming app on your phone (e.g. Screen Stream or RustDesk) from Play Store / F-Droid to mirror over local Wi-Fi.

If any software claims full control of a stock phone with zero authorization or phone app, treat it as malware.

---

<img width="1308" height="759" alt="Blur_fiver" src="https://github.com/user-attachments/assets/4328f0a7-72a0-4d76-ad29-635caaa442af" />

## What you need

### Computer

| Tool | Why | Required |
|------|-----|----------|
| Python 3.9+ | runs fiver | Yes (to install) |
| **adb** | talks to the phone | Yes |
| **scrcpy** | live screen + mouse/keyboard | Yes |
| fiver | the server CLI | Yes |

### Phone

| Item | Required |
|------|----------|
| Android 5.0 or newer | Yes |
| USB debugging enabled (one-time) | Yes |
| Data USB cable for first trust | Yes |
| Wi-Fi or VPN for cable-free use | Optional |

iPhone is not supported.

---

## One-line install (from GitHub)

```bash
curl -fsSL https://raw.githubusercontent.com/Chintanpatel24/fiver/main/install.sh | bash
```

That script will:

1. Check Python 3.9+
2. Install fiver with `pipx` (or `pip install --user`)
3. Remind you to install `adb` + `scrcpy` if missing

### Install from a local clone

```bash
git clone https://github.com/Chintanpatel24/fiver.git
cd fiver
./install.sh
```

`install.sh` uses **pipx** when available, otherwise a user venv under
`~/.local/share/fiver-venv` and links `~/.local/bin/fiver` (works on Arch
and other PEP 668 distros without breaking system Python).

Manual options:

```bash
pipx install .
# or development:
python3 -m venv .venv && .venv/bin/pip install -e .
```

### Host tools (adb + scrcpy)

```bash
# Arch / CachyOS / Manjaro
sudo pacman -S scrcpy android-tools

# Debian / Ubuntu / Mint
sudo apt update && sudo apt install -y scrcpy adb

# Fedora
sudo dnf install -y scrcpy android-tools

# macOS
brew install scrcpy android-platform-tools

# Windows
winget install Genymobile.scrcpy Google.PlatformTools
```

---

## Easy daily use

```bash
fiver --doctor      # check setup
fiver --init        # create ~/.config/fiver/fiver.conf (optional)
fiver --start       # start background server
# unlock phone, plug USB, tap Allow once
fiver --status      # see if it is running
fiver --stop        # stop everything
```

### All common flags

| Command | Meaning |
|---------|---------|
| `fiver --easy` | Guided setup & auto-connect wizard (beginner-friendly) |
| `fiver --update` | Check for GitHub release/repo updates & install |
| `fiver --start` | Start server (background) |
| `fiver --start --fg` | Start in this terminal |
| `fiver --stop` | Stop server |
| `fiver --restart` | Restart server |
| `fiver --status` | Status + devices + log tail |
| `fiver --once` | One session, no daemon |
| `fiver --setup-wifi` | Enable wireless ADB while on USB |
| `fiver --doctor` | Dependency check |
| `fiver --init` | Write config file |
| `fiver --banner` | ASCII logo |
| `fiver --version` | Version |
| `fiver --help-android` | Short phone setup help |
| `fiver --help` | Full help |

Subcommands also work: `fiver start`, `fiver stop`, `fiver status`, ...

---

## Phone setup (one-time, ~1 minute)

```text
1. Settings -> About phone
2. Tap "Build number" 7 times
3. Open Developer options
4. Enable "USB debugging"
5. Run:  fiver --start
6. Unlock phone, plug USB, tap "Allow USB debugging"
```

Optional (Xiaomi and similar): enable **USB debugging (Security settings)**
so mouse/keyboard input is allowed.

More detail: [docs/ANDROID.md](docs/ANDROID.md)

---

## How it works (smooth server)

```text
  fiver --start
       |
       v
  [ waiting_for_device ]  <-- polls adb until phone is authorized
       |
       v
  [ preparing ]           <-- optional wireless handoff
       |
       v
  [ mirroring ]           <-- scrcpy window: live view + control
       |
       +--> disconnect / Wi-Fi blip
       |
       v
  [ reconnecting ]        <-- exponential backoff, remembers last IP
       |
       +--> phone back online -> mirroring again
       |
  fiver --stop  -> exit
```

Anti-glitch design:

- Single background process with a PID file
- Interruptible reconnect sleeps
- scrcpy stderr drained (no pipe stalls)
- Version-tolerant scrcpy flags (1.x and 2.x)
- H.264 preferred for broad Android compatibility
- Small video buffer when scrcpy supports it
- Clean SIGTERM shutdown

---

## Wireless and other networks

Same Wi-Fi after first USB trust:

```bash
fiver --setup-wifi
fiver --start
# cable can be unplugged
```

Different networks (home vs mobile data):

1. Put phone and PC on the same VPN (for example Tailscale)
2. Set in `~/.config/fiver/fiver.conf`:

```text
PHONE_IP=100.x.x.x
PREFER_WIRELESS=true
```

3. `fiver --restart`

Do not expose ADB port 5555 to the public internet.

---

## Configuration

```bash
fiver --init
# edit ~/.config/fiver/fiver.conf
```

Useful keys:

```text
MAX_SIZE=1280
BITRATE=8M
MAX_FPS=60
PREFER_WIRELESS=true
ADB_PORT=5555
PHONE_IP=
DEVICE_SERIAL=
LOG_LEVEL=info
```

Logs: `~/.local/state/fiver/fiver.log`

---

## Project layout

```text
fiver/
  src/fiver/          Python package (CLI + server)
  tests/              unit tests
  configs/            example config
  docs/               Android + troubleshooting
  install.sh          one-line installer
  pyproject.toml
  README.md
```

---

## Development

```bash
git clone https://github.com/Chintanpatel24/fiver.git
cd fiver
python3 -m pip install -e ".[dev]"
pytest -q
python3 -m fiver --help
```

---

## Security

- Only for devices you own or administer
- Requires the phone to show and accept a trust prompt
- Not a stealth RAT; do not use it that way
- See [SECURITY.md](SECURITY.md)

---

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

```bash
fiver --doctor
fiver --status
adb devices
tail -f ~/.local/state/fiver/fiver.log
```

---

## Credits

- [scrcpy](https://github.com/Genymobile/scrcpy) — mirror and control engine  
- Android platform-tools — `adb`

---

## License

[MIT](LICENSE)
