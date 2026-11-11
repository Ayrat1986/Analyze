# ============================================================
# 14_export_pdf.py — Экспорт отчётов в PDF (v22.1 — True Rolling Perf)
# ============================================================
import os
import re
import json
import statistics
import sqlite3
import shutil
from datetime import datetime
from fpdf import FPDF
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import io

import _common
from analysis.dashboard_trends import get_daily_metrics_trend

REPORTS_DIR = str(_common.REPORTS_DIR)
BASE_DIR = str(_common.BASE_DIR)
DB_FILE = str(_common.BASE_DIR / "data" / "chess.db")
PDF_FILE = os.path.join(REPORTS_DIR, "dashboard_report.pdf")
TEMP_DIR = os.path.join(REPORTS_DIR, "temp_pdf")
FONT_DIR = os.path.join(str(_common.BASE_DIR / "src"), "fonts")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(FONT_DIR, exist_ok=True)

def ensure_font(name):
    target = os.path.join(FONT_DIR, name)
    if os.path.exists(target): return target
    win_path = os.path.join("C:\\Windows\\Fonts", name)
    if os.path.exists(win_path):
        try:
            shutil.copy2(win_path, target)
            return target
        except Exception: pass
    return None

FONT_REG = ensure_font("arial.ttf")
FONT_BOLD = ensure_font("arialbd.ttf")
FONT_ITAL = ensure_font("ariali.ttf")
FONT_MONO = ensure_font("cour.ttf")
FONT_MONO_BOLD = ensure_font("courbd.ttf")

if not FONT_REG or not FONT_BOLD or not FONT_MONO:
    print("❌ Не найдены шрифты Arial/Courier New. Проверь C:\\Windows\\Fonts\\")
    exit(1)

COLOR_PRIMARY = (41, 128, 185)
COLOR_DANGER = (231, 76, 60)
COLOR_SUCCESS = (46, 204, 113)
COLOR_BG_LIGHT = (245, 248, 250)

class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Chess Analytics Report — {datetime.now().strftime('%d.%m.%Y')}", align="R")
        self.ln(10)
        
    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Стр. {self.page_no()}", align="C")

def clean_text(text):
    text = re.sub(r'[^\x00-\x7F\u0400-\u04FF\s\.\,\-\+\%\(\)\[\]\:\|\/\(\)\!\"\'\*\=\_\#]', '', text)
    return text.strip()

def _plot_trend():
    data = get_daily_metrics_trend(30)
    if not data: return None
    
    df = pd.DataFrame(data)
    if df.empty: return None
    df['Дата'] = pd.to_datetime(df['Дата'])
    df.set_index('Дата', inplace=True)

    # Правильный скользящий Perf (по сырым победам/поражениям, а не по средним)
    df['roll_n'] = df['Игр'].rolling(window=7, min_periods=1).sum()
    df['roll_wins'] = df['Wins'].rolling(window=7, min_periods=1).sum()
    df['roll_draws'] = df['Draws'].rolling(window=7, min_periods=1).sum()
    df['roll_opp'] = (df['AvgOpp'] * df['Игр']).rolling(window=7, min_periods=1).sum() / df['roll_n']
    df['Perf_smooth'] = df['roll_opp'] + ((df['roll_wins'] + 0.5 * df['roll_draws']) / df['roll_n'] - 0.5) * 800

    # Сглаживание остальных метрик
    df['GameR_smooth'] = df['GameR'].rolling(window=7, min_periods=1).mean()
    df['SpeedR_smooth'] = df['SpeedR'].rolling(window=7, min_periods=1).mean()
    df['CombR_smooth'] = df['CombR'].rolling(window=7, min_periods=1).mean()
    df['Rating_smooth'] = df['Rating'].rolling(window=7, min_periods=1).mean()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df.index, df['GameR_smooth'], label='GameR (Точность)', color='#00CC96', linewidth=2.5)
    ax.plot(df.index, df['SpeedR_smooth'], label='SpeedR (Скорость)', color='#EF553B', linewidth=2)
    ax.plot(df.index, df['CombR_smooth'], label='CombR (Общий)', color='#AB63FA', linewidth=2.5, linestyle='--')
    ax.plot(df.index, df['Perf_smooth'], label='Perf (Результат)', color='#FFA15A', linewidth=2)
    ax.plot(df.index, df['Rating_smooth'], label='Рейтинг (Факт)', color='#636EFA', linewidth=2, linestyle=':')

    ax.set_title("Тренд за 30 дней (7-дн сглаживание)", fontsize=14, fontweight='bold')
    ax.set_ylabel("Рейтинг")
    ax.legend(loc='upper left', frameon=False)
    ax.grid(alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()

    path = os.path.join(TEMP_DIR, "trend.png")
    fig.savefig(path, dpi=150); plt.close(fig)
    return path

def _plot_blunder_map():
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
    cur.execute("""
        SELECT b.move_num, COUNT(*) FROM blunders b JOIN games g ON g.url = b.game_url
        WHERE g.is_lag=0 AND g.is_cheater=0 AND b.is_my_blunder=1 AND b.is_berserk=0 AND b.is_instant=0
        AND b.move_num BETWEEN 11 AND 30 GROUP BY b.move_num ORDER BY b.move_num
    """)
    rows = cur.fetchall(); conn.close()
    if not rows: return None
    moves = [r[0] for r in rows]; counts = [r[1] for r in rows]
    
    fig, ax = plt.subplots(figsize=(10, 4))
    colors = ['#EF553B' if c > max(counts)*0.8 else '#3498DB' for c in counts]
    ax.bar(moves, counts, color=colors, edgecolor='black', alpha=0.8)
    ax.set_title("Карта зевков (по номерам ходов)", fontsize=14, fontweight='bold')
    ax.set_xlabel("Номер хода"); ax.set_ylabel("Количество зевков")
    ax.grid(alpha=0.3, axis='y')
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "blunders.png")
    fig.savefig(path, dpi=150); plt.close(fig)
    return path

def _plot_acpl_distribution():
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
    cur.execute("SELECT acpl FROM games WHERE is_lag=0 AND is_cheater=0 AND acpl > 0")
    vals = sorted([r[0] for r in cur.fetchall()]); conn.close()
    if len(vals) < 10: return None
    
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.hist(vals, bins=30, color='#9B59B6', edgecolor='black', alpha=0.7)
    p10 = vals[int(len(vals)*0.1)]; p50 = vals[int(len(vals)*0.5)]; p90 = vals[int(len(vals)*0.9)]
    ax.axvline(p10, color='#00CC96', linestyle='--', linewidth=2, label=f'P10 (потолок): {p10:.0f}')
    ax.axvline(p50, color='#F1C40F', linestyle='--', linewidth=2, label=f'P50 (медиана): {p50:.0f}')
    ax.axvline(p90, color='#EF553B', linestyle='--', linewidth=2, label=f'P90 (дно): {p90:.0f}')
    ax.set_title("Распределение ACPL (Точность)", fontsize=14, fontweight='bold')
    ax.set_xlabel("ACPL"); ax.set_ylabel("Партий")
    ax.legend(frameon=False); ax.grid(alpha=0.3, axis='y')
    plt.tight_layout()
    path = os.path.join(TEMP_DIR, "acpl.png")
    fig.savefig(path, dpi=150); plt.close(fig)
    return path

def _draw_text_block(pdf, file_path, title):
    if not os.path.exists(file_path): return
    
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    pdf.set_text_color(0, 0, 0)
    start_y = pdf.get_y()
    pdf.set_fill_color(*COLOR_BG_LIGHT)
    
    for line in content.split("\n"):
        if line.startswith("###") or line.startswith("===") or line.startswith("---") or not line.strip(): continue
        clean_line = clean_text(line)
        if not clean_line: continue
        
        if clean_line.isupper() and len(clean_line) > 5:
            pdf.set_font("Arial", "B", 10)
            pdf.set_text_color(*COLOR_PRIMARY)
            pdf.ln(2)
        else:
            pdf.set_font("CourierNew", size=7.5)
            pdf.set_text_color(0, 0, 0)
            
        pdf.multi_cell(0, 4.5, clean_line, fill=True)
        pdf.ln(0.5)
        
    end_y = pdf.get_y()
    pdf.set_draw_color(200, 200, 200)
    pdf.rect(8, start_y - 2, 194, end_y - start_y + 4)

def generate_pdf():
    print(f"🔍 Шрифты: {FONT_REG}, {FONT_BOLD}, {FONT_ITAL}, {FONT_MONO}")
    print("🎨 Генерируем графики...")
    trend_img = _plot_trend()
    blunder_img = _plot_blunder_map()
    acpl_img = _plot_acpl_distribution()
    
    pdf = PDF()
    pdf.add_font("Arial", style="", fname=FONT_REG, uni=True)
    pdf.add_font("Arial", style="B", fname=FONT_BOLD, uni=True)
    pdf.add_font("Arial", style="I", fname=FONT_ITAL, uni=True)
    pdf.add_font("CourierNew", style="", fname=FONT_MONO, uni=True)
    pdf.add_font("CourierNew", style="B", fname=FONT_MONO_BOLD, uni=True)
    pdf.set_font("Arial", "", 10)
    
    pdf.add_page()
    pdf.set_fill_color(*COLOR_PRIMARY)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_font("Arial", "B", 28)
    pdf.set_text_color(255, 255, 255)
    pdf.set_y(15)
    pdf.cell(0, 10, "CHESS ANALYTICS", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(30)
    pdf.cell(0, 10, f"Игрок: {_common.CONFIG.get('player', '?')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 10, f"Дата отчёта: {datetime.now().strftime('%d.%m.%Y %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(20)
    pdf.set_font("Arial", "I", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 6, "Этот отчёт содержит ключевые метрики, визуализацию трендов и советы тренера.", align="C")
    
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 15, "Визуальный анализ", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    if trend_img and os.path.exists(trend_img): pdf.image(trend_img, w=190); pdf.ln(5)
    if blunder_img and os.path.exists(blunder_img): pdf.image(blunder_img, w=190); pdf.ln(5)
    if acpl_img and os.path.exists(acpl_img): pdf.image(acpl_img, w=190)
    
    _draw_text_block(pdf, os.path.join(BASE_DIR, "00_INDEX.txt"), "Dashboard Index")
    _draw_text_block(pdf, os.path.join(REPORTS_DIR, "08_coach.txt"), "Совет тренера")

    pdf.output(PDF_FILE)
    print(f"\n✅ PDF-отчёт с графиками: {PDF_FILE}")

def main():
    print("=" * 60)
    print(" 14_export_pdf.py — Экспорт отчётов в PDF (v22.1)")
    print("=" * 60)
    
    index_path = os.path.join(BASE_DIR, "00_INDEX.txt")
    if not os.path.exists(index_path):
        print(f"⚠️ {index_path} не найден. Сначала запусти 13_dashboard_final.py.")
        return
    generate_pdf()

if __name__ == "__main__":
    main()