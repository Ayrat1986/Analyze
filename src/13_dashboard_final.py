# ============================================================
# 13_dashboard_final.py — v19.3 (Fix: main() для run.py)
# Тонкий оркестратор: вызывает analysis.dashboard.build_all()
# ============================================================
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SRC_DIR)


def main():
    from analysis.dashboard import build_all
    build_all()


if __name__ == "__main__":
    main()