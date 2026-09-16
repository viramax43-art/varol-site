import os
import io
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, UploadFile, Form, File, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
import aiohttp
import re
import secrets
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
import db

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount static directory for CSS/JS
app.mount("/static", StaticFiles(directory="static"), name="static")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "DUMMY_TOKEN")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_ID", "DUMMY_ID")

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
    if category in DONATION_CATEGORIES:
        if project_id.strip() or project_code.strip():
            raise HTTPException(status_code=400, detail="Для доната проект указывать нельзя.")
        validate_min_amount(amount, db.get_setting("min_donation", "5"))
        return None

    if not category.startswith("Инвестор: "):
        raise HTTPException(status_code=400, detail="Некорректная категория заявки.")

    submitted_code = (project_code or "").strip().upper()
    if project_id.strip() == "-1":
        if submitted_code != "OWN" or category != "Инвестор: Предложить свой":
            raise HTTPException(status_code=400, detail="Некорректный код пользовательского проекта.")
        validate_min_amount(amount, db.get_setting("min_investment", "100"))
        return "OWN"

    try:
        numeric_project_id = int(project_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Выберите существующий проект.")
    if numeric_project_id <= 0:
        raise HTTPException(status_code=400, detail="Выберите существующий проект.")

    project = db.get_project(numeric_project_id)
    if not project:
        raise HTTPException(status_code=400, detail="Выбранный проект не найден.")
    if submitted_code != project["code"]:
        raise HTTPException(status_code=400, detail="Код проекта не соответствует выбранному проекту.")
    if category != f"Инвестор: {project['name']}":
        raise HTTPException(status_code=400, detail="Название проекта не соответствует выбранному проекту.")
    minimum = project["min_amount"] or db.get_setting("min_investment", "100")
    validate_min_amount(amount, minimum)
    return project["code"]

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
    comment: str = Form(""),
    project_id: str = Form(""),
    project_code: str = Form(""),
    feedback_requested: str = Form("false"),
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
                try:
                    with Image.open(io.BytesIO(contents)) as image:
                        image.verify()
                        detected_format = image.format
                except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
                    raise HTTPException(status_code=400, detail="Invalid image file.")

                allowed_formats = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif"}
                suffix = allowed_formats.get(detected_format)
                if suffix is None:
                    raise HTTPException(status_code=400, detail="Invalid image format.")

            fd, upload_path = tempfile.mkstemp(prefix="varol_receipt_", suffix=suffix)
            safe_filename = os.path.basename(upload_path)
            with os.fdopen(fd, "wb") as f:
                f.write(contents)
        except HTTPException:
            raise
        except Exception as e:
            print(f"[Receipt Upload Notice] {e}")
            raise HTTPException(status_code=400, detail="Could not process uploaded file.")

    tx_code = generate_tx_code(parsed_amount, trusted_project_code)
    
    # Date, local time and amount are machine-readable; the random suffix keeps the code unique.
    
    amt_float = float(parsed_amount)
    
    fb_str = "Да" if feedback_requested == "true" else "Нет"
    full_comment = f"Контакт: {contact} | Страна: {country} | Обратная связь: {fb_str}" + (f" | {comment}" if comment else "")

    now_utc = datetime.now(timezone.utc)
    expires_at = (now_utc + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tx_id = db.create_transaction(tx_code, category, amt_float, currency, name, full_comment, upload_path or "", expires_at)

    # Анонимному клиенту некуда отправить ответ, поэтому выдаём все
    # доступные реквизиты сразу на сайте. Остальные заявки обрабатывает оператор.
    requisites = ""
    if category == "Донат: Анонимный взнос":
        banks = db.get_all_banks()
        requisites = "\n\n".join(
            f"{bank['name']}:\n{bank['value']}" for bank in banks if bank.get("value")
        )
        if requisites:
            db.update_transaction_status(tx_id, "requisites_sent")
    
    if BOT_TOKEN != "DUMMY_TOKEN":
        auto_requisites_note = (
            "\nРеквизиты выданы автоматически на сайте."
            if requisites else ""
        )
        caption = (
            f"[НОВАЯ ЗАЯВКА НА ПОДДЕРЖКУ]\n\n"
            f"Код заявки: {tx_code}\n"
            f"Категория: {category}\n"
            f"Сумма: {amount} {currency}\n"
            f"Страна карты: {country}\n"
            f"Имя: {name or 'Аноним'}\n"
            f"Контакт: {contact or '—'}\n"
            f"Обратная связь: {fb_str}\n"
            f"Комментарий: {comment or '—'}"
            f"{auto_requisites_note}"
        )
        async with aiohttp.ClientSession() as session:
            admin_ids = [aid.strip() for aid in ADMIN_CHAT_ID.split(',') if aid.strip()]
            for chat_id in admin_ids:
                data = aiohttp.FormData()
                data.add_field('chat_id', chat_id)
                action_row = f'[{{"text": "Принять", "callback_data": "approve_tx:{tx_id}"}}, {{"text": "Отклонить", "callback_data": "reject_tx:{tx_id}"}}]'
                if requisites:
                    reply_markup = f'{{"inline_keyboard": [{action_row}]}}'
                else:
                    reply_markup = f'{{"inline_keyboard": [[{{"text": "Выдать реквизиты", "callback_data": "send_req_tx:{tx_id}"}}], {action_row}]}}'
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

@app.get("/api/config")
async def get_config():
    return {
        "min_donation": db.get_setting("min_donation", "5"),
        "min_investment": db.get_setting("min_investment", "100"),
        "projects": db.get_all_projects()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
