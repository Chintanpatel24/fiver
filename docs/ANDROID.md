# Android setup for fiver

## Why USB debugging is required

Stock Android blocks apps and desktops from capturing the screen and injecting
touches unless:

- USB debugging / wireless debugging is enabled and the computer is trusted, or
- A phone app is granted MediaProjection (screen capture) by the user.

fiver uses the official **adb + scrcpy** path. That needs debugging enabled
once. After you tap Allow, daily use is just `fiver --start`.

## Steps

1. Settings -> About phone  
2. Tap **Build number** seven times  
3. Developer options -> enable **USB debugging**  
4. `fiver --start`  
5. Unlock phone, plug a data USB cable, tap **Allow**

## Brand notes

### Xiaomi / Redmi / POCO
Also enable **USB debugging (Security settings)** or input may not work.

### Samsung
Accept the RSA fingerprint dialog. Revoke authorizations if stuck.

### Oppo / Realme / OnePlus / Vivo
Enable any extra “USB debugging security” toggles. Keep the screen unlocked
for the first session.

## Wireless

```text
fiver --setup-wifi
```

Then unplug if phone and PC share Wi-Fi or a VPN.
