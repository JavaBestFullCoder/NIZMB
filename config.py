import os
import pytz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
HEAD_OFFICE_CODE = "GlavnyOffice111"
TZ_NAME = "Asia/Tashkent"
TZ = pytz.timezone(TZ_NAME)
DB_PATH = os.path.join(BASE_DIR, "bot.db")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

