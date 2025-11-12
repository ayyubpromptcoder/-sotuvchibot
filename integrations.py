# integrations.py

import os
import logging
import datetime
import json
import asyncio # Asinxron ishlov berish uchun

# Tashqi kutubxonalar
# pip install gspread oauth2client
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    logging.error("gspread yoki oauth2client kutubxonalari o'rnatilmagan.")
    gspread = None
    ServiceAccountCredentials = None


logger = logging.getLogger(__name__)

# --- 1. SOZLAMALARNI ENV DAN YUKLASH ---
# Bu sozlamalar Render.com dagi Environment Variables (Atrof-muhit o'zgaruvchilari) dan olinadi.
# Render.com ga yuklaganingizda ushbu nomlar bilan kiriting:
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GCP_JSON_CONTENT = os.getenv("GCP_SERVICE_ACCOUNT_JSON")

# Bot tranzaksiyalarni yozadigan jadval nomi
SHEET_NAME = "Tovar Harakatlari"


# --- 2. GOOGLE SHEETS BILAN ULANISH FUNKSIYASI ---

def get_sheets_client():
    """Google Sheets API bilan ulanishni yaratadi. Service Account JSON kontentidan foydalanadi."""
    if not gspread or not ServiceAccountCredentials:
        return None # Kutubxonalar o'rnatilmagan

    if not GCP_JSON_CONTENT:
        logger.error("Integratsiya: GCP_SERVICE_ACCOUNT_JSON environment variable topilmadi.")
        return None
        
    try:
        # JSON stringini Python lug'atiga (dict) aylantiramiz
        creds_info = json.loads(GCP_JSON_CONTENT) 

        # Sheets va Drive API ga kirish uchun ruxsat doirasi
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # To'g'ridan-to'g'ri lug'at (dict) dan yuklab olish orqali xavfsiz ulanish
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        logger.info("Google Sheets Client muvaffaqiyatli yaratildi.")
        return client
        
    except Exception as e:
        logger.error(f"Integratsiya: Google Sheets ulanishida xato: {e}")
        return None

# --- 3. MA'LUMOT YOZISH FUNKSIYASI (ASOSIY TRANZAKSIYA) ---

async def log_transaction_to_sheet(
    seller_name: str, 
    product_name: str, 
    quantity: int, 
    price: int, 
    total_cost: int
):
    """
    Berilgan tranzaksiya ma'lumotlarini Google Sheetsga yozadi.
    Bu funksiya asinxron ravishda chaqirilishi kerak (log_transaction_to_sheet orqali).
    """
    
    # gspread bilan ishlash CPU-bound ish bo'lgani uchun, 
    # asinxron botni bloklamaslik uchun uni executor orqali chaqiramiz.
    loop = asyncio.get_event_loop()
    
    # Sinhron funksiyani asinxron tarzda boshqarish uchun executor ishlatiladi.
    await loop.run_in_executor(None, 
                               _sync_log_transaction_to_sheet, 
                               seller_name, 
                               product_name, 
                               quantity, 
                               price, 
                               total_cost)
    

# --- 4. YORDAMCHI SINHRON FUNKSIYA ---

def _sync_log_transaction_to_sheet(
    seller_name: str, 
    product_name: str, 
    quantity: int, 
    price: int, 
    total_cost: int
):
    """
    Google Sheetsga yozishni amalga oshiradigan sinxron funksiya.
    """
    client = get_sheets_client()
    if not client or not SHEET_ID:
        return logger.warning("Google Sheets integratsiyasi o'chirilgan yoki noto'g'ri sozlamalar.")

    try:
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Worksheetni nom bo'yicha olish, topilmasa birinchisiga yozish
        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.sheet1
            logger.warning(f"'{SHEET_NAME}' jadvali topilmadi. Ma'lumotlar birinchi jadvalga yozilmoqda.")

        # Joriy vaqtni tayyorlash
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Yoziladigan qator ma'lumotlari (Sizning jadvalingiz ustunlari tartibi)
        row_data = [
            timestamp,
            seller_name,
            product_name,
            quantity,
            price,
            total_cost,
            "Bot orqali berildi" # Izoh ustuni
        ]

        # Ma'lumotni jadvalning oxiriga qo'shish
        worksheet.append_row(row_data)
        logger.info(f"Google Sheetsga yozildi: {seller_name} - {product_name} - {quantity} dona")

    except Exception as e:
        logger.error(f"Google Sheetsga sinxron yozishda xato: {e}")
        
# --------------------------------------------------------------------------------
# Eslatma: Bu fayl ishga tushishi uchun Google Sheets'da ustunlar:
# | A: Sana/Vaqt | B: Sotuvchi | C: Mahsulot | D: Miqdor | E: Narxi | F: Jami Summa | G: Izoh |
# kabi tartiblangan bo'lishi kerak.
