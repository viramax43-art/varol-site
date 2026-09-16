from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import db

shop_router = Router()

TRANSLATIONS = {
    'ru': {
        'welcome': 'Добро пожаловать в каталог! Пожалуйста, выберите язык:',
        'main_menu': 'Главное меню. Выберите действие:',
        'catalog': 'Каталог',
        'lang_changed': 'Язык успешно изменен на Русский.',
        'no_categories': 'Каталог пуст.',
        'no_products': 'В этой категории пока нет товаров.',
        'btn_back': 'Назад',
        'btn_back_cat': 'Назад к категориями',
        'btn_order': '🛍 Заказать',
        'order_sent': '✅ Заявка отправлена! Менеджер свяжется с вами в ближайшее время.',
        'new_order_admin': '🚨 <b>Новый заказ из магазина!</b>\n\n'
    },
    'en': {
        'welcome': 'Welcome to the catalog! Please select your language:',
        'main_menu': 'Main Menu. Please choose an action:',
        'catalog': 'Catalog',
        'lang_changed': 'Language successfully changed to English.',
        'no_categories': 'Catalog is empty.',
        'no_products': 'No products in this category yet.',
        'btn_back': 'Back',
        'btn_back_cat': 'Back to categories',
        'btn_order': '🛍 Order',
        'order_sent': '✅ Order sent! A manager will contact you shortly.',
        'new_order_admin': '🚨 <b>New order from shop!</b>\n\n'
    },
    'lt': {
        'welcome': 'Sveiki atvykę į katalogą! Pasirinkite kalbą:',
        'main_menu': 'Pagrindinis meniu. Pasirinkite veiksmą:',
        'catalog': 'Katalogas',
        'lang_changed': 'Kalba sėkmingai pakeista į lietuvių.',
        'no_categories': 'Katalogas tuščias.',
        'no_products': 'Šioje kategorijoje prekių kol kas nėra.',
        'btn_back': 'Atgal',
        'btn_back_cat': 'Atgal į kategorijas',
        'btn_order': '🛍 Užsisakyti',
        'order_sent': '✅ Užsakymas išsiųstas! Vadybininkas netrukus su jumis susisieks.',
        'new_order_admin': '🚨 <b>Naujas užsakymas iš parduotuvės!</b>\n\n'
    }
}

class ShopAdminState(StatesGroup):
    waiting_for_category_ru = State()
    waiting_for_category_en = State()
    waiting_for_category_lt = State()

def get_text(lang, key):
    return TRANSLATIONS.get(lang, TRANSLATIONS['ru']).get(key, key)

def get_lang_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en")],
        [InlineKeyboardButton(text="🇱🇹 Lietuvių", callback_data="setlang_lt")]
    ])

def get_client_main_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'catalog'), callback_data="shop_catalog")],
        [InlineKeyboardButton(text="🌍 Change Language", callback_data="shop_change_lang")]
    ])

@shop_router.message(Command("start"))
async def shop_start(message: types.Message):
    db.create_or_update_shop_user(message.chat.id)
    user = db.get_shop_user(message.chat.id)
    
    args = message.text.split()
    if len(args) > 1:
        payload = args[1]
        # Future: handle direct link to product
        pass

    lang = user['lang'] if user else 'ru'
    
    if db.is_admin(message.chat.id):
        await message.reply(f"System ready. Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")
    
    await message.reply(get_text(lang, 'welcome'), reply_markup=get_lang_kb())

@shop_router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: types.CallbackQuery):
    lang = callback.data.split('_')[1]
    db.create_or_update_shop_user(callback.message.chat.id, lang=lang)
    await callback.message.edit_text(get_text(lang, 'lang_changed'), reply_markup=get_client_main_menu(lang))

@shop_router.callback_query(F.data == "shop_change_lang")
async def change_lang_menu(callback: types.CallbackQuery):
    user = db.get_shop_user(callback.message.chat.id)
    lang = user['lang'] if user else 'ru'
    await callback.message.edit_text(get_text(lang, 'welcome'), reply_markup=get_lang_kb())

@shop_router.callback_query(F.data == "shop_catalog")
async def show_catalog(callback: types.CallbackQuery):
    user = db.get_shop_user(callback.message.chat.id)
    lang = user['lang'] if user else 'ru'
    
    categories = db.get_shop_categories()
    if not categories:
        await callback.message.edit_text(get_text(lang, 'no_categories'), reply_markup=get_client_main_menu(lang))
        return
        
    buttons = []
    for c in categories:
        name = c.get(f'name_{lang}', c['name_ru'])
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"shop_cat_{c['id']}")])
    buttons.append([InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data="shop_main")])
    
    await callback.message.edit_text(get_text(lang, 'catalog'), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@shop_router.callback_query(F.data == "shop_main")
async def back_to_main(callback: types.CallbackQuery):
    user = db.get_shop_user(callback.message.chat.id)
    lang = user['lang'] if user else 'ru'
    await callback.message.edit_text(get_text(lang, 'main_menu'), reply_markup=get_client_main_menu(lang))

@shop_router.callback_query(F.data.startswith("shop_cat_"))
async def show_category_products(callback: types.CallbackQuery):
    user = db.get_shop_user(callback.message.chat.id)
    lang = user['lang'] if user else 'ru'
    cat_id = int(callback.data.split("_")[2])
    
    products = db.get_shop_products(cat_id)
    if not products:
        await callback.answer(get_text(lang, 'no_products'), show_alert=True)
        return
        
    buttons = []
    for p in products:
        name = p.get(f'name_{lang}', p['name_ru'])
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"shop_prod_{p['id']}")])
        
    buttons.append([InlineKeyboardButton(text=get_text(lang, 'btn_back_cat'), callback_data="shop_catalog")])
    cat = db.get_shop_category(cat_id)
    cat_name = cat.get(f'name_{lang}', cat['name_ru'])
    
    await callback.message.edit_text(f"📁 <b>{cat_name}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@shop_router.callback_query(F.data.startswith("shop_prod_"))
async def show_product_details(callback: types.CallbackQuery):
    user = db.get_shop_user(callback.message.chat.id)
    lang = user['lang'] if user else 'ru'
    prod_id = int(callback.data.split("_")[2])
    
    p = db.get_shop_product(prod_id)
    if not p:
        await callback.answer("Error", show_alert=True)
        return
        
    name = p.get(f'name_{lang}', p['name_ru'])
    desc = p.get(f'desc_{lang}', p['desc_ru'])
    
    text = f"📦 <b>{name}</b>\n\n{desc}"
    
    buttons = [
        [InlineKeyboardButton(text=get_text(lang, 'btn_order'), callback_data=f"shop_order_{p['id']}")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_back'), callback_data=f"shop_cat_{p['category_id']}")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@shop_router.callback_query(F.data.startswith("shop_order_"))
async def process_order(callback: types.CallbackQuery):
    user = db.get_shop_user(callback.message.chat.id)
    lang = user['lang'] if user else 'ru'
    prod_id = int(callback.data.split("_")[2])
    
    p = db.get_shop_product(prod_id)
    if not p:
        return
        
    name = p.get(f'name_{lang}', p['name_ru'])
    username = callback.from_user.username
    contact = f"@{username}" if username else f"ID: {callback.from_user.id}"
    
    admin_msg = f"{get_text('ru', 'new_order_admin')}" \
                f"Товар: <b>{name}</b>\n" \
                f"Клиент: {contact}\n" \
                f"Язык клиента: {lang.upper()}"
                
    admins = db.get_all_admins()
    for admin in admins:
        try:
            from bot import bot
            await bot.send_message(admin['chat_id'], admin_msg, parse_mode="HTML")
        except Exception:
            pass
            
    await callback.message.edit_text(get_text(lang, 'order_sent'), reply_markup=get_client_main_menu(lang))
