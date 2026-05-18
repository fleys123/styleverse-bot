import json
from pathlib import Path

PHOTO_DIR = Path("user_photos")
TEMP_DIR = Path("temp")
LORA_DIR = Path("user_loras")

PHOTO_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
LORA_DIR.mkdir(exist_ok=True)

_profile_photos: dict[int, str] = {}


def get_profile_photo_dir() -> Path:
    return PHOTO_DIR


def get_temp_dir() -> Path:
    return TEMP_DIR


def register_profile_photo(user_id: int, path: str):
    _profile_photos[user_id] = path


def get_profile_photo_path(user_id: int) -> str | None:
    path = _profile_photos.get(user_id)
    if path and Path(path).exists():
        return path
    # Fallback: check disk (persists across restarts)
    disk_path = PHOTO_DIR / f"{user_id}.jpg"
    if disk_path.exists():
        _profile_photos[user_id] = str(disk_path)
        return str(disk_path)
    return None


def has_profile_photo(user_id: int) -> bool:
    return get_profile_photo_path(user_id) is not None


def save_user_lora(user_id: int, lora_url: str, trigger_word: str):
    data = {"url": lora_url, "trigger": trigger_word}
    (LORA_DIR / f"{user_id}.json").write_text(json.dumps(data))


def get_user_lora(user_id: int) -> dict | None:
    path = LORA_DIR / f"{user_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def has_user_lora(user_id: int) -> bool:
    return (LORA_DIR / f"{user_id}.json").exists()
