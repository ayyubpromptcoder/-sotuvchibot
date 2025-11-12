import logging
import asyncio
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramBadRequest

# Loyihaning ichki modullarini import qilish
from db_models import Base, Product, Seller, SellerProduct
from db import init_db, get_or_create_product, add_new_seller, get_all_products, get_all_sellers, get_seller_by_id, get_product_by_name, add_product_to_seller, get_seller_products_info, get_all_seller_passwords_list

# .env faylini yuklash
load_dotenv()

# --- 1. Konfiguratsiya ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

# Global sozlamalar
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 2. Admin Vaziyatlari (FSM - Holat Boshqaruvi) ---
class AdminState(StatesGroup):
    # Mahsulot qo'shish
    waiting_for_product_name = State()
    waiting_for_product_price = State()
    
    # Sotuvchi qo'shish
    waiting_for_seller_name = State()
    waiting_for_seller_neighborhood = State()
    waiting_for_seller_phone = State()
    waiting_for_seller_password = State()

    # Sotuvchiga tovar berish
    waiting_for_product_name_for_seller = State()
    waiting_for_product_quantity_for_seller = State()
    waiting_for_new_product_price_for_seller = State()

# --- 3. Sotuvchi Vaziyatlari (FSM) ---
class SellerState(StatesGroup):
    waiting_for_login_password = State()
    
# --- 4. Yordamchi Funksiyalar ---

def is_admin(user_id: int) -> bool:
    """Faqat ADMIN_ID uchun ruxsat beradi."""
    return user_id == ADMIN_ID

# --- 5. Tugmalar (Keyboards) ---

# Admin Menyusi (Reply Keyboard)
admin_main_menu = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False, keyboard=[
    [KeyboardButton(text="/mahsulot")],
    [KeyboardButton(text="/sotuvchi")]
])

# /mahsulot tugmalari (Inline Keyboard)
mahsulot_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📋 Barcha Mahsulotlar", callback_data="admin_products_all")],
    [InlineKeyboardButton(text="➕ Yangi Mahsulot Kiritish", callback_data="admin_products_add")]
])

# /sotuvchi tugmalari (Inline Keyboard)
sotuvchi_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💰 Sotuvchilardagi Mahsulotlar (Jami)", callback_data="admin_seller_total_info")],
    [InlineKeyboardButton(text="👥 Sotuvchilar Ro'yxati", callback_data="admin_seller_list")],
    [InlineKeyboardButton(text="➕ Yangi Sotuvchi Qo'shish", callback_data="admin_seller_add")],
    [InlineKeyboardButton(text="🔐 Sotuvchilar Parollari", callback_data="admin_seller_passwords")],
])

# --- 6. HANDLERS (Umumiy va Admin Buyruqlar) ---

@dp.message(Command("start"))
async def command_start_handler(message: types.Message, state: FSMContext):
    await state.clear() # Har doim /start bosilganda barcha holatlarni o'chirish
    
    if is_admin(message.from_user.id):
        await message.answer(
            f"Assalomu alaykum, Administrator! 😊\n\nKerakli bo'limni tanlang yoki buyruq bering:",
            reply_markup=admin_main_menu
        )
    else:
        # Sotuvchi kirish qismi
        await message.answer("Assalomu alaykum! Tizimga kirish uchun maxsus parolni kiriting.")
        await state.set_state(SellerState.waiting_for_login_password)

@dp.message(Command("mahsulot"))
async def handle_mahsulot(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer(
        "Mahsulotlar bo'limi:\nQuyidagi amallardan birini tanlang:",
        reply_markup=mahsulot_menu
    )

@dp.message(Command("sotuvchi"))
async def handle_sotuvchi(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer(
        "Sotuvchilar bo'limi:\nQuyidagi amallardan birini tanlang:",
        reply_markup=sotuvchi_menu
    )

# --- 7. ADMIN CALLBACK BOSHQARUVI ---

@dp.callback_query(F.data == "admin_products_all")
async def show_all_products(callback: types.CallbackQuery):
    """Barcha mahsulotlar ro'yxatini chiqaradi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
    await callback.answer()
    
    products = await get_all_products()
    if not products:
        text = "Bazada hozircha hech qanday mahsulot yo'q."
    else:
        text = "📋 **Barcha Mahsulotlar Ro'yxati:**\n\n"
        for i, prod in enumerate(products, 1):
            # Narxni so'm formatiga o'tkazish tavsiya etiladi
            formatted_price = f"{prod.price:,}".replace(",", " ")
            text += f"{i}. **{prod.name}** - *{formatted_price} so'm*\n"

    await callback.message.answer(text, parse_mode="Markdown")

# --- 8. YANGI MAHSULOT QO'SHISH (FSM) ---

@dp.callback_query(F.data == "admin_products_add")
async def start_add_new_product(callback: types.CallbackQuery, state: FSMContext):
    """Yangi mahsulot qo'shish jarayonini boshlaydi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
        
    await callback.answer()
    await callback.message.answer("Yangi Mahsulot Kiritish:\nIltimos, **mahsulot nomini** kiriting:")
    await state.set_state(AdminState.waiting_for_product_name)

@dp.message(AdminState.waiting_for_product_name, F.text)
async def process_product_name(message: types.Message, state: FSMContext):
    await state.update_data(new_product_name=message.text.strip())
    await message.answer("Mahsulot nomi qabul qilindi.\nEndi mahsulotning **narxini** kiriting (faqat raqamlarda, masalan: 12500):")
    await state.set_state(AdminState.waiting_for_product_price)

@dp.message(AdminState.waiting_for_product_price, F.text)
async def process_product_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price <= 0: raise ValueError
    except ValueError:
        return await message.answer("Narx noto'g'ri formatda. Iltimos, faqat musbat butun son kiriting.")

    data = await state.get_data()
    name = data['new_product_name']

    try:
        product, is_new = await get_or_create_product(name=name, price=price)
        
        if not is_new and product.price != price:
             # Mahsulot mavjud bo'lsa, narxini yangilaymiz
             product.price = price
             is_new = False # Aslida yangilandi
        
        await message.answer(
            f"✅ **Muvaffaqiyatli!**\nMahsulot: **{product.name}**\nNarxi: **{product.price:,} so'm**\nStatus: {'Yangi mahsulot qo\'shildi' if is_new else 'Narxi yangilandi'}"
            .replace(",", " "), parse_mode="Markdown")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Mahsulot kiritishda xato: {e}")
        await message.answer(f"Xato yuz berdi. Iltimos, qaytadan urinib ko'ring.")
        await state.clear()


# --- 9. YANGI SOTUVCHI QO'SHISH (FSM) ---

@dp.callback_query(F.data == "admin_seller_add")
async def start_add_new_seller(callback: types.CallbackQuery, state: FSMContext):
    """Yangi sotuvchi qo'shish jarayonini boshlaydi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
        
    await callback.answer()
    await callback.message.answer("Yangi Sotuvchi Kiritish:\nIltimos, **sotuvchining ismini** kiriting:")
    await state.set_state(AdminState.waiting_for_seller_name)

@dp.message(AdminState.waiting_for_seller_name, F.text)
async def process_seller_name(message: types.Message, state: FSMContext):
    await state.update_data(seller_name=message.text.strip())
    await message.answer("Ismi qabul qilindi.\nEndi sotuvchining **mahallasi (hududi)** ni kiriting:")
    await state.set_state(AdminState.waiting_for_seller_neighborhood)

@dp.message(AdminState.waiting_for_seller_neighborhood, F.text)
async def process_seller_neighborhood(message: types.Message, state: FSMContext):
    await state.update_data(seller_neighborhood=message.text.strip())
    await message.answer("Mahalla qabul qilindi.\nEndi sotuvchining **telefon raqamini** kiriting (Masalan: 901234567):")
    await state.set_state(AdminState.waiting_for_seller_phone)

@dp.message(AdminState.waiting_for_seller_phone, F.text)
async def process_seller_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    # Oddiy telefon raqami tekshiruvi (faqat raqam bo'lishi)
    if not phone.isdigit():
        return await message.answer("Telefon raqami noto'g'ri formatda. Iltimos, faqat raqamlarni kiriting.")

    await state.update_data(seller_phone=phone)
    await message.answer("Telefon raqami qabul qilindi.\nEndi sotuvchi **botga kirishi uchun maxsus parolni** kiriting:")
    await state.set_state(AdminState.waiting_for_seller_password)

@dp.message(AdminState.waiting_for_seller_password, F.text)
async def process_seller_password(message: types.Message, state: FSMContext):
    seller_password = message.text.strip()
    
    if len(seller_password) < 4:
        return await message.answer("Parol juda qisqa. Kamida 4 belgi bo'lishi kerak.")
        
    data = await state.get_data()
    
    try:
        new_seller = await add_new_seller(
            name=data['seller_name'],
            neighborhood=data['seller_neighborhood'],
            phone_number=data['seller_phone'],
            password=seller_password
        )
        
        await message.answer(
            f"✅ **Yangi sotuvchi muvaffaqiyatli qo'shildi!**\n"
            f"Ism: **{new_seller.name}**\n"
            f"Mahalla: {new_seller.neighborhood}\n"
            f"Telefon: {new_seller.phone_number}\n"
            f"Maxsus Parol: `{new_seller.password}`"
            f"\n\n**(Ushbu parolni sotuvchiga bering.)**",
            parse_mode="Markdown"
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Sotuvchi kiritishda xato: {e}")
        await message.answer(f"Xato yuz berdi. Ehtimol, telefon raqami allaqachon bazada mavjud.")
        await state.clear()

# --- 10. QOLGAN SOTUVCHI FUNKSIYALARI (Boshlanish) ---

@dp.callback_query(F.data == "admin_seller_list")
async def show_all_sellers_list(callback: types.CallbackQuery):
    """Barcha sotuvchilar ro'yxatini alifbo tartibidagi tugmalar sifatida chiqaradi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
    await callback.answer()
    
    sellers = await get_all_sellers()
    if not sellers:
        return await callback.message.answer("Bazada hozircha sotuvchilar yo'q.")
    
    # Sotuvchilarni alifbo bo'yicha saralash
    sorted_sellers = sorted(sellers, key=lambda s: s.name)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s.name, callback_data=f"seller_detail_{s.id}")] 
        for s in sorted_sellers
    ])
    
    await callback.message.answer("👥 **Barcha Sotuvchilar Ro'yxati:**\n(Kerakli sotuvchini tanlang)", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("seller_detail_"))
async def show_seller_details(callback: types.CallbackQuery):
    """Tanlangan sotuvchi uchun amallar menyusini chiqaradi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
    await callback.answer()
    
    seller_id = int(callback.data.split('_')[-1])
    seller = await get_seller_by_id(seller_id)
    
    if not seller:
        return await callback.message.answer("Sotuvchi topilmadi.")
        
    # Sotuvchi uchun amallar menyusi
    menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Mahsulotlar va Narxlar (Qarzdorlik)", callback_data=f"seller_debt_{seller_id}")],
        [InlineKeyboardButton(text="📦 Sotuvchiga Yangi Tovar Berish", callback_data=f"seller_give_product_{seller_id}")],
        # [InlineKeyboardButton(text="🔐 Sotuvchining Paroli", callback_data=f"seller_password_single_{seller_id}")],
    ])
    
    await callback.message.answer(f"**{seller.name}** ({seller.neighborhood}) bilan bog'liq amallar:", reply_markup=menu, parse_mode="Markdown")

@dp.callback_query(F.data == "admin_seller_passwords")
async def show_all_seller_passwords(callback: types.CallbackQuery):
    """Barcha sotuvchilar parollarini chiqaradi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
    await callback.answer()

    passwords_list = await get_all_seller_passwords_list()
    
    if not passwords_list:
        text = "Bazada sotuvchilar yo'q."
    else:
        text = "🔐 **Barcha Sotuvchilar Parollari:**\n\n"
        for seller_name, password in passwords_list:
            text += f"**{seller_name}**: `{password}`\n"
        text += "\n⚠️ Parollarni uchinchi shaxslarga bermang!"

    await callback.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("seller_give_product_"))
async def start_give_product_to_seller(callback: types.CallbackQuery, state: FSMContext):
    """Sotuvchiga tovar berish jarayonini boshlaydi."""
    if not is_admin(callback.from_user.id): return await callback.answer("Ruxsat yo'q.")
    await callback.answer()
    
    seller_id = int(callback.data.split('_')[-1])
    seller = await get_seller_by_id(seller_id)
    
    if not seller:
        return await callback.message.answer("Sotuvchi topilmadi.")

    await state.update_data(current_seller_id=seller_id, seller_name=seller.name)
    await callback.message.answer(
        f"**{seller.name}**ga tovar berish:\nIltimos, **mahsulot nomini** kiriting (bazadagi yoki yangi):",
        parse_mode="Markdown"
    )
    await state.set_state(AdminState.waiting_for_product_name_for_seller)

# Qolgan FSM qismlari (Mahsulot nomi, soni, yangi narx) shu yerga qo'shiladi...


# --- 11. BOTNI ISHGA TUSHIRISH FUNKSIYASI ---

async def main():
    """Botning asosiy ishga tushirish mantig'i (Long Polling)"""
    logger.info("Bot ishga tushirilmoqda...")
    
    if not BOT_TOKEN or ADMIN_ID is None:
        logger.error("BOT_TOKEN yoki ADMIN_ID topilmadi. Bot ishga tushirilmadi.")
        return 

    # DB ni ishga tushirish
    try:
        await init_db()
        logger.info("Ma'lumotlar bazasi tayyor.")
    except Exception as e:
        logger.error(f"DB initsializatsiyasida jiddiy xato: {e}. Bot ishga tushirilmadi.")
        return

    # Long Pollingni ishga tushirish
    await dp.start_polling(bot)

if __name__ == '__main__':
    # Event Loopni ishga tushirish
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot o'chirildi.")
    except Exception as e:
        logger.error(f"Asosiy bot xatosi: {e}")
