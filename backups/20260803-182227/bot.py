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

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "DUMMY_TOKEN")
ADMIN_CHAT_IDS = [aid.strip() for aid in os.getenv("TELEGRAM_ADMIN_ID", "DUMMY_ID").split(',')]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class EditSettings(StatesGroup):
    waiting_for_text = State()
    waiting_for_custom_reply = State()

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
        [InlineKeyboardButton(text="💼 Управление проектами", callback_data="panel_projects")],
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

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply(f"System ready. Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")

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
    text = (
        f"<b>Необработанные заявки ({offset+1}/{total})</b>\n\n"
        f"<b>Заявка:</b> <code>{tx['tx_code']}</code>\n"
        f"<b>Категория:</b> {tx['category']}\n"
        f"<b>Сумма:</b> {tx['amount']} {tx['currency']}\n"
        f"<b>Имя:</b> {tx['name']}\n"
        f"<b>Детали:</b> {tx['comment']}\n"
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
    waiting_for_project_min = State()
    waiting_for_project_description = State()
    waiting_for_project_url = State()
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
    base_regions = ['PL', 'LT', 'KZ', 'AZ']
    banks = db.get_all_banks()
    db_regions = list(set([b['region_code'] for b in banks]))
    all_regions = sorted(list(set(base_regions + db_regions)))
    
    text = "<b>Настройки шлюзов (Регионы)</b>\nВыберите регион для управления банками:"
    buttons = []
    row = []
    for r in all_regions:
        row.append(InlineKeyboardButton(text=f"Регион {r}", callback_data=f"region_settings_{r}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="panel_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("region_settings_"))
async def show_region_settings(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    region = callback.data.split("_")[2]
    banks = db.get_banks_by_region(region)
    
    text = f"<b>Управление банками: Регион {region}</b>\n\n"
    if banks:
        text += "Список активных банков:"
    else:
        text += "Нет активных банков."
        
    buttons = []
    for b in banks:
        buttons.append([InlineKeyboardButton(text=f"{b['name']}", callback_data=f"edit_bank_{b['id']}")])
        
    buttons.append([InlineKeyboardButton(text="Добавить банк", callback_data=f"add_bank_{region}")])
    buttons.append([InlineKeyboardButton(text="Назад к регионам", callback_data="panel_settings")])
    
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
        
    text = (
        f"<b>Банк / Метод:</b> {bank['name']}\n"
        f"<b>Регион:</b> {bank['region_code']}\n\n"
        f"<b>Реквизиты:</b>\n<code>{bank['value']}</code>\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить реквизиты", callback_data=f"change_bank_val_{bank_id}")],
        [InlineKeyboardButton(text="Удалить банк", callback_data=f"delete_bank_{bank_id}")],
        [InlineKeyboardButton(text="Назад", callback_data=f"region_settings_{bank['region_code']}")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("delete_bank_"))
async def delete_bank_action(callback: types.CallbackQuery):
    bank_id = int(callback.data.split("_")[2])
    banks = db.get_all_banks()
    bank = next((b for b in banks if b['id'] == bank_id), None)
    if bank:
        db.delete_bank(bank_id)
        await callback.answer("Банк удален!")
        region = bank['region_code']
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Вернуться", callback_data=f"region_settings_{region}")]])
        await callback.message.edit_text(f"Банк <b>{bank['name']}</b> успешно удален.", reply_markup=kb, parse_mode="HTML")
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
    
    text = f"<b>Изменение реквизитов для {bank['name']}</b>\n\nОтправьте новые реквизиты (счет, IBAN, кошелек):"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"edit_bank_{bank_id}")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

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
    action, tx_id = callback.data.split(":")
    
    orig_text = callback.message.caption or callback.message.text or ""
    
    if action == 'approve_tx':
        db.update_transaction_status(tx_id, 'approved')
        status_suffix = "\n\n[СТАТУС: ОДОБРЕНО]"
    else:
        db.update_transaction_status(tx_id, 'rejected')
        status_suffix = "\n\n[СТАТУС: ОТКЛОНЕНО]"
        
    updated_text = orig_text + status_suffix

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
    await callback.answer("Статус заявки обновлен!")

# --- PROJECT MANAGEMENT ---
@dp.callback_query(F.data == "panel_projects")
async def panel_projects_start(callback: types.CallbackQuery):
    if not is_admin(callback.message.chat.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    projects = db.get_all_projects()
    kb = InlineKeyboardBuilder()
    text = "<b>Управление проектами (Вкладка Инвестор)</b>\n\nТекущие проекты:\n"
    if not projects:
        text += "Нет добавленных проектов."
    else:
        for p in projects:
            minimum = f"{p['min_amount']:g} EUR" if p.get('min_amount') else "общий"
            text += f"ID {p['id']}: {html.escape(p['name'])} (минимум: {minimum})\n"
            kb.row(
                InlineKeyboardButton(text=f"✏️ Изменить {p['id']}", callback_data=f"edit_proj_{p['id']}"),
                InlineKeyboardButton(text=f"❌ Удалить {p['id']}", callback_data=f"del_proj_{p['id']}")
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
    data = await state.get_data()
    if data.get("editing"):
        db.update_project(data["project_id"], data["name"], data["min_amount"], data["description"], media_url)
        action = "обновлён"
    else:
        db.add_project(data["name"], data["min_amount"], data["description"], media_url)
        action = "добавлен"
    await state.clear()
    await message.answer(f"Проект «{html.escape(data['name'])}» успешно {action}!\nВернуться к проектам: /panel", parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_proj_"))
async def del_proj_handler(callback: types.CallbackQuery):
    if not is_admin(callback.message.chat.id):
        return
    p_id = int(callback.data.split('_')[2])
    db.delete_project(p_id)
    await callback.answer("Проект удален!")
    await panel_projects_start(callback)

async def setup_bot_commands():
    commands = [
        BotCommand(command="panel", description="Открыть Control panel"),
        BotCommand(command="pending", description="Необработанные заявки"),
        BotCommand(command="search", description="Поиск заявки (пр. /search CODE)"),
        BotCommand(command="export", description="Выгрузка CSV отчета"),
        BotCommand(command="start", description="Узнать свой Chat ID")
    ]
    await bot.set_my_commands(commands)

async def main():
    if BOT_TOKEN == "DUMMY_TOKEN":
        print("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID environment variables.")
        return
    await setup_bot_commands()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
