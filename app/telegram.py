from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self._bot_token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{bot_token}"

    async def send_message(self, chat_id: int, text: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self._base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()

    async def get_file_path(self, file_id: str) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self._base_url}/getFile", params={"file_id": file_id})
            response.raise_for_status()
            return response.json()["result"]["file_path"]

    async def download_file(self, file_id: str, suffix: str) -> Path:
        file_path = await self.get_file_path(file_id)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self._file_base_url}/{file_path}")
            response.raise_for_status()
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(response.content)
            target = Path(tmp_file.name)
        return target
