# ============================================================
# analysis/utils/build_cache.py — v20.2 (Очистка старых хэшей)
# ============================================================
import os
import hashlib
import json
import time
import _common

CACHE_DIR = str(_common.BASE_DIR / "data" / "build_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def _get_file_hash(filepath: str) -> str:
    if not os.path.exists(filepath): return "missing"
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        buf = f.read(65536)
        while buf:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def get_inputs_hash(files: list) -> str:
    hashes = [f"{f}:{_get_file_hash(f)}" for f in files]
    return hashlib.md5("|".join(hashes).encode()).hexdigest()

def is_up_to_date(step_name: str, files: list) -> bool:
    cache_file = os.path.join(CACHE_DIR, f"{step_name}.json")
    if not os.path.exists(cache_file): return False
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return cached.get("inputs_hash") == get_inputs_hash(files)
    except Exception:
        return False

def mark_completed(step_name: str, files: list):
    cache_file = os.path.join(CACHE_DIR, f"{step_name}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"inputs_hash": get_inputs_hash(files), "timestamp": time.time()}, f)

def cleanup_old_cache(days=30):
    """Удаляет хэши, которые не обновлялись больше N дней."""
    now = time.time()
    deleted = 0
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"): continue
        fpath = os.path.join(CACHE_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if now - data.get("timestamp", 0) > days * 86400:
                os.remove(fpath)
                deleted += 1
        except Exception:
            os.remove(fpath) # Битый файл — удаляем
            deleted += 1
    return deleted