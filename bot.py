import os
import asyncio
import logging
import re
import csv
import html
from urllib.parse import urlparse
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import db

if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip())

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_IDS = [aid.strip() for aid in os.getenv("TELEGRAM_ADMIN_ID", "").split(',') if aid.strip()]
COMMUNITY_GROUP_URL = os.getenv("TELEGRAM_GROUP_URL", "https://t.me/+IrlZdfw5ECszYWQ0").strip()
COMMUNITY_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID", "-1004294029083").strip()
if COMMUNITY_GROUP_ID and COMMUNITY_GROUP_ID not in ADMIN_CHAT_IDS:
    ADMIN_CHAT_IDS.append(COMMUNITY_GROUP_ID)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class EditSettings(StatesGroup):
    waiting_for_text = State()
    waiting_for_custom_reply = State()

class PaymentConfirmation(StatesGroup):
    waiting_for_receipt = State()

def is_admin(message_or_id):
    chat_id = message_or_id if isinstance(message_or_id, int) else message_or_id.chat.id
    return db.is_admin(chat_id)

def get_main_menu_text():
    return "<b>Control panel</b>"

def get_main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Аналитика", callback_data="panel_stats")],
        [InlineKeyboardButton(text="Необработанные заявки", callback_data="panel_pending")],
        [InlineKeyboardButton(text="Настройки шлюзов", callback_data="panel_settings")],
        [InlineKeyboardButton(text="Настройки лимитов", callback_data="panel_limits")],
        [InlineKeyboardButton(text="Управление проектами", callback_data="panel_projects")],
        [InlineKeyboardButton(text="Администраторы", callback_data="panel_admins")]
    ])

def build_contact_buttons(text_content):
    buttons = []
    if not text_content:
        return None

    # Check for Telegram username
    tg_match = re.search(r'@[a-zA-Z0-9_]{4,32}', text_content)
    if tg_match:
        username = tg_match.group(0).lstrip('@')
        buttons.append([InlineKeyboardButton(text=f"Написать в Telegram (@{username})", url=f"https://t.me/{username}")])

    # Check for Phone (WhatsApp)
    phone_match = re.search(r'\+?\d{10,15}', text_content)
    if phone_match:
        raw_phone = phone_match.group(0).lstrip('+')
        buttons.append([InlineKeyboardButton(text=f"Написать в WhatsApp (+{raw_phone})", url=f"https://wa.me/{raw_phone}")])

    # Check for Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_content)
    if email_match and not tg_match:
        email = email_match.group(0)
        buttons.append([InlineKeyboardButton(text=f"Написать на Email ({email})", url=f"mailto:{email}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None



@dp.message(Command("panel"))
async def admin_panel(message: types.Message):
    if not is_admin(message): return
    await message.reply(get_main_menu_text(), reply_markup=get_main_menu_kb(), parse_mode="HTML")

@dp.message(Command("search"))
async def search_cmd(message: types.Message):
    if not is_admin(message): return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("Использование: /search <код_заявки>")
        return
    tx_code = args[1].strip()
    tx = db.get_transaction_by_code(tx_code)
    if not tx:
        await message.reply(f"Заявка с кодом {tx_code} не найдена.")
        return
    
    buttons = []
    if tx['status'] == 'pending':
        buttons = [
            [InlineKeyboardButton(text="Выдать реквизиты", callback_data=f"send_req_tx:{tx['id']}")],
            [InlineKeyboardButton(text="Принять", callback_data=f"approve_tx:{tx['id']}"), InlineKeyboardButton(text="Отклонить", callback_data=f"reject_tx:{tx['id']}")]
        ]
    contact_kb = build_contact_buttons(tx['comment'])
    if contact_kb and contact_kb.inline_keyboard:
        buttons.extend(contact_kb.inline_keyboard)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    
    text = (
        f"<b>Заявка:</b> <code>{tx['tx_code']}</code>\n"
        f"<b>Статус:</b> {tx['status']}\n"
        f"<b>Категория:</b> {tx['category']}\n"
        f"<b>Сумма:</b> {tx['amount']} {tx['currency']}\n"
        f"<b>Имя:</b> {tx['name']}\n"
        f"<b>Детали:</b> {tx['comment']}\n"
        f"<b>Дата:</b> {tx['created_at']}"
    )
    await message.reply(text, reply_markup=kb, parse_mode="HTML")

async def render_pending_page(chat_id, message_id=None, offset=0):
    limit = 1
    pending_list, total = db.get_pending_transactions(offset, limit)
    if total == 0:
        text = "Необработанных заявок нет. Все заявки рассмотрены!"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В главное меню", callback_data="panel_main")]])
        if message_id:
            try:
                await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb)
            except Exception:
                pass
        else:
            await bot.send_message(chat_id, text, reply_markup=kb)
        return
        
    if not pending_list:
        await render_pending_page(chat_id, message_id, max(0, total - 1))
        return

    tx = pending_list[0]
    buttons = [
        [InlineKeyboardButton(text="Выдать реквизиты", callback_data=f"send_req_tx:{tx['id']}")],
        [InlineKeyboardButton(text="Принять", callback_data=f"approve_tx:{tx['id']}"), InlineKeyboardButton(text="Отклонить", callback_data=f"reject_tx:{tx['id']}")]
    ]
    contact_kb = build_contact_buttons(tx['comment'])
    if contact_kb and contact_kb.inline_keyboard:
        buttons.extend(contact_kb.inline_keyboard)
        
    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton(text="[ < Назад ]", callback_data=f"pending_page:{offset-1}"))
    if offset < total - 1:
        nav_row.append(InlineKeyboardButton(text="[ Вперед > ]", callback_data=f"pending_page:{offset+1}"))
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton(text="В главное меню", callback_data="panel_main")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    cat = tx['category']
    text = (
        f"<b>Заявка ({offset+1}/{total})</b>\n\n"
        f"<b>Код заявки:</b> <code>{tx['tx_code']}</code>\n"
        f"<b>Тип:</b> {cat}\n"
        f"<b>Сумма:</b> {tx['amount']} {tx['currency']}\n"
        f"<b>Имя:</b> {tx['name'] or '—'}\n"
        f"<b>Контакты/Детали:</b> {tx['comment'] or '—'}\n"
        f"<b>Дата:</b> {tx['created_at']}"
    )
    
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
    else:
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("pending"))
async def show_pending_cmd(message: types.Message):
    if not is_admin(message): return
    await render_pending_page(message.chat.id)

@dp.callback_query(F.data.startswith("pending_page:"))
async def pending_page_callback(callback: types.CallbackQuery):
    offset = int(callback.data.split(":")[1])
    await render_pending_page(callback.message.chat.id, callback.message.message_id, offset)
    await callback.answer()

@dp.message(Command("export"))
async def export_cmd(message: types.Message):
    if not is_admin(message): return
    txs = db.get_all_transactions()
    if not txs:
        await message.reply("Транзакций пока нет.")
        return
        
    csv_file_path = "/tmp/varol_transactions_export.csv"
    with open(csv_file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Код заявки", "Категория", "Сумма", "Валюта", "Имя", "Детали/Контакты", "Статус", "Дата создания"])
        for r in txs:
            writer.writerow([r['id'], r['tx_code'], r['category'], r['amount'], r['currency'], r['name'], r['comment'], r['status'], r['created_at']])
            
    doc = FSInputFile(csv_file_path, filename="varol_transactions_export.csv")
    await message.reply_document(doc, caption=f"Выгрузка отчета по всем заявкам ({len(txs)} шт.)")

@dp.callback_query(F.data == "panel_pending")
async def panel_pending_callback(callback: types.CallbackQuery):
    await render_pending_page(callback.message.chat.id, callback.message.message_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("panel_stats"))
async def show_stats(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    period = parts[1] if len(parts) > 1 else "today"
    
    stats = db.get_extended_statistics(period)
    approved_sum = f"{stats['approved_sum']:,.2f}".replace(",", " ")
    
    period_names = {
        'today': 'Сегодня',
        'week': 'За неделю',
        'month': 'За месяц',
        'all': 'За все время'
    }
    
    text = (
        f"<b>Аналитика ({period_names[period]})</b>\n\n"
        f"Оборот: <code>{approved_sum} EUR</code>\n\n"
        f"Успешно: <code>{stats['approved_count']}</code>\n"
        f"Отклонено: <code>{stats['rejected_count']}</code>\n"
        f"Всего заявок: <code>{stats['total_count']}</code>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня", callback_data="panel_stats:today"),
            InlineKeyboardButton(text="Неделя", callback_data="panel_stats:week")
        ],
        [
            InlineKeyboardButton(text="Месяц", callback_data="panel_stats:month"),
            InlineKeyboardButton(text="Все время", callback_data="panel_stats:all")
        ],
        [InlineKeyboardButton(text="В главное меню", callback_data="panel_main")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data == "panel_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(get_main_menu_text(), reply_markup=get_main_menu_kb(), parse_mode="HTML")

# --- ADMIN MANAGEMENT ---
class AdminSettings(StatesGroup):
    waiting_for_add = State()
    waiting_for_remove = State()
    waiting_for_limit_donation = State()
    waiting_for_limit_investment = State()
    waiting_for_add_project = State()
    waiting_for_project_code = State()
    waiting_for_project_min = State()
    waiting_for_project_description = State()
    waiting_for_project_url = State()
    waiting_for_project_payment_link = State()
    waiting_for_del_project = State()

@dp.callback_query(F.data == "panel_limits")
async def panel_limits_start(callback: types.CallbackQuery):
    min_don = db.get_setting("min_donation", "5")
    min_inv = db.get_setting("min_investment", "100")
    
    text = (
        "<b>Настройки лимитов проектов</b>\n\n"
        f"Мин. сумма доната: <code>{min_don} EUR</code>\n"
        f"Мин. сумма инвестиции: <code>{min_inv} EUR</code>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить мин. донат", callback_data="edit_limit_donation")],
        [InlineKeyboardButton(text="Изменить мин. инвестицию", callback_data="edit_limit_investment")],
        [InlineKeyboardButton(text="В главное меню", callback_data="panel_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "edit_limit_donation")
async def edit_limit_donation_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettings.waiting_for_limit_donation)
    await callback.message.reply("Введите новую минимальную сумму доната (число):")
    await callback.answer()

@dp.message(StateFilter(AdminSettings.waiting_for_limit_donation))
async def edit_limit_donation_received(message: types.Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
        await message.reply("Пожалуйста, введите только число.")
        return
    db.set_setting("min_donation", val)
    await state.clear()
    await message.reply(f"Мин. сумма доната успешно изменена на {val}.")

@dp.callback_query(F.data == "edit_limit_investment")
async def edit_limit_investment_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettings.waiting_for_limit_investment)
    await callback.message.reply("Введите новую минимальную сумму инвестиции (число):")
    await callback.answer()

@dp.message(StateFilter(AdminSettings.waiting_for_limit_investment))
async def edit_limit_investment_received(message: types.Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
        await message.reply("Пожалуйста, введите только число.")
        return
    db.set_setting("min_investment", val)
    await state.clear()
    await message.reply(f"Мин. сумма инвестиции успешно изменена на {val}.")

@dp.callback_query(F.data == "panel_admins")
async def panel_admins_start(callback: types.CallbackQuery):
    admins = db.get_all_admins()
    
    text = "<b>Управление администраторами</b>\n\nТекущие админы:\n"
    for a in admins:
        text += f"• <code>{a['chat_id']}</code> (с {a['added_at'][:10]})\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить админа", callback_data="add_admin_start"),
         InlineKeyboardButton(text="Удалить админа", callback_data="remove_admin_start")],
        [InlineKeyboardButton(text="В главное меню", callback_data="panel_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "add_admin_start")
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettings.waiting_for_add)
    await callback.message.reply("Отправьте Telegram ID нового администратора:")
    await callback.answer()

@dp.message(StateFilter(AdminSettings.waiting_for_add))
async def add_admin_received(message: types.Message, state: FSMContext):
    new_admin_id = message.text.strip()
    if not new_admin_id.isdigit():
        await message.reply("ID должен состоять только из цифр. Попробуйте еще раз.")
        return
        
    db.add_admin(new_admin_id)
    await state.clear()
    await message.reply(f"Администратор <code>{new_admin_id}</code> успешно добавлен!", parse_mode="HTML")

@dp.callback_query(F.data == "remove_admin_start")
async def remove_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSettings.waiting_for_remove)
    await callback.message.reply("Отправьте Telegram ID администратора для удаления:")
    await callback.answer()

@dp.message(StateFilter(AdminSettings.waiting_for_remove))
async def remove_admin_received(message: types.Message, state: FSMContext):
    admin_id = message.text.strip()
    db.remove_admin(admin_id)
    await state.clear()
    await message.reply(f"Права администратора <code>{admin_id}</code> аннулированы.", parse_mode="HTML")


@dp.callback_query(F.data == "panel_settings")
async def show_settings(callback: types.CallbackQuery):
    banks = db.get_all_banks()
    text = "<b>Настройки шлюзов и способов оплаты</b>\n\nВыберите способ оплаты для управления реквизитами, ссылкой или включением/выключением:"
    buttons = []
    
    for b in banks:
        status_icon = "🟢" if b.get('is_active', 1) else "🔴"
        buttons.append([InlineKeyboardButton(text=f"{status_icon} {b['name']}", callback_data=f"edit_bank_{b['id']}")])
        
    buttons.append([InlineKeyboardButton(text="➕ Добавить метод оплаты", callback_data="add_bank_ALL")])
    buttons.append([InlineKeyboardButton(text="« Главное меню", callback_data="panel_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("edit_bank_"))
async def show_bank_edit(callback: types.CallbackQuery):
    bank_id = int(callback.data.split("_")[2])
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    
    if not bank:
        await callback.answer("Банк не найден.")
        return
        
    is_act = bool(bank.get('is_active', 1))
    status_str = "🟢 Активен на сайте" if is_act else "🔴 Выключен на сайте"
    toggle_btn_text = "🔴 Выключить на сайте" if is_act else "🟢 Включить на сайте"
    link_url = bank.get('link_url', '') or '—'
    
    text = (
        f"<b>Способ оплаты:</b> {html.escape(bank['name'])}\n"
        f"<b>Статус:</b> {status_str}\n\n"
        f"<b>Реквизиты:</b>\n<code>{html.escape(bank['value'] or '')}</code>\n\n"
        f"<b>Ссылка для оплаты:</b> {html.escape(link_url)}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_btn_text, callback_data=f"toggle_bank_{bank_id}_{0 if is_act else 1}")],
        [InlineKeyboardButton(text="Изменить реквизиты", callback_data=f"change_bank_val_{bank_id}")],
        [InlineKeyboardButton(text="Изменить ссылку оплаты", callback_data=f"change_bank_link_{bank_id}")],
        [InlineKeyboardButton(text="Удалить метод", callback_data=f"delete_bank_{bank_id}")],
        [InlineKeyboardButton(text="« Назад к методам", callback_data="panel_settings")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("toggle_bank_"))
async def toggle_bank_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    bank_id = int(parts[2])
    new_active = int(parts[3])
    db.toggle_bank_active(bank_id, new_active)
    await callback.answer("Статус обновлен!")
    await show_bank_edit(callback)

@dp.callback_query(F.data.startswith("delete_bank_"))
async def delete_bank_action(callback: types.CallbackQuery):
    bank_id = int(callback.data.split("_")[2])
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    if bank:
        db.delete_bank(bank_id)
        await callback.answer("Метод удален!")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Вернуться", callback_data="panel_settings")]])
        await callback.message.edit_text(f"Метод <b>{html.escape(bank['name'])}</b> успешно удален.", reply_markup=kb, parse_mode="HTML")
    else:
        await callback.answer("Ошибка удаления.")

@dp.callback_query(F.data.startswith("change_bank_val_"))
async def change_bank_value_start(callback: types.CallbackQuery, state: FSMContext):
    bank_id = int(callback.data.split("_")[3])
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    if not bank:
        await callback.answer("Банк не найден.")
        return
        
    await state.update_data(bank_id=bank_id)
    await state.set_state("WAITING_FOR_NEW_BANK_VALUE")
    
    text = f"<b>Изменение реквизитов для {html.escape(bank['name'])}</b>\n\nОтправьте новые реквизиты (счет, IBAN, имя получателя):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"edit_bank_{bank_id}")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("change_bank_link_"))
async def change_bank_link_start(callback: types.CallbackQuery, state: FSMContext):
    bank_id = int(callback.data.split("_")[3])
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    if not bank:
        await callback.answer("Банк не найден.")
        return
        
    await state.update_data(bank_id=bank_id)
    await state.set_state("WAITING_FOR_NEW_BANK_LINK")
    
    text = f"<b>Изменение ссылки оплаты для {html.escape(bank['name'])}</b>\n\nОтправьте прямую ссылку (например: https://checkout.revolut.com/pay/...):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"edit_bank_{bank_id}")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.message(StateFilter("WAITING_FOR_NEW_BANK_LINK"))
async def update_bank_link_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    bank_id = data['bank_id']
    new_link = (message.text or "").strip()
    
    db.update_bank_link(bank_id, new_link)
    await state.clear()
    await message.reply(f"Ссылка оплаты успешно обновлена на:\n<code>{html.escape(new_link)}</code>\n\nВернуться: /panel", parse_mode="HTML")

@dp.message(StateFilter("WAITING_FOR_NEW_BANK_VALUE"))
async def update_bank_value_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    bank_id = data['bank_id']
    new_value = message.text
    
    db.update_bank_value(bank_id, new_value)
    await state.clear()
    
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    if bank:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Вернуться к банку", callback_data=f"edit_bank_{bank_id}")]])
        await message.reply(f"Реквизиты для <b>{bank['name']}</b> успешно обновлены!", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("add_bank_"))
async def add_bank_start(callback: types.CallbackQuery, state: FSMContext):
    region = callback.data.split("_")[2]
    await state.update_data(region=region)
    await state.set_state(EditSettings.waiting_for_text)
    
    text = f"<b>Добавление банка в {region}</b>\n\nОтправьте название банка (например: Kaspi Bank, USDT TRC-20, BLIK):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"region_settings_{region}")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.message(EditSettings.waiting_for_text)
async def add_bank_name_received(message: types.Message, state: FSMContext):
    bank_name = message.text
    await state.update_data(bank_name=bank_name)
    await state.set_state("WAITING_FOR_BANK_VALUE")
    
    text = f"Отлично! Название: <b>{bank_name}</b>\n\nТеперь отправьте реквизиты (счет, IBAN, кошелек):"
    await message.reply(text, parse_mode="HTML")

@dp.message(StateFilter("WAITING_FOR_BANK_VALUE"))
async def add_bank_value_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    region = data['region']
    bank_name = data['bank_name']
    bank_value = message.text
    
    db.add_bank(region, bank_name, bank_value)
    await state.clear()
    
    text = f"Банк <b>{bank_name}</b> успешно добавлен в регион <b>{region}</b>!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Вернуться в регион", callback_data=f"region_settings_{region}")]])
    await message.reply(text, reply_markup=kb, parse_mode="HTML")

# --- REQUISITES & APPLICATION REPLY HANDLERS ---

@dp.callback_query(F.data.startswith("send_req_tx:"))
async def send_requisites_menu(callback: types.CallbackQuery):
    tx_id = int(callback.data.split(":")[1])
    tx = db.get_transaction(tx_id)
    if not tx:
        await callback.answer("Заявка не найдена.")
        return
        
    banks = db.get_all_banks()
    buttons = []
    for b in banks:
        buttons.append([InlineKeyboardButton(
            text=f"{b['name']} ({b['region_code']})",
            callback_data=f"send_bank_to_tx:{tx_id}:{b['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="Отправить все реквизиты", callback_data=f"send_all_banks_to_tx:{tx_id}")])
    buttons.append([InlineKeyboardButton(text="Вписать реквизиты вручную", callback_data=f"custom_reply_tx:{tx_id}")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.reply(
        f"<b>Выберите счет/банк для выдачи по заявке {tx['tx_code']} ({tx['amount']} {tx['currency']}):</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("send_bank_to_tx:"))
async def process_send_bank(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    tx_id = int(parts[1])
    bank_id = int(parts[2])
    
    tx = db.get_transaction(tx_id)
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    
    if not tx or not bank:
        await callback.answer("Ошибка: данные не найдены.")
        return
        
    db.update_transaction_status(tx_id, 'requisites_sent')
    comment_text = str(tx['comment'] or '')
    
    response_msg = (
        f"<b>Готовый ответ для клиента по заявке {tx['tx_code']}:</b>\n"
        f"────────────────────────\n"
        f"Здравствуйте, {tx['name'] or 'Клиент'}!\n"
        f"Для перевода <b>{tx['amount']} {tx['currency']}</b> зафиксированы реквизиты:\n\n"
        f"<b>Реквизиты:</b>\n<code>{bank['value']}</code>\n"
        f"<b>Способ/Банк:</b> {bank['name']}\n\n"
        f"<b>Назначение платежа / Код:</b> <code>{tx['tx_code']}</code>\n"
        f"────────────────────────\n"
        f"После оплаты отправьте квитанцию в ответ."
    )
    
    kb = build_contact_buttons(comment_text)
    
    # Update main status in original message
    orig_text = callback.message.caption or callback.message.text or ""
    updated_orig = orig_text + f"\n\n[СТАТУС: РЕКВИЗИТЫ ОТПРАВЛЕНЫ ({bank['name']})]"
    
    try:
        await callback.message.edit_text(updated_orig, parse_mode="HTML")
    except Exception:
        pass
        
    await callback.message.reply(response_msg, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Реквизиты и готовый ответ сформированы!")

@dp.callback_query(F.data.startswith("send_all_banks_to_tx:"))
async def process_send_all_banks(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    tx_id = int(parts[1])
    
    tx = db.get_transaction(tx_id)
    banks = db.get_all_banks()
    
    if not tx or not banks:
        await callback.answer("Ошибка: данные не найдены.")
        return
        
    db.update_transaction_status(tx_id, 'requisites_sent')
    comment_text = str(tx['comment'] or '')
    
    req_list_str = ""
    for b in banks:
        req_list_str += f"<b>{b['name']}</b>:\n<code>{b['value']}</code>\n\n"
        
    response_msg = (
        f"<b>Готовый ответ для клиента по заявке {tx['tx_code']}:</b>\n"
        f"────────────────────────\n"
        f"Здравствуйте, {tx['name'] or 'Клиент'}!\n"
        f"Для перевода <b>{tx['amount']} {tx['currency']}</b> вы можете использовать любые из следующих реквизитов:\n\n"
        f"{req_list_str}"
        f"<b>Назначение платежа / Код:</b> <code>{tx['tx_code']}</code>\n"
        f"────────────────────────\n"
        f"После оплаты отправьте квитанцию в ответ."
    )
    
    kb = build_contact_buttons(comment_text)
    
    orig_text = callback.message.caption or callback.message.text or ""
    updated_orig = orig_text + f"\n\n[СТАТУС: ВСЕ РЕКВИЗИТЫ ОТПРАВЛЕНЫ]"
    
    try:
        await callback.message.edit_text(updated_orig, parse_mode="HTML")
    except Exception:
        pass
        
    await callback.message.reply(response_msg, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Все реквизиты сформированы!")


@dp.callback_query(F.data.startswith("custom_reply_tx:"))
async def custom_reply_start(callback: types.CallbackQuery, state: FSMContext):
    tx_id = int(callback.data.split(":")[1])
    await state.update_data(reply_tx_id=tx_id)
    await state.set_state(EditSettings.waiting_for_custom_reply)
    
    await callback.message.reply(
        f"<b>Отправьте текстом кастомные реквизиты или ответ для заявки #{tx_id}:</b>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StateFilter(EditSettings.waiting_for_custom_reply))
async def custom_reply_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tx_id = data.get("reply_tx_id")
    reply_text = message.text
    
    if tx_id:
        db.update_transaction_status(tx_id, 'requisites_sent')
        tx = db.get_transaction(tx_id)
        tx_code = tx['tx_code'] if tx else f"#{tx_id}"
        
        response_msg = (
            f"<b>Сформирован персональный ответ для заявки {tx_code}:</b>\n\n"
            f"<code>{reply_text}</code>\n\n"
            f"Укажите код <code>{tx_code}</code> при переводе."
        )
        kb = build_contact_buttons(tx['comment']) if tx else None
        await message.reply(response_msg, reply_markup=kb, parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data.startswith("approve_tx:") | F.data.startswith("reject_tx:"))
async def process_tx(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    action = parts[0]
    tx_id = parts[1] if len(parts) > 1 else ""

    orig_text = callback.message.caption or callback.message.text or ""

    if action == 'approve_tx':
        db.update_transaction_status(tx_id, 'approved')
        status_suffix = "\n\n[СТАТУС: ОДОБРЕНО]"
    else:
        db.update_transaction_status(tx_id, 'rejected')
        status_suffix = "\n\n[СТАТУС: ОТКЛОНЕНО]"

    updated_text = orig_text + status_suffix
    try:
        if callback.message.caption is not None:
            await bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                caption=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            await bot.edit_message_text(
                text=updated_text,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
                parse_mode="HTML"
            )
    except Exception:
        pass
    await callback.answer("Статус заявки обновлен!")

# --- PROJECT MANAGEMENT ---
@dp.callback_query(F.data == "panel_projects")
async def panel_projects_start(callback: types.CallbackQuery):
    if not is_admin(callback.message.chat.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    projects = db.get_all_projects()
    p_stats = {s['category']: s for s in db.get_project_stats()}
    kb = InlineKeyboardBuilder()
    text = "<b>Управление проектами (Вкладка Инвестор)</b>\n\nТекущие проекты:\n"
    if not projects:
        text += "Нет добавленных проектов."
    else:
        for p in projects:
            minimum = f"{p['min_amount']:g} EUR" if p.get('min_amount') else "общий"
            cat_key = f"Инвестор: {p['name']}"
            stat = p_stats.get(cat_key, {'count': 0, 'total_amount': 0.0})
            link_info = f"\n  Ссылка: <i>{html.escape(p['payment_link'])}</i>" if p.get('payment_link') else ""
            text += f"ID {p['id']}: <code>{p['code']}</code> — <b>{html.escape(p['name'])}</b> (мин: {minimum})\n  Заявок: <b>{stat['count']}</b>/500 | Сумма: <b>{stat['total_amount']:.2f} EUR</b>{link_info}\n\n"
            kb.row(
                InlineKeyboardButton(text=f"Изменить {p['id']}", callback_data=f"edit_proj_{p['id']}"),
                InlineKeyboardButton(text=f"Удалить {p['id']}", callback_data=f"del_proj_{p['id']}")
            )
    
    kb.row(InlineKeyboardButton(text="Добавить проект", callback_data="add_proj"))
    kb.row(InlineKeyboardButton(text="Назад в меню", callback_data="panel_main"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "add_proj")
async def add_proj_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message.chat.id):
        return
    await callback.message.edit_text("Введите название нового проекта:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data="panel_projects")]]))
    await state.set_state(AdminSettings.waiting_for_add_project)

@dp.callback_query(F.data.startswith("edit_proj_"))
async def edit_proj_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.message.chat.id):
        return
    project_id = int(callback.data.rsplit('_', 1)[1])
    project = db.get_project(project_id)
    if not project:
        await callback.answer("Проект не найден", show_alert=True)
        return
    await state.set_data({"project_id": project_id, "editing": True, "original": project})
    await callback.message.edit_text(
        f"Введите название проекта (сейчас: {html.escape(project['name'])}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data="panel_projects")]]),
        parse_mode="HTML",
    )
    await state.set_state(AdminSettings.waiting_for_add_project)

@dp.message(StateFilter(AdminSettings.waiting_for_add_project))
async def add_proj_finish(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(name=name)
    data = await state.get_data()
    current = data.get("original", {}).get("code")
    prompt = "Введите короткий уникальный код проекта (2–12 символов A-Z, 0-9)"
    if current:
        prompt += f" (сейчас: {current})"
    await message.answer(prompt + ":")
    await state.set_state(AdminSettings.waiting_for_project_code)

@dp.message(StateFilter(AdminSettings.waiting_for_project_code))
async def project_code_finish(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    try:
        code = db.normalize_project_code(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    data = await state.get_data()
    existing = db.get_project_by_code(code)
    if existing and existing["id"] != data.get("project_id"):
        await message.answer("Этот код уже используется другим проектом.")
        return
    await state.update_data(code=code)
    await message.answer("Введите индивидуальный минимум в EUR (положительное число) или «-» для общего минимума:")
    await state.set_state(AdminSettings.waiting_for_project_min)

@dp.message(StateFilter(AdminSettings.waiting_for_project_min))
async def project_min_finish(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    raw = (message.text or "").strip().replace(',', '.')
    if raw == '-':
        minimum = None
    else:
        try:
            minimum = float(raw)
            if minimum <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Введите положительное число или «-».")
            return
    await state.update_data(min_amount=minimum)
    await message.answer("Введите описание проекта или «-», чтобы оставить пустым:")
    await state.set_state(AdminSettings.waiting_for_project_description)

@dp.message(StateFilter(AdminSettings.waiting_for_project_description))
async def project_description_finish(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    description = (message.text or "").strip()
    await state.update_data(description="" if description == '-' else description)
    await message.answer("Введите ссылку проекта (http/https) или «-», чтобы оставить пустой:")
    await state.set_state(AdminSettings.waiting_for_project_url)

@dp.message(StateFilter(AdminSettings.waiting_for_project_url))
async def project_url_finish(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    media_url = (message.text or "").strip()
    if media_url == '-':
        media_url = ""
    if media_url:
        parsed = urlparse(media_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            await message.answer("Допустима только полная ссылка с http:// или https://.")
            return
    await state.update_data(media_url=media_url)
    await message.answer("Введите индивидуальную ссылку на оплату (Revolut Checkout) или «-», чтобы использовать общую:")
    await state.set_state(AdminSettings.waiting_for_project_payment_link)

@dp.message(StateFilter(AdminSettings.waiting_for_project_payment_link))
async def project_payment_link_finish(message: types.Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    payment_link = (message.text or "").strip()
    if payment_link == '-':
        payment_link = ""
    if payment_link:
        parsed = urlparse(payment_link)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            await message.answer("Допустима только полная ссылка с http:// или https://.")
            return
    data = await state.get_data()
    if data.get("editing"):
        db.update_project(data["project_id"], data["name"], data["code"], data["min_amount"], data["description"], data.get("media_url", ""), payment_link)
        action = "обновлён"
    else:
        db.add_project(data["name"], data["code"], data["min_amount"], data["description"], data.get("media_url", ""), payment_link)
        action = "добавлен"
    await state.clear()
    await message.answer(f"Проект «{html.escape(data['name'])}» успешно {action}!\nВернуться к проектам: /panel", parse_mode="HTML")

@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    is_adm = is_admin(message.chat.id)
    args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Пользователь"

    if args.startswith("inv_"):
        tx_code = args[4:].strip()
        # Verify TX exists in DB
        tx = db.get_transaction_by_code(tx_code)
        if not tx:
            await message.answer(
                f"Заявка <code>{html.escape(tx_code)}</code> не найдена. Проверьте код или обратитесь к администратору.",
                parse_mode="HTML"
            )
            return
        # Save pending state — do NOT grant access yet, wait for receipt
        await state.set_state(PaymentConfirmation.waiting_for_receipt)
        await state.update_data(tx_code=tx_code, tx_id=str(tx['id']), user_id=user_id, username=username, first_name=first_name)
        await message.answer(
            f"<b>Заявка зафиксирована.</b>\n\n"
            f"Код: <code>{html.escape(tx_code)}</code>\n"
            f"Сумма: <b>{tx['amount']} {tx['currency']}</b>\n\n"
            f"Для подтверждения оплаты отправьте скриншот или выписку из Revolut прямо сюда в чат.\n"
            f"Администратор проверит и откроет доступ в «Сферу».",
            parse_mode="HTML"
        )
        return

    if args.startswith("idea_"):
        tx_code = args[5:].strip()
        tx = db.get_transaction_by_code(tx_code)
        if not tx:
            await message.answer(f"Заявка <code>{html.escape(tx_code)}</code> не найдена.", parse_mode="HTML")
            return
        # Ideas/donations: register immediately, no payment receipt needed
        _, badge, _ = db.verify_and_activate_code(user_id, username, first_name, tx_code)
        text = (
            f"<b>Здравствуйте, {html.escape(first_name)}!</b>\n\n"
            f"Ваше предложение/донат принято по коду <code>{html.escape(tx_code)}</code>.\n"
            f"Оно направлено на аналитическую обработку и сопоставление со схожими идеями.\n\n"
            f"<b>Ваш статус:</b> {badge}\n"
            f"Благодарим за ваш вклад в развитие экосистемы!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Группа сообщества «Сфера»", url=COMMUNITY_GROUP_URL)],
            [InlineKeyboardButton(text="Мой профиль", callback_data="user_profile")],
            [InlineKeyboardButton(text="Открыть сайт платформы", url="https://varolpaying.duckdns.org/")]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return


# --- RECEIPT UPLOAD HANDLER ---
@dp.message(StateFilter(PaymentConfirmation.waiting_for_receipt))
async def handle_payment_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tx_code = data.get("tx_code", "")
    tx_id = data.get("tx_id", "")
    user_id = data.get("user_id", message.from_user.id)
    username = data.get("username", message.from_user.username or "")
    first_name = data.get("first_name", message.from_user.first_name or "Пользователь")

    has_media = message.photo or message.document or message.video
    if not has_media:
        await message.answer(
            "Пожалуйста, отправьте скриншот или документ (фото из Revolut/банка) в качестве подтверждения оплаты."
        )
        return

    await state.clear()

    # Build caption for admin
    uname_str = f"@{username}" if username else f"ID {user_id}"
    caption = (
        f"<b>ПОДТВЕРЖДЕНИЕ ОПЛАТЫ</b>\n\n"
        f"Код заявки: <code>{html.escape(tx_code)}</code>\n"
        f"Пользователь: <b>{html.escape(first_name)}</b> ({uname_str})\n"
        f"TG ID: <code>{user_id}</code>\n\n"
        f"Проверьте скриншот и примите или отклоните заявку."
    )
    approve_cb = f"approve_receipt:{tx_id}:{user_id}"
    reject_cb = f"reject_receipt:{tx_id}:{user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Принять — открыть доступ", callback_data=approve_cb)],
        [InlineKeyboardButton(text="Отклонить", callback_data=reject_cb)]
    ])

    # Forward receipt to all admins
    admin_ids_str = os.getenv("TELEGRAM_ADMIN_ID", "")
    admin_ids = [aid.strip() for aid in admin_ids_str.split(",") if aid.strip()]
    group_id = os.getenv("TELEGRAM_GROUP_ID", "").strip()
    notify_ids = list(set(admin_ids + ([group_id] if group_id else [])))

    for chat_id in notify_ids:
        try:
            if message.photo:
                await bot.send_photo(chat_id, message.photo[-1].file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
            elif message.document:
                await bot.send_document(chat_id, message.document.file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
            elif message.video:
                await bot.send_video(chat_id, message.video.file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            print(f"Error forwarding receipt to {chat_id}: {e}")

    await message.answer(
        f"Скриншот получен и отправлен администратору на проверку.\n\n"
        f"Как только оплата будет подтверждена — вы получите ссылку на группу «Сфера».",
    )


# --- RECEIPT APPROVE / REJECT ---
@dp.callback_query(F.data.startswith("approve_receipt:") | F.data.startswith("reject_receipt:"))
async def process_receipt(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    action = parts[0]  # approve_receipt or reject_receipt
    tx_id = parts[1] if len(parts) > 1 else ""
    user_tg_id = int(parts[2]) if len(parts) > 2 else 0

    orig_text = callback.message.caption or callback.message.text or ""

    if action == "approve_receipt":
        db.update_transaction_status(tx_id, "approved")
        tx = db.get_transaction_by_id(tx_id) if hasattr(db, 'get_transaction_by_id') else None
        tx_code = ""
        if tx:
            tx_code = tx.get("tx_code", "")
        # Activate user
        if user_tg_id:
            _, badge, _ = db.verify_and_activate_code(user_tg_id, "", "", tx_code)
            try:
                await bot.send_message(
                    user_tg_id,
                    f"<b>Оплата подтверждена!</b>\n\n"
                    f"Добро пожаловать в сообщество, <b>{badge}</b>.\n"
                    f"Ваш доступ в закрытую группу «Сфера» открыт.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Войти в группу «Сфера»", url=COMMUNITY_GROUP_URL)],
                        [InlineKeyboardButton(text="Мой профиль", callback_data="user_profile")]
                    ]),
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Could not notify user {user_tg_id}: {e}")
        status_suffix = "\n\n[ОДОБРЕНО — доступ выдан]"
    else:
        db.update_transaction_status(tx_id, "rejected")
        if user_tg_id:
            try:
                await bot.send_message(
                    user_tg_id,
                    "Ваша оплата не была подтверждена. Если вы считаете это ошибкой — напишите администратору."
                )
            except Exception as e:
                print(f"Could not notify user {user_tg_id}: {e}")
        status_suffix = "\n\n[ОТКЛОНЕНО]"

    updated_text = orig_text + status_suffix
    try:
        if callback.message.caption is not None:
            await bot.edit_message_caption(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                caption=updated_text,
                reply_markup=None,
                parse_mode="HTML"
            )
        else:
            await bot.edit_message_text(
                text=updated_text,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                reply_markup=None,
                parse_mode="HTML"
            )
    except Exception:
        pass
    await callback.answer("Готово!")

    # Regular /start
    member = db.get_community_member(user_id)
    if not member:
        db.register_community_member(user_id, username, first_name, role="member", title_badge="Участник")
        member = db.get_community_member(user_id)

    badge = member.get("title_badge", "Участник")
    is_anon = member.get("is_anonymous", 0)
    anon_str = "[Инкогнито] Скрыт" if is_anon else "Публичный"

    text = (
        f"<b>Добро пожаловать в экосистему Varol Blask, {html.escape(first_name)}!</b>\n\n"
        f"<b>Ваш статус:</b> {badge}\n"
        f"<b>Приватность:</b> {anon_str}\n"
        f"<b>ID аккаунта:</b> <code>{message.chat.id}</code>\n"
    )
    if is_adm:
        text += "\n<i>Авторизован как Администратор (/panel).</i>"

    kb_buttons = [
        [InlineKeyboardButton(text="Группа сообщества «Сфера»", url=COMMUNITY_GROUP_URL)],
        [InlineKeyboardButton(text="Мой профиль", callback_data="user_profile")],
        [InlineKeyboardButton(text="Переключить приватность", callback_data="toggle_anon")],
        [InlineKeyboardButton(text="Открыть сайт платформы", url="https://varolpaying.duckdns.org/")]
    ]
    if is_adm:
        kb_buttons.insert(0, [InlineKeyboardButton(text="Панель управления", callback_data="panel_main")])
        kb_buttons.insert(1, [InlineKeyboardButton(text="Список участников", callback_data="panel_members")])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")

@dp.callback_query(F.data == "user_profile")
async def user_profile_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    member = db.get_community_member(user_id)
    if not member:
        db.register_community_member(user_id, callback.from_user.username or "", callback.from_user.first_name or "", "member", "Участник")
        member = db.get_community_member(user_id)

    badge = member.get("title_badge", "Участник")
    is_anon = member.get("is_anonymous", 0)
    tx_code = member.get("tx_code", "")
    anon_str = "[Инкогнито] Скрыт" if is_anon else "Публичный"

    text = (
        f"<b>Профиль участника</b>\n\n"
        f"Имя: <b>{html.escape(callback.from_user.first_name or '')}</b> (@{callback.from_user.username or '—'})\n"
        f"Звание / Ранг: <b>{badge}</b>\n"
        f"Статус в чате: <b>{anon_str}</b>\n"
    )
    if tx_code:
        text += f"Привязанный код: <code>{html.escape(tx_code)}</code>\n"

    anon_btn_text = "Сделать публичным" if is_anon else "Скрыть статус (Инкогнито)"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=anon_btn_text, callback_data="toggle_anon")],
        [InlineKeyboardButton(text="« Назад", callback_data="back_to_start")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "toggle_anon")
async def toggle_anon_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_val = db.toggle_community_anonymity(user_id)
    status_text = "скрыт от других участников (Инкогнито)" if new_val else "виден публично в сообществе"
    await callback.answer(f"Статус теперь {status_text}!", show_alert=True)
    await user_profile_handler(callback)

@dp.callback_query(F.data == "back_to_start")
async def back_to_start_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "Пользователь"
    is_adm = is_admin(callback.message.chat.id)
    member = db.get_community_member(user_id)
    badge = member.get("title_badge", "Участник") if member else "Участник"
    is_anon = member.get("is_anonymous", 0) if member else 0
    anon_str = "[Инкогнито] Скрыт" if is_anon else "Публичный"

    text = (
        f"<b>Добро пожаловать в экосистему Varol Blask, {html.escape(first_name)}!</b>\n\n"
        f"<b>Ваш статус:</b> {badge}\n"
        f"<b>Приватность:</b> {anon_str}\n"
        f"<b>ID:</b> <code>{callback.message.chat.id}</code>\n"
    )
    if is_adm:
        text += "\n<i>Авторизован как Администратор (/panel).</i>"

    kb_buttons = [
        [InlineKeyboardButton(text="Группа сообщества «Сфера»", url=COMMUNITY_GROUP_URL)],
        [InlineKeyboardButton(text="Мой профиль", callback_data="user_profile")],
        [InlineKeyboardButton(text="Переключить приватность", callback_data="toggle_anon")],
        [InlineKeyboardButton(text="Открыть сайт платформы", url="https://varolpaying.duckdns.org/")]
    ]
    if is_adm:
        kb_buttons.insert(0, [InlineKeyboardButton(text="Панель управления", callback_data="panel_main")])
        kb_buttons.insert(1, [InlineKeyboardButton(text="Список участников", callback_data="panel_members")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")

@dp.message(Command("profile"))
async def profile_command(message: types.Message):
    user_id = message.from_user.id
    member = db.get_community_member(user_id)
    if not member:
        db.register_community_member(user_id, message.from_user.username or "", message.from_user.first_name or "", "member", "Участник")
        member = db.get_community_member(user_id)

    badge = member.get("title_badge", "Участник")
    is_anon = member.get("is_anonymous", 0)
    tx_code = member.get("tx_code", "")
    anon_str = "[Инкогнито] Скрыт" if is_anon else "Публичный"

    text = (
        f"<b>Профиль участника</b>\n\n"
        f"Имя: <b>{html.escape(message.from_user.first_name or '')}</b> (@{message.from_user.username or '—'})\n"
        f"Звание / Ранг: <b>{badge}</b>\n"
        f"Статус в чате: <b>{anon_str}</b>\n"
    )
    if tx_code:
        text += f"Привязанный код: <code>{html.escape(tx_code)}</code>\n"

    anon_btn_text = "Сделать публичным" if is_anon else "Скрыть статус (Инкогнито)"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=anon_btn_text, callback_data="toggle_anon")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("members"))
@dp.callback_query(F.data == "panel_members")
async def members_list_handler(event: types.Message | types.CallbackQuery):
    chat_id = event.chat.id if isinstance(event, types.Message) else event.message.chat.id
    is_adm = is_admin(chat_id)
    members = db.get_all_community_members()
    if not members:
        msg_text = "Список участников сообщества пуст."
    else:
        msg_text = f"<b>Участники сообщества (Всего: {len(members)}):</b>\n\n"
        for m in members[:30]:
            user_tg = f"@{m['tg_username']}" if m.get('tg_username') else f"ID {m['tg_user_id']}"
            if m.get('is_anonymous') and not is_adm:
                msg_text += "• [Инкогнито] Анонимный инвестор\n"
            else:
                anon_tag = " [Инкогнито]" if m.get('is_anonymous') else ""
                tx_tag = f" ({m['tx_code']})" if m.get('tx_code') else ""
                badge = m.get('title_badge', 'Участник')
                msg_text += f"• [{badge}] <b>{html.escape(m.get('tg_first_name', ''))}</b> ({user_tg}){anon_tag}{tx_tag}\n"

    if isinstance(event, types.Message):
        await event.answer(msg_text, parse_mode="HTML")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« В панель", callback_data="panel_main")]])
        await event.message.edit_text(msg_text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("poll"))
async def admin_poll_handler(message: types.Message):
    if not is_admin(message.chat.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "Использование: /poll <Вопрос>\nПример: /poll Утвердить расширение маркетплейса на рынок ЕС?",
            parse_mode="HTML"
        )
        return
    question = parts[1].strip()
    target_chat = COMMUNITY_GROUP_ID if message.chat.type == "private" else message.chat.id
    try:
        await bot.send_poll(
            chat_id=target_chat,
            question=question[:300],
            options=["Поддерживаю", "Требует доработки", "Против"],
            is_anonymous=False
        )
        if message.chat.type == "private":
            await message.reply("Опрос запущен в группе «Сфера».", parse_mode="HTML")
    except Exception as e:
            await message.reply(f"Ошибка создания опроса: {e}")

@dp.chat_join_request()
async def join_request_handler(event: types.ChatJoinRequest):
    user_id = event.from_user.id
    first_name = event.from_user.first_name or "Пользователь"
    username = event.from_user.username or ""

    has_access = db.check_community_access(user_id)
    if has_access:
        try:
            await event.approve()
            logging.info(f"Approved join request for {user_id} (@{username})")
            member = db.get_community_member(user_id)
            is_anon = member.get("is_anonymous", 0) if member else 0
            badge = member.get("title_badge", "Инвестор") if member else "Инвестор"
            if not is_anon:
                try:
                    await bot.send_message(
                        chat_id=event.chat.id,
                        text=(
                            f"В закрытое сообщество «Сфера» вступил <b>{html.escape(first_name)}</b> (Ранг: <b>{badge}</b>)\n\n"
                            f"Добро пожаловать в ряды платформы!\n"
                            f"Напишите пару слов о себе и ваших основных интересах в проектах экосистемы."
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.error(f"Failed to announce member in group: {e}")
        except Exception as e:
            logging.error(f"Error approving join request: {e}")
    else:
        try:
            await event.decline()
            logging.info(f"Declined join request for {user_id} (@{username}) - no code")
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"Здравствуйте, {html.escape(first_name)}.\n\n"
                        f"Группа «Сфера» является закрытым сообществом инвесторов платформы Varol Blask.\n"
                        f"Для подтверждения статуса оформите заявку на официальном сайте:\n"
                        f"https://varolpaying.duckdns.org/\n\n"
                        f"После создания заявки перейдите в бота по ссылке активации."
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Failed to send decline notice to {user_id}: {e}")
        except Exception as e:
            logging.error(f"Error declining join request: {e}")

        caption += f"Комментарий: {html.escape(message.caption)}\n"

    for adm_id in ADMIN_CHAT_IDS:
        try:
            await bot.send_photo(chat_id=adm_id, photo=photo_file_id, caption=caption, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to forward photo to admin {adm_id}: {e}")

    await message.reply(
        "<b>Квитанция успешно принята.</b>\n"
        "Мы сверим данные и обновим статус инвестора.",
        parse_mode="HTML"
    )

@dp.message(F.text & ~F.text.startswith("/"))
async def user_text_tx_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return
    if is_admin(message.chat.id):
        return

    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Пользователь"
    member = db.get_community_member(user_id)
    tx_code = member.get("tx_code", "Не привязан") if member else "Не привязан"

    text = (
        f"[СООБЩЕНИЕ / КОД ПЕРЕВОДА ОТ ПОЛЬЗОВАТЕЛЯ]\n\n"
        f"От: <b>{html.escape(first_name)}</b> (@{username or '—'})\n"
        f"ID пользователя: <code>{user_id}</code>\n"
        f"Номер заявки: <code>{html.escape(tx_code)}</code>\n"
        f"Текст/Код: <code>{html.escape(message.text)}</code>"
    )

    for adm_id in ADMIN_CHAT_IDS:
        try:
            await bot.send_message(chat_id=adm_id, text=text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to forward text to admin {adm_id}: {e}")

    await message.reply(
        "<b>Данные переданы администраторам платформы.</b>\n"
        "Мы сверим информацию и обновим ваш статус.",
        parse_mode="HTML"
    )

@dp.my_chat_member()
async def bot_added_to_group(event: types.ChatMemberUpdated):
    if event.new_chat_member.status in ["member", "administrator"]:
        chat_id = event.chat.id
        title = event.chat.title or "Группа"
        logging.info(f"Bot added to chat {title} ({chat_id})")
        if str(chat_id) not in ADMIN_CHAT_IDS:
            ADMIN_CHAT_IDS.append(str(chat_id))
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"<b>Бот Varldost подключён к группе «{html.escape(title)}».</b>\n\n"
                    f"Уведомления о заявках и переводах поступают в этот чат.\n\n"
                    f"Команды управления:\n"
                    f"• /stats — статистика платформы\n"
                    f"• /pending — нерассмотренные заявки\n"
                    f"• /members — реестр участников\n"
                    f"• /poll <вопрос> — запустить опрос сообщества"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Error greeting group: {e}")

@dp.message(F.chat.type.in_({"group", "supergroup"}) & F.text.startswith("/"))
async def group_commands_handler(message: types.Message):
    cmd = message.text.split()[0].lower().split("@")[0]

    if str(message.chat.id) not in ADMIN_CHAT_IDS:
        ADMIN_CHAT_IDS.append(str(message.chat.id))

    if cmd == "/stats":
        stats = db.get_stats()
        text = (
            f"<b>Статистика платформы Varol Blask</b>\n\n"
            f"• Всего заявок: <b>{stats.get('total_count', 0)}</b>\n"
            f"• Общая сумма: <b>{stats.get('total_amount', 0):,.2f} EUR</b>\n"
            f"• Ожидают проверки: <b>{stats.get('pending_count', 0)}</b>\n"
            f"• Одобрено: <b>{stats.get('approved_count', 0)}</b>\n"
            f"• Отклонено: <b>{stats.get('rejected_count', 0)}</b>"
        )
        await message.answer(text, parse_mode="HTML")
    elif cmd == "/pending":
        pending = db.get_pending_transactions()
        if not pending:
            await message.answer("Нет необработанных заявок.", parse_mode="HTML")
            return
        text = f"<b>Необработанные заявки ({len(pending)}):</b>\n\n"
        for tx in pending[:10]:
            text += f"• <code>{tx['code']}</code> | {tx['amount']} {tx['currency']} | {html.escape(tx.get('sender_name') or 'Аноним')} ({tx.get('source_tab', 'Проекты')})\n"
        await message.answer(text, parse_mode="HTML")
    elif cmd == "/members":
        members = db.get_all_community_members()
        is_adm = is_admin(message.from_user.id) or is_admin(message.chat.id)
        text = f"<b>Участники сообщества ({len(members)}):</b>\n\n"
        for m in members[:20]:
            if m.get('is_anonymous') and not is_adm:
                text += "• [Инкогнито] Анонимный инвестор\n"
            else:
                uname = f"@{m['tg_username']}" if m.get('tg_username') else f"ID {m['tg_user_id']}"
                badge = m.get('title_badge', 'Участник')
                text += f"• [{badge}] <b>{html.escape(m.get('tg_first_name', ''))}</b> ({uname})\n"
        await message.answer(text, parse_mode="HTML")



async def setup_bot_commands():
    commands = [
        BotCommand(command="start", description="Главное меню / Статус"),
        BotCommand(command="profile", description="Мой профиль и приватность"),
        BotCommand(command="panel", description="Открыть Control panel"),
        BotCommand(command="members", description="Список участников"),
        BotCommand(command="pending", description="Необработанные заявки"),
        BotCommand(command="search", description="Поиск заявки (пр. /search CODE)"),
        BotCommand(command="export", description="Выгрузка CSV отчета")
    ]
    await bot.set_my_commands(commands)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "DUMMY_TOKEN":
        print("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID environment variables.")
        return
    db.init_db()
    await setup_bot_commands()
    print("Bot starting polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
