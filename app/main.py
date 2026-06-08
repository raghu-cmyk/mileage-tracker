import os
from pathlib import Path

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
from .models import User

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Mileage Tracker", version="0.1.0")
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


@app.get("/", response_class=HTMLResponse)
def root(request: Request, db: Session = Depends(get_db)):
    if get_current_user_id(request) is None:
        return RedirectResponse(url="/login", status_code=303)
    user = require_authenticated_user(request, db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "title": "Dashboard"},
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


@app.get("/health")
def health():
    return {"status": "ok"}
