# Troubleshooting

## fiver: missing adb / scrcpy

```text
fiver --doctor
```

Install host packages for your OS (see README), then open a new terminal.

## unauthorized device

Unlock phone, replug USB, tap Allow.  
Developer options -> Revoke USB debugging authorizations, then try again.

## Can it work with USB debugging OFF?

Not for full control on stock Android. That is an OS security limit.
fiver will not fake or bypass it.

## Window closes / reconnect loop

Keep the server running (`fiver --status`). Check Wi-Fi or set `PHONE_IP`.
Lower quality if the link is weak:

```text
MAX_SIZE=1024
BITRATE=4M
MAX_FPS=30
AUDIO=false
```

## Command not found: fiver

```text
# after pip --user install
export PATH="$HOME/.local/bin:$PATH"
```

Or use `pipx ensurepath` and restart the shell.

## Logs

```text
tail -f ~/.local/state/fiver/fiver.log
```
