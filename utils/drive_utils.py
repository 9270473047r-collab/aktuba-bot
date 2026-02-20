import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Путь к credentials.json (не храните боевой ключ в репозитории!)
# По умолчанию ожидаем файл в utils/credentials.json
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "credentials.json"),
)
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

def get_drive_service():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

def find_file_in_folder(file_name: str, folder_id: str):
    """Ищет файл по имени в папке Google Drive. Возвращает file_id или None."""
    service = get_drive_service()
    query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None
