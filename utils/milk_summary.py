import os

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Путь к credentials.json (не храните боевой ключ в репозитории!)
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(__file__), "credentials.json"),
)

def find_file_in_folder_by_name(filename: str, folder_id: str) -> str | None:
    """
    Ищет файл по имени в конкретной папке Google Drive.
    Возвращает file_id или None, если не найден.
    """
    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build('drive', 'v3', credentials=creds)
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=1
    ).execute()
    files = results.get('files', [])
    if not files:
        return None
    return files[0]['id']
