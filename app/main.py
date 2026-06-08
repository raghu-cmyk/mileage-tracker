import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .auth import (
    authenticate_user,
    clear_session,
    create_user,
    establish_session,
    get_current_user_id,
    get_user_count,
    require_authenticated_user,
)
from .database import Base, engine, get_db
from .exceptions import MileageTrackerError
from .models import User
from .vehicles import (
    archive_vehicle,
    create_vehicle,
    delete_vehicle,
    get_vehicle,
    list_odometer_readings,
    list_vehicles,
    update_vehicle,
    upsert_odometer_reading,
    vehicle_has_trips,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Mileage Tracker", version="0.2.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-only-change-in-production"),
    session_cookie="mileage_session",
    max_age=3600,
    same_site="lax",
    https_only=os.environ.get("ENFORCE_HTTPS", "0") == "1",
)
if os.environ.get("ENFORCE_HTTPS", "0") == "1":
    app.add_middleware(HTTPSRedirectMiddleware)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _redirect_with_error(url: str, error: str) -> RedirectResponse:
    from urllib.parse import quote

    return RedirectResponse(url=f"{url}?error={quote(error)}", status_code=303)


def _require_user_or_redirect(request: Request, db: Session) -> Union[User, RedirectResponse]:
    if get_current_user_id(request) is None:
        return RedirectResponse(url="/login", status_code=303)
    return require_authenticated_user(request, db)


@app.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicles = list_vehicles(db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "title": "Dashboard", "vehicles": vehicles},
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user_id(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "title": "Login",
            "registration_open": get_user_count(db) == 0,
            "error": request.query_params.get("error"),
        },
    )


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password, _client_key(request))
    establish_session(request, user.id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user_id(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    if get_user_count(db) >= 1:
        return RedirectResponse(url="/login?error=Registration+is+closed", status_code=303)
    return templates.TemplateResponse(
        request,
        "register.html",
        {"title": "Register", "error": request.query_params.get("error")},
    )


@app.post("/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != confirm_password:
        return RedirectResponse(url="/register?error=Passwords+do+not+match", status_code=303)
    if len(password) < 8:
        return RedirectResponse(
            url="/register?error=Password+must+be+at+least+8+characters",
            status_code=303,
        )
    user = create_user(db, username, password)
    establish_session(request, user.id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    clear_session(request)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/vehicles", response_class=HTMLResponse)
def vehicles_list(request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    show_archived = request.query_params.get("archived") == "1"
    vehicles = list_vehicles(db, include_archived=show_archived)
    return templates.TemplateResponse(
        request,
        "vehicles_list.html",
        {
            "user": user,
            "title": "Vehicles",
            "vehicles": vehicles,
            "show_archived": show_archived,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@app.get("/vehicles/new", response_class=HTMLResponse)
def vehicles_new_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        request,
        "vehicle_form.html",
        {"user": user, "title": "Add Vehicle", "vehicle": None, "error": request.query_params.get("error")},
    )


@app.post("/vehicles/new")
def vehicles_new_submit(
    request: Request,
    display_name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    try:
        vehicle = create_vehicle(db, display_name=display_name, description=description)
    except MileageTrackerError as exc:
        return _redirect_with_error("/vehicles/new", exc.message)
    return RedirectResponse(url=f"/vehicles/{vehicle.id}?success=Vehicle+created", status_code=303)


@app.get("/vehicles/{vehicle_id}", response_class=HTMLResponse)
def vehicle_detail(vehicle_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle is None:
        return RedirectResponse(url="/vehicles?error=Vehicle+not+found", status_code=303)
    readings = list_odometer_readings(db, vehicle.id)
    return templates.TemplateResponse(
        request,
        "vehicle_detail.html",
        {
            "user": user,
            "title": vehicle.display_name,
            "vehicle": vehicle,
            "readings": readings,
            "has_trips": vehicle_has_trips(db, vehicle.id),
            "current_tax_year": datetime.now().year,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@app.get("/vehicles/{vehicle_id}/edit", response_class=HTMLResponse)
def vehicle_edit_page(vehicle_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle is None:
        return RedirectResponse(url="/vehicles?error=Vehicle+not+found", status_code=303)
    return templates.TemplateResponse(
        request,
        "vehicle_form.html",
        {
            "user": user,
            "title": f"Edit {vehicle.display_name}",
            "vehicle": vehicle,
            "error": request.query_params.get("error"),
        },
    )


@app.post("/vehicles/{vehicle_id}/edit")
def vehicle_edit_submit(
    vehicle_id: int,
    request: Request,
    display_name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle is None:
        return RedirectResponse(url="/vehicles?error=Vehicle+not+found", status_code=303)
    try:
        update_vehicle(db, vehicle, display_name=display_name, description=description)
    except MileageTrackerError as exc:
        return _redirect_with_error(f"/vehicles/{vehicle_id}/edit", exc.message)
    return RedirectResponse(url=f"/vehicles/{vehicle_id}?success=Vehicle+updated", status_code=303)


@app.post("/vehicles/{vehicle_id}/archive")
def vehicle_archive_submit(vehicle_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle is None:
        return RedirectResponse(url="/vehicles?error=Vehicle+not+found", status_code=303)
    archive_vehicle(db, vehicle)
    return RedirectResponse(url="/vehicles?success=Vehicle+archived", status_code=303)


@app.post("/vehicles/{vehicle_id}/delete")
def vehicle_delete_submit(vehicle_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle is None:
        return RedirectResponse(url="/vehicles?error=Vehicle+not+found", status_code=303)
    try:
        delete_vehicle(db, vehicle)
    except MileageTrackerError as exc:
        return _redirect_with_error(f"/vehicles/{vehicle_id}", exc.message)
    return RedirectResponse(url="/vehicles?success=Vehicle+deleted", status_code=303)


@app.post("/vehicles/{vehicle_id}/odometer")
def vehicle_odometer_submit(
    vehicle_id: int,
    request: Request,
    tax_year: int = Form(...),
    odometer_year_start: str = Form(""),
    odometer_year_end: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_user_or_redirect(request, db)
    if isinstance(user, RedirectResponse):
        return user
    vehicle = get_vehicle(db, vehicle_id)
    if vehicle is None:
        return RedirectResponse(url="/vehicles?error=Vehicle+not+found", status_code=303)
    try:
        upsert_odometer_reading(
            db,
            vehicle,
            tax_year=tax_year,
            odometer_year_start=odometer_year_start,
            odometer_year_end=odometer_year_end,
        )
    except MileageTrackerError as exc:
        return _redirect_with_error(f"/vehicles/{vehicle_id}", exc.message)
    return RedirectResponse(
        url=f"/vehicles/{vehicle_id}?success=Odometer+readings+saved+for+{tax_year}",
        status_code=303,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
