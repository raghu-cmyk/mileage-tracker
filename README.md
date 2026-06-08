# Mileage Tracker

Single-user web application for IRS-substantiation-grade mileage logging.

## Authentication (Issue #1)

This branch implements the MVP authentication layer:

- Single registered user with one-time registration
- Argon2id password hashing
- Server-side session enforcement with explicit expiry and logout
- Login rate limiting (5 failed attempts per 5 minutes per client IP)
- Protected routes redirect unauthenticated users to login

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:8000 — register the sole user account, then sign in.

Set `ENFORCE_HTTPS=1` and a strong `SESSION_SECRET` in production.

## Health check

`GET /health` returns `{"status": "ok"}` without authentication.
