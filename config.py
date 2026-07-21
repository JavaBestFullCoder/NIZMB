import os
import pytz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN", "6702099427:AAGXB9buUhOYWL1i5ui0QQiow93ZhV6GUf0")
HEAD_OFFICE_CODE = "GlavnyOffice111"
TZ_NAME = "Asia/Tashkent"
TZ = pytz.timezone(TZ_NAME)
DB_PATH = os.path.join(BASE_DIR, "bot.db")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

