# src/_common.py
import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "data" / "config.json"
REPORTS_DIR = BASE_DIR / "reports"

def load_config():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

def log_start(script_name):
    REPORTS_DIR.mkdir(exist_ok=True)
    with open(REPORTS_DIR / "run_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] START {script_name}\n")

def log_end(script_name, status="OK"):
    with open(REPORTS_DIR / "run_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] END   {script_name} — {status}\n")