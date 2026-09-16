import logging
import os
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional
from zoneinfo import ZoneInfo

if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import aiohttp
import db
from admin_auth import ensure_admin_password, login as admin_login, logout as admin_logout, verify_admin
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

IP_REQUEST_LOGS = defaultdict(list)
RATE_LIMIT_GLOBAL = 150  # max requests per min per IP
RATE_LIMIT_SUBMIT = 25   # max payment submits per min per IP

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.on_event("startup")
def bootstrap_admin_credentials():
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if admin_password:
        ensure_admin_password(admin_password)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    now = time.time()
    path = request.url.path

    # Prune timestamps older than 60 seconds
    logs = [t for t in IP_REQUEST_LOGS[client_ip] if now - t < 60]
    IP_REQUEST_LOGS[client_ip] = logs

    limit = RATE_LIMIT_SUBMIT if path == "/api/submit_payment" else RATE_LIMIT_GLOBAL

    if len(logs) >= limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Слишком много запросов. Пожалуйста, подождите минуту."}
        )

    IP_REQUEST_LOGS[client_ip].append(now)
    return await call_next(request)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Mount static directory for CSS/JS
app.mount("/static", StaticFiles(directory="static"), name="static")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "DUMMY_TOKEN")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_ID", "DUMMY_ID")
ADMIN_PATH = os.getenv("ADMIN_PATH", "").strip()
if not re.fullmatch(r"/[A-Za-z0-9_-]{12,128}", ADMIN_PATH):
    raise RuntimeError("ADMIN_PATH must start with / and contain 12-128 URL-safe characters")
ADMIN_API_PREFIX = f"/api{ADMIN_PATH}"
GROUP_CHAT_ID = os.getenv("TELEGRAM_GROUP_ID", "-1004294029083").strip()

DONATION_CATEGORIES = {"Донат: Анонимный взнос", "Донат: Персональный взнос"}

def parse_positive_amount(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Введите корректную сумму.")
    if not amount.is_finite() or amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть положительным числом.")
    return amount

def validate_min_amount(amount: Decimal, minimum) -> None:
    try:
        min_amount = Decimal(str(minimum))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=500, detail="Некорректно настроена минимальная сумма.")
    if not min_amount.is_finite() or min_amount <= 0:
        raise HTTPException(status_code=500, detail="Некорректно настроена минимальная сумма.")
    if amount < min_amount:
        raise HTTPException(status_code=400, detail=f"Минимальная сумма: {min_amount:g} EUR.")

def validate_payment_target(category: str, project_id: str, project_code: str, amount: Decimal):
    cat_str = str(category or "").strip()
    proj_id_str = str(project_id or "").strip()
    code_str = str(project_code or "").strip().upper()

    # 1. Custom User Investment ("Предложить свой" / Вестибюль)
    if proj_id_str == "-1":
        if code_str and code_str != "OWN":
            raise HTTPException(status_code=400, detail="Некорректный код для собственного проекта.")
        own_min = db.get_setting("own_project_min", "250")
        validate_min_amount(amount, own_min)
        return "OWN"
    
    if code_str == "OWN":
        own_min = db.get_setting("own_project_min", "250")
        validate_min_amount(amount, own_min)
        return "OWN"

    # 2. Project from Database (by project_id or project_code)
    if proj_id_str:
        if not proj_id_str.isdigit() or int(proj_id_str) <= 0:
            raise HTTPException(status_code=400, detail="Некорректный идентификатор проекта.")
        project = db.get_project(int(proj_id_str))
        if not project:
            raise HTTPException(status_code=400, detail="Проект не найден.")
        if code_str and project.get("code") and code_str != project["code"].upper():
            raise HTTPException(status_code=400, detail="Код проекта не совпадает.")
        minimum = project.get("min_amount") or (db.get_setting("min_donation", "5") if project.get("category") in ("feedback", "donation") else db.get_setting("min_investment", "250"))
        validate_min_amount(amount, minimum)
        return project.get("code") or code_str or "PROJ"

    if code_str:
        project = db.get_project_by_code(code_str)
        if project:
            minimum = project.get("min_amount") or 5
            validate_min_amount(amount, minimum)
            return project.get("code") or code_str
        raise HTTPException(status_code=400, detail="Проект с указанным кодом не найден.")

    # 3. Donations / Feedback / General submissions
    if "донат" in cat_str.lower() or "предложен" in cat_str.lower() or "feedback" in cat_str.lower() or "взнос" in cat_str.lower():
        validate_min_amount(amount, db.get_setting("min_donation", "5"))
        return None

    # 4. Fallback investment validation
    if "инвестор" in cat_str.lower():
        validate_min_amount(amount, db.get_setting("min_investment", "250"))
        return None

    validate_min_amount(amount, 5)
    return None

def generate_tx_code(amount: Decimal, project_code: str | None = None) -> str:
    """Keep donation codes stable; insert a trusted project code for investments."""
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    random_part = "".join(secrets.choice(alphabet) for _ in range(4))
    created_local = datetime.now(ZoneInfo("Europe/Volgograd"))
    amount_cents = int(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
    prefix = f"TX-{project_code}" if project_code else "TX"
    return f"{prefix}-{created_local:%y%m%d%H%M%S}-{amount_cents}-{random_part}"

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/requisites")
async def get_requisites():
    banks = db.get_all_banks()
    req_dict = {}
    for b in banks:
        code = b['region_code']
        if code not in req_dict:
            req_dict[code] = []
        req_dict[code].append(b)
    return JSONResponse(content={"requisites": req_dict})

@app.post("/api/submit_payment")
async def submit_payment(
    amount: str = Form(...),
    currency: str = Form("EUR"),
    name: str = Form("Аноним"),
    contact: str = Form("—"),
    country: str = Form(""),
    country_code: str = Form(""),
    category: str = Form(""),
    payment_method: str = Form(""),
    comment: str = Form(""),
    project_id: str = Form(""),
    project_code: str = Form(""),
    custom_project_name: str = Form(""),
    feedback_requested: str = Form("false"),
    source_tab: str = Form(""),
    receipt: Optional[UploadFile] = File(None)
):
    country = country.strip()
    country_code = country_code.strip().upper()
    if country and not re.fullmatch(r"[A-Z]{2}", country_code):
        raise HTTPException(status_code=400, detail="Выберите страну из списка подсказок.")
    if not country:
        country_code = ""

    parsed_amount = parse_positive_amount(amount)
    trusted_project_code = validate_payment_target(category, project_id, project_code, parsed_amount)

    # Получаем payment_link для инвестиционного проекта (для уведомления)
    _proj_obj = None
    _project_payment_link = ""
    _project_display_name = ""
    if trusted_project_code and trusted_project_code != "OWN":
        try:
            _proj_obj = db.get_project(int(project_id))
            if _proj_obj:
                _project_payment_link = _proj_obj.get("payment_link", "") or ""
                _project_display_name = _proj_obj.get("name", "") or ""
        except Exception:
            pass

    safe_filename = None
    upload_path = None
    contents = None
    is_pdf = False

    if receipt and receipt.filename:
        try:
            contents = await receipt.read()
            if len(contents) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File too large")
            header = contents[:4]
            is_pdf = header.startswith(b'%PDF')
            is_jpeg = header.startswith(b'\xff\xd8')
            is_png = header.startswith(b'\x89PNG')
            is_gif = header.startswith(b'GIF8')
            if not (is_pdf or is_jpeg or is_png or is_gif):
                raise HTTPException(status_code=400, detail="Invalid file format.")

            if is_pdf:
                if not contents.rstrip().endswith(b'%%EOF'):
                    raise HTTPException(status_code=400, detail="Invalid PDF file.")
                suffix = ".pdf"
            else:
                if is_jpeg:
                    suffix = ".jpg"
                elif is_png:
                    suffix = ".png"
                elif is_gif:
                    suffix = ".gif"
                else:
                    raise HTTPException(status_code=400, detail="Invalid image format.")

            safe_filename = f"receipt_{secrets.token_hex(8)}{suffix}"
            upload_path = os.path.join(UPLOADS_DIR, safe_filename)
            with open(upload_path, "wb") as f:
                f.write(contents)
        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"[Receipt Upload Notice] {e}")
            raise HTTPException(status_code=400, detail="Could not process uploaded file.")

    tx_code = generate_tx_code(parsed_amount, trusted_project_code)
    
    amt_float = float(parsed_amount)
    
    display_category = f"{category} («{custom_project_name.strip()}»)" if (custom_project_name.strip() and "Предложить свой" in category) else category
    full_comment = f"Метод оплаты: {payment_method}" + (f" | {comment}" if comment else "")

    now_utc = datetime.now(timezone.utc)
    expires_at = (now_utc + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tx_id = db.create_transaction(tx_code, display_category, amt_float, currency, name, full_comment, upload_path or "", expires_at)

    requisites = ""
    is_anon = (name == "Аноним" or contact == "—" or "Аноним" in display_category)
    is_feedback_category = "feedback" in str(category).lower() or "предложение" in str(category).lower() or "идея" in str(category).lower() or (_proj_obj and _proj_obj.get("category") == "feedback")
    is_donation_category = "донат" in str(category).lower() or "donation" in str(category).lower() or (_proj_obj and _proj_obj.get("category") == "donation")

    if is_donation_category or is_anon:
        banks = db.get_all_banks()
        requisites = "\n\n".join(
            f"{bank['name']}:\n{bank['value']}" for bank in banks if bank.get("value")
        )
        if requisites:
            db.update_transaction_status(tx_id, "requisites_sent")
    
    if BOT_TOKEN != "DUMMY_TOKEN":
        if is_feedback_category:
            header = f"[ПРЕДЛОЖЕНИЕ / ИДЕЯ] {_project_display_name or ''}"
        elif is_donation_category:
            header = f"[ДОНАТ НА РАЗВИТИЕ] {'(Анонимно)' if is_anon else ''} {_project_display_name or ''}"
        elif trusted_project_code and trusted_project_code != "OWN":
            header = f"[ИНВЕСТИЦИЯ] {'(Анонимно)' if is_anon else ''} {_project_display_name or display_category}"
        elif trusted_project_code == "OWN":
            header = f"[ИНВЕСТОР: СВОЙ ПРОЕКТ] {'(Анонимно)' if is_anon else ''}"
        else:
            header = f"[НОВАЯ ЗАЯВКА] {'(Анонимно)' if is_anon else ''}"

        caption_lines = [
            f"{header}\n",
            f"Код заявки: {tx_code}",
            f"Категория: {display_category}",
            f"Сумма: {amount} {currency}",
            f"Способ оплаты: {payment_method or '—'}"
        ]
        if _project_payment_link:
            caption_lines.append(f"Revolut ссылка: {_project_payment_link}")
        if name and name != "Аноним":
            caption_lines.append(f"Имя: {name}")
        if contact and contact != "—":
            caption_lines.append(f"Контакт клиента: {contact}")
        else:
            if "Анонимный" in display_category:
                caption_lines.append("Контакт: — (Конфиденциально)")
        if comment:
            caption_lines.append(f"Комментарий: {comment}")
        if source_tab:
            caption_lines.append(f"Вкладка: {source_tab}")
            
        if contact and contact != "—":
            caption_lines.append("\nРеквизиты (Польская карта):\nPL89 1020 5558 1111 2222 3333 4444")
            
        caption = "\n".join(caption_lines)
        async with aiohttp.ClientSession() as session:
            admin_ids = [aid.strip() for aid in ADMIN_CHAT_ID.split(',') if aid.strip()]
            if GROUP_CHAT_ID and GROUP_CHAT_ID not in admin_ids:
                admin_ids.append(GROUP_CHAT_ID)
            for chat_id in admin_ids:
                data = aiohttp.FormData()
                data.add_field('chat_id', chat_id)
                
                kb_rows = []
                tg_match = re.search(r'@[a-zA-Z0-9_]{3,32}', f"{contact} {comment}")
                if tg_match:
                    uname = tg_match.group(0).lstrip('@')
                    kb_rows.append(f'[{{"text": "Написать клиенту (@{uname})", "url": "https://t.me/{uname}"}}]')
                
                if kb_rows:
                    reply_markup = f'{{"inline_keyboard": [{",".join(kb_rows)}]}}'
                    data.add_field('reply_markup', reply_markup)

                if contents and safe_filename:
                    data.add_field('caption', caption)
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument" if is_pdf else f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                    file_field = 'document' if is_pdf else 'photo'
                    data.add_field(file_field, contents, filename=safe_filename)
                else:
                    data.add_field('text', caption)
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

                async with session.post(url, data=data) as resp:
                    if resp.status != 200:
                        print(f"Telegram API Error for chat_id {chat_id}:", await resp.text())

    return JSONResponse(content={"status": "success", "tx_code": tx_code, "requisites": requisites, "expires_at": expires_at})

@app.get(ADMIN_PATH, response_class=HTMLResponse)
async def read_admin():
    with open("admin.html", "r", encoding="utf-8") as f:
        content = f.read().replace("__ADMIN_API_PREFIX__", ADMIN_API_PREFIX)
    return HTMLResponse(
        content=content,
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


@app.post(f"{ADMIN_API_PREFIX}/login")
async def admin_login_route(request: Request, response: Response):
    body = await request.json()
    password = str(body.get("password") or "").strip()
    if not password:
        raise HTTPException(status_code=400, detail="Password required")
    admin_login(request, response, password)
    return {"status": "ok"}


@app.post(f"{ADMIN_API_PREFIX}/logout")
async def admin_logout_route(request: Request, response: Response):
    admin_logout(request, response)
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/set_anon_title")
async def set_anon_title(request: Request):
    verify_admin(request)
    body = await request.json()
    db.set_setting("anon_title", body.get("title", "Анонимный взнос"))
    return {"status": "ok"}

@app.get(f"{ADMIN_API_PREFIX}/data")
async def get_admin_data(request: Request):
    verify_admin(request)
    return {
        "min_donation": db.get_setting("min_donation", "5"),
        "min_investment": db.get_setting("min_investment", "250"),
        "own_project_enabled": int(db.get_setting("own_project_enabled", "1")),
        "own_project_title": db.get_setting("own_project_title", "Предложить свой"),
        "own_project_min": db.get_setting("own_project_min", "250"),
        "own_project_link": db.get_setting("own_project_link", ""),
        "anon_title": db.get_setting("anon_title", "Анонимный взнос"),
        "feedback_manifest_title": db.get_setting("feedback_manifest_title", "Мы ценим ваш вклад"),
        "feedback_manifest_text": db.get_setting("feedback_manifest_text", "Мы выражаем глубокую благодарность за ваш уникальный вклад. Каждая идея особенна: мы обязательно изучим ваше предложение, оно пройдет анализ через систему ИИ и будет объединено с общими векторами развития платформы."),
        "banks": db.get_all_banks(),
        "projects": db.get_all_projects(),
    }

@app.post(f"{ADMIN_API_PREFIX}/toggle_bank")
async def toggle_bank(request: Request):
    verify_admin(request)
    body = await request.json()
    db.toggle_bank_active(body.get("bank_id"), body.get("is_active"))
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/save_bank")
async def save_bank(request: Request):
    verify_admin(request)
    body = await request.json()
    bank_id = body.get("id")
    name = body.get("name")
    value = body.get("value", "")
    link_url = body.get("link_url", "")
    if bank_id:
        db.update_bank_full(bank_id, name, value, link_url)
    else:
        db.add_bank("ALL", name, value, link_url)
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/reorder_banks")
async def reorder_banks(request: Request):
    verify_admin(request)
    body = await request.json()
    bank_ids = body.get("bank_ids", [])
    if bank_ids:
        db.update_bank_order(bank_ids)
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/toggle_project")
async def toggle_project(request: Request):
    verify_admin(request)
    body = await request.json()
    db.toggle_project_active(body.get("project_id"), body.get("is_active", 1))
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/add_project")
async def add_project(request: Request):
    verify_admin(request)
    body = await request.json()
    db.add_project(
        name=body.get("name"),
        code=body.get("code"),
        min_amount=body.get("min_amount", 100),
        description=body.get("description", ""),
        payment_link=body.get("payment_link", ""),
        is_active=body.get("is_active", 1),
        category=body.get("category", "investment")
    )
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/reorder_projects")
async def reorder_projects(request: Request):
    verify_admin(request)
    body = await request.json()
    project_ids = body.get("project_ids", [])
    if project_ids:
        db.update_project_order(project_ids)
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/edit_project")
async def edit_project(request: Request):
    verify_admin(request)
    body = await request.json()
    db.update_project(
        project_id=body.get("project_id"),
        name=body.get("name"),
        code=body.get("code"),
        min_amount=body.get("min_amount", 100),
        description=body.get("description", ""),
        payment_link=body.get("payment_link", ""),
        is_active=body.get("is_active", 1),
        category=body.get("category", "investment")
    )
    return {"status": "ok"}

@app.post(f"{ADMIN_API_PREFIX}/delete_project")
async def delete_project(request: Request):
    verify_admin(request)
    body = await request.json()
    db.delete_project(body.get("project_id"))
    return {"status": "ok"}


@app.get("/uploads/{filename}")
async def get_uploaded_file(filename: str, request: Request):
    verify_admin(request)
    safe_name = os.path.basename(filename)
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = os.path.join(UPLOADS_DIR, safe_name)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/api/config")
async def get_config():
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "varlpay_bot")
    return {
        "bot_username": bot_username,
        "min_donation": db.get_setting("min_donation", "5"),
        "min_investment": db.get_setting("min_investment", "250"),
        "own_project_enabled": int(db.get_setting("own_project_enabled", "1")),
        "own_project_title": db.get_setting("own_project_title", "Предложить свой"),
        "own_project_min": db.get_setting("own_project_min", "250"),
        "own_project_link": db.get_setting("own_project_link", ""),
        "anon_title": db.get_setting("anon_title", "Анонимный взнос"),
        "feedback_manifest_title": db.get_setting("feedback_manifest_title", "Мы ценим ваш вклад"),
        "feedback_manifest_text": db.get_setting("feedback_manifest_text", "Мы выражаем глубокую благодарность за ваш уникальный вклад. Каждая идея особенна: мы обязательно изучим ваше предложение, оно пройдет анализ через систему ИИ и будет объединено с общими векторами развития платформы."),
        "projects": db.get_active_projects()
    }

@app.post(f"{ADMIN_API_PREFIX}/set_own_project")
async def set_own_project(request: Request):
    verify_admin(request)
    body = await request.json()
    enabled = 1 if body.get("enabled") else 0
    title = body.get("title")
    min_amount = body.get("min_amount")
    link = body.get("link")
    
    db.set_setting("own_project_enabled", str(enabled))
    if title is not None:
        db.set_setting("own_project_title", str(title))
    if min_amount is not None:
        db.set_setting("own_project_min", str(min_amount))
    if link is not None:
        db.set_setting("own_project_link", str(link))
        
    return {"status": "ok", "own_project_enabled": enabled}

@app.post(f"{ADMIN_API_PREFIX}/set_feedback_manifest")
async def set_feedback_manifest(request: Request):
    verify_admin(request)
    body = await request.json()
    title = body.get("title")
    text = body.get("text")
    if title is not None:
        db.set_setting("feedback_manifest_title", str(title).strip())
    if text is not None:
        db.set_setting("feedback_manifest_text", str(text).strip())
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

