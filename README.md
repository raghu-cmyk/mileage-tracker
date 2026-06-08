# Mileage Tracker

Single-user web app for IRS-grade mileage substantiation. This branch adds deduction calculation and year-end summary reporting (issue #5) on top of authentication, vehicles, trip management, and time-effective mileage rates (issues #1–#4).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Visit http://127.0.0.1:8000 — register the sole user, sign in, then manage vehicles and trips.

## Deduction calculation and year-end summary (issue #5)

- Per-trip deduction = `miles × resolved_rate` using exact integer-cent arithmetic (no floating-point drift)
- Year summary for a selected tax year shows total miles, miles by category, deductible total, business-use percentage, and late-entered trip count
- Personal-category miles are excluded from deductions and reported separately
- Business-use percentage = deductible miles ÷ total logged miles
- Ambiguous or missing rate resolution blocks calculation with an explicit error
- UI at `/summary`; JSON API at `/api/summary/{tax_year}`

## Trip categories and mileage rates (issue #4)

- Trip categories (`business`, `medical`, `moving`, `charitable`, `personal`) are seeded reference data with `is_deductible` flags
- IRS mileage rates are time-effective database records (`category_code`, `rate_cents_per_mile`, `effective_start_date`, `effective_end_date`); rates are never hardcoded in application logic
- Seeded IRS values: 2026 business 72.5¢, medical/moving 20.5¢, charitable 14¢; 2025 business 70¢
- `resolve_rate(category_code, trip_date)` returns exactly one matching rate or raises `RateResolutionError`
- Rate table is validated on startup for non-overlapping effective windows per category

## Health check

`GET /health` returns `{"status": "ok"}` without authentication.

## Tests

```bash
python -m unittest discover -s tests -v
```
