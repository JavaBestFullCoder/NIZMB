import os
from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_DRIVE_FOLDER_ID

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


async def _get_service():
    try:
        from google.oauth2.service_account import Credentials as SACredentials
        from googleapiclient.discovery import build
    except ImportError:
        return None

    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        return None
    try:
        creds = SACredentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception:
        return None


async def upload_file(filepath: str, folder_id: str | None = None) -> str | None:
    from googleapiclient.http import MediaFileUpload

    folder = folder_id or GOOGLE_DRIVE_FOLDER_ID
    if not folder:
        return None

    service = await _get_service()
    if service is None:
        return None

    try:
        file_metadata = {"name": os.path.basename(filepath), "parents": [folder]}
        media = MediaFileUpload(
            filepath, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return file.get("webViewLink")
    except Exception:
        return None


async def is_configured() -> bool:
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        return False
    if not GOOGLE_DRIVE_FOLDER_ID:
        return False
    return True


def setup_instructions() -> str:
    return (
        "📋 Для настройки Google Диска:\n\n"
        "1. Создайте сервисный аккаунт в Google Cloud Console\n"
        "2. Включите Google Drive API\n"
        "3. Скачайте JSON-ключ и сохраните как credentials.json\n"
        "4. Создайте папку на Google Диске и дайте доступ сервисному аккаунту\n"
        "5. Укажите ID папки в переменной GOOGLE_DRIVE_FOLDER_ID\n"
        "   или отправьте его боту командой /setfolder <ID>"
    )
