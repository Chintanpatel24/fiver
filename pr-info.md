# Fiver Wireless Companion App — Implementation Complete

## What Was Built

A complete **wireless screen mirroring** system that works **without USB debugging**. When a phone scans a QR code, it downloads a companion Android app that captures the screen and streams it live to the laptop over WiFi.

## New Files Created

| File | Purpose |
|------|---------|
| [`companion/__init__.py`](file:///home/cachy/github-p/fiver/src/fiver/companion/__init__.py) | Package marker |
| [`companion/AndroidManifest.xml`](file:///home/cachy/github-p/fiver/src/fiver/companion/AndroidManifest.xml) | Android app manifest with MediaProjection permissions |
| [`companion/MainActivity.java`](file:///home/cachy/github-p/fiver/src/fiver/companion/MainActivity.java) | Dark-themed UI, requests screen capture permission |
| [`companion/ScreenCaptureService.java`](file:///home/cachy/github-p/fiver/src/fiver/companion/ScreenCaptureService.java) | Foreground service: captures screen → JPEG → HTTP POST to laptop |
| [`apk_builder.py`](file:///home/cachy/github-p/fiver/src/fiver/apk_builder.py) | Auto-builds APK: finds/downloads SDK → javac → d8 → aapt2 → sign |

## Modified Files

| File | Changes |
|------|---------|
| [`web_mirror.py`](file:///home/cachy/github-p/fiver/src/fiver/web_mirror.py) | New `/download/companion.apk` endpoint, raw JPEG frame support, APK download page |
| [`tui.py`](file:///home/cachy/github-p/fiver/src/fiver/tui.py) | Companion app fallback when ADB fails: build APK → serve → show QR |
| [`pyproject.toml`](file:///home/cachy/github-p/fiver/pyproject.toml) | Include companion source files in package data |

## Complete Flow

```
User runs: fiver --setup-wifi
    │
    ▼
TUI scans WiFi → picks device → tries ADB connect
    │
    ▼  (ADB fails — no USB debugging)
APK Builder activates:
    ├── Checks for Android SDK tools
    ├── Auto-downloads SDK if missing (~1 min first time)
    ├── Embeds laptop IP into Java source
    ├── javac → d8 → aapt2 → apksigner
    └── Caches built APK
    │
    ▼
Web server starts → Cloudflare tunnel → QR code shown
    │
    ▼  (Phone scans QR)
Phone opens page → "DOWNLOAD & INSTALL" button
    │
    ▼  (User installs APK)
APK opens → "START SCREEN SHARE" button
    │
    ▼  (User taps "Start Now" on permission dialog)
ScreenCaptureService starts:
    ├── MediaProjection captures screen at 720p
    ├── JPEG frames at ~20 FPS, quality 60
    └── HTTP POST raw JPEG to laptop:8080/api/frame
    │
    ▼
Desktop browser shows live MJPEG stream at /desktop
```

## Required Dependencies

Before the APK can be built, you need **JDK** installed:

```bash
# Arch / CachyOS
sudo pacman -S jdk-openjdk

# Debian / Ubuntu
sudo apt install default-jdk

# Fedora
sudo dnf install java-latest-openjdk-devel
```

> [!IMPORTANT]
> The **Android SDK build-tools** and **platform** will be **auto-downloaded** on first use to `~/.fiver/sdk/`. No manual Android Studio setup needed.

## Key Design Decisions

- **View-only**: Laptop can see the phone screen but not control it (avoids Accessibility Service complexity)
- **JPEG over HTTP**: Simple, universal, ~15-25 FPS at 720p
- **Auto SDK install**: Downloads `commandlinetools` from Google, then uses `sdkmanager` to install `build-tools;34.0.0` and `platforms;android-34`
- **APK caching**: Built APKs are cached at `~/.fiver/apk/` keyed by server URL hash
- **No USB debugging required**: Uses Android's `MediaProjection` API which only needs user consent
