# Mileage Tracker

Single-user web app for IRS-grade mileage substantiation. This branch adds vehicle management and per-tax-year odometer tracking (issue #2) on top of session-based authentication (issue #1).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Visit http://127.0.0.1:8000 — register the sole user, sign in, then manage vehicles under **Vehicles**.

## Vehicle management (issue #2)

- Create, view, edit, and archive vehicles
- Record start-of-year and end-of-year odometer readings per vehicle per tax year
- Vehicles with trips cannot be hard-deleted (archive instead)
- Audit events recorded on vehicle and odometer mutations

## Health check

`GET /health` returns `{"status": "ok"}` without authentication.
