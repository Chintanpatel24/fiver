# Contributing

## Scope

Improvements to reliability, packaging, docs, and UX for consent-based
Android desk control.

## Not accepted

- Bypassing USB debugging or lock screens
- Stealth / RAT-style behavior
- Emojis in CLI output or README (project style)

## Develop

```text
python3 -m pip install -e ".[dev]"
pytest -q
python3 -m fiver --help
```
