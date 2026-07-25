# Security policy

fiver is for owners and authorized admins of Android devices. It uses the
official USB debugging consent model.

## Rules of use

- Only accept debugging prompts on computers you trust
- Do not expose ADB port 5555 to the public internet
- Prefer a VPN (for example Tailscale) for cross-network use
- Stop when done: `fiver --stop`

## Not accepted

Stealth features, lock-screen bypass, or unauthorized remote access tooling.
