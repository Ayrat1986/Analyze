================================================================
 CHESS ANALYTICS PROJECT — README
 Версия: v23.1 (Исправлена шкала квалификаций)
 Обновлён: 2026-11-10
================================================================

ЦЕЛЬ ПРОЕКТА:
  Анализ партий chess.com для игрока ~2500-2600 в bullet (1+0).
  Конечная цель игрока: 3000 рейтинга Chess.com.
  Проект = инструмент анализа, а не игра за игрока.

ИГРОК:
  • Играет ТОЛЬКО на телефоне (Android)
  • ОСНОВНОЙ КОНТРОЛЬ: 1+0 (bullet).
    Все формулы, калибровки, отчёты — на 1+0. База времени = 60 сек.
  • ТУРНИРНЫЙ КОНТРОЛЬ: 3+2 (blitz). Рассматривается отдельно.
  • Средняя скорость: 1.13–1.17 сек/ход (на 1+0)
  • Стиль: быстрый интуит, сильный дебют, слабый миттельшпиль
  • Главная слабость: каскадный тильт, аллергия на агрессию,
    цейтнот при перевесе (играет на 28% медленнее при +3.0)

================================================================
 АРХИТЕКТУРА (src/)
================================================================

  chess.com API
       │
       ▼
  data/chess_api_cache.json
       │
       ▼
  data/stockfish_cache.json  (Stockfish, ACPL, зевки, PGN, clocks)
       │
       ▼
  data/chess.db  (SQLite — единый источник для отчётов и дашборда)

  ── ЯДРО (src/analysis/) ────────────────────────────────────
    game.py            — доменная модель партии (v21.0: opp_style)
    engine_pool.py     — пул Stockfish (защита от BrokenPipe)
    cache.py           — кэширование промежуточных результатов
    constants.py       — константы (DEPTH, пороги зевков)
    helpers.py         — доменно-нейтральные утилиты
    common.py          — WAL-режим, WINDOWS, RATING_BUCKETS
    __init__.py        — публичный API пакета

  ── НОВОЕ В v23.1 ───────────────────────────────────────────
    analysis/utils/build_cache.py    — Хэши для инкрементальной сборки
    analysis/dashboard_aggression.py — Агрессия (вынесено)
    analysis/dashboard_trends.py     — Тренды и графики (вынесено)
    analysis/coach/                  — Пакет тренера (4 модуля)
    analysis/psych_rating/           — Пакет рейтинга (6 модулей)
    analysis/openings/cheat_sheets.py — Шпаргалки D00, D02, D10
    analysis/opponents/trainer.py    — Тренажер анти-агрессора
    14_export_pdf.py                 — Генерация PDF с графиками

  ── СБОРКА ДАШБОРДОВ ────────────────────────────────────────
    analysis/dashboard.py          — оркестратор
    analysis/dashboard_helpers.py  — фасад (SQL для 00_INDEX)
    analysis/dashboards/           — 9 сборщиков

  ── ДОМЕНЫ ──────────────────────────────────────────────────
    openings/       — anatomy, reports, planner, cheat_sheets
    middlegame/     — 11 модулей (phase_deep, advantage_speed, ...)
    psych_focus/    — blunder_anatomy, first_blunder, missed, review
    psych_state/    — time_management, speed_rating, combined_rating
    opponents/      — weakness, style, anti, position_type, trainer

  ── ОРКЕСТРАЦИЯ ─────────────────────────────────────────────
    run.py               — конвейер (v20.9: --fast, --force, кэш)
    13_dashboard_final.py — тонкий оркестратор

================================================================
 СХЕМА БАЗЫ ДАННЫХ
================================================================

  games (основная таблица):
    url, end_time, white, black, opening, eco,
    my_rating, opp_rating, opp_username, won, draw, reason,
    is_lag, is_cheater, acpl, acpl_opening, acpl_middlegame,
    acpl_endgame, accuracy, critical_moments, max_eval_advantage,
    min_eval_advantage, momentum_after_blunder, eval_after_opening,
    opening_line, pgn, clocks, eval_history, time_control,
    flag_result, my_clock_at_timeout, opp_clock_at_timeout,
    opp_style (v21.0)

  blunders (зевки):
    game_url, move_num, move_uci, loss_cp, pattern_tag,
    is_my_blunder, time_spent, next_move_time,
    fen_before, best_move_uci, missed_threat

  checkins (дневник):
    date, sleep_hours, mood, energy, stress, note

  trainer_progress (UI-состояние тренировок):
    task_hash, task_type, fen, status, attempts,
    last_seen, next_review, created_at

================================================================
 ТЕКУЩИЙ СТАТУС (v23.1)
================================================================

  ✅ Sprint A–O (v19.1–v22.1): завершены
  ✅ Sprint P / v23.1 (Критический пересмотр правил):
       • PROJECT_RULES.txt: Δ (Delta) — главная метрика.
       • GameR ≠ рейтинг Chess.com. Рейтинг ≈ Perf.
       • Агрессия — рычаг против сильных (2600+).
       • README.txt: исправлена шкала квалификаций.
       • LIMITS.txt: путь к 3000 через Δ, а не только P90.
       • START_HERE.txt: обновлен под новые правила.

================================================================
 КЛЮЧЕВЫЕ ЦИФРЫ (на 2026-11-10, окно 90 дней)
================================================================

  Партий в базе:            2438 (без лагов/читеров)
  Средний рейтинг в окне:   2545
    • на начало 90д:        2596
    • последний:            2505
  ACPL общий:               65 CP
  ACPL миттельшпиля:        74 CP ← главная дыра
  ACPL P10 (потолок):       31.0 (GameR 2890)
  ACPL P50 (медиана):       61.0
  ACPL P90 (дно):           103.9 (GameR 2161)
  StdDev ACPL:              30.4
  Winrate общий:            48.8%
  Скорость:                 1.17 сек/ход
  Победы по флагу:          35.9%
  Каскады в миттельшпиле:   59.2%
  Моментум после зевка:     122 CP
  Лаги:                     34.3% партий (winrate −16%)
  CombinedR (90д):          ~2544 (≈ Perf 2542)
  SpeedR (90д):             ~2540 (≈ GameR 2549)
  Δ (Delta, 90д):           +9 (баланс)

================================================================
 ТОП-3 СЛАБОСТИ (по данным)
================================================================

  1. Слив перевеса (+3.0) (36.2%)
     → middlegame/win_loss_conversion.py
     → лечение: при +3.0 — держи ритм (не замедляйся без причины)

  2. Цейтнот (просрочки) (25%)
     → psych_state/time_management.py
     → лечение: на 20-м ходу при <15 сек — форсируй размен

  3. Каскадный тильт в миттельшпиле (59.2%)
     → psych_state/psych_tilt.py → cascade_tilt
     → лечение: правило «3 секунды после зевка»

  Бонус: «Час X» — первый зевок в среднем на 17-м ходу.
     → лечение: на ходах 10-15 — замедлись в 2 раза, проверь угрозы.

================================================================
 БЫСТРЫЙ СТАРТ
================================================================

  # Полный прогон (CLI)
  python run.py --keep-going

  # Проверить, что будет запущено (без запуска)
  python run.py --dry-run

  # Только конкретные шаги (5=дебюты, 6=миттельшпиль)
  python run.py --steps 5,6

  # Быстрый режим (пропуск тяжелых шагов 05, 06)
  python run.py --fast

  # Принудительный пересчет (игнорировать кэш)
  python run.py --force

  # Пересборка дашбордов
  python 13_dashboard_final.py

  # PDF-отчет
  python 14_export_pdf.py

================================================================
 КАРТА ПРОЕКТА (что где лежит)
================================================================

  ┌─ [DOC] Корневые документы (читать первыми) ────────────────┐
  ├── START_HERE.txt        ← ★ НАЧНИ ЗДЕСЬ (5 шагов) ★
  ├── README.txt            ← ВЫ ЗДЕСЬ
  ├── PROJECT_RULES.txt     ← Что НЕ предлагать
  ├── LIMITS.txt            ← Потолок аналитики, путь к 3000
  ├── 00_INDEX.txt          ← DASHBOARD INDEX
  └── dashboard_FINAL.txt   ← Архив (~300КБ, legacy)
  └────────────────────────────────────────────────────────────┘

  ┌─ [DATA] Данные (не трогать руками) ────────────────────────┐
  ├── data/
  │    ├── chess.db                ← SQLite (games, blunders, checkins, trainer_progress)
  │    ├── chess_api_cache.json    ← Сырые ответы API
  │    ├── stockfish_cache.json    ← Результаты Stockfish
  │    ├── combined_rating_coefs.json ← Коэффициенты CombinedR
  │    ├── codex_rules.json        ← «Кодекс Пули»
  │    ├── config.json             ← player, email, stockfish_path
  │    ├── build_cache/            ← Хэши шагов (для run.py)
  │    └── backup/                 ← Бэкапы (5 последних)
  └────────────────────────────────────────────────────────────┘

  ┌─ [CORE] Код анализа (src/) ────────────────────────────────┐
  ├── src/
  │    ├── _common.py
  │    ├── _chess_utils.py
  │    ├── run.py                  ← Оркестратор (v20.9)
  │    ├── 00_data_quality.py
  │    ├── 01_fetch_chess_api.py
  │    ├── 02_analyze_stockfish.py
  │    ├── 02a_check_cheaters.py
  │    ├── 03_migrate_sqlite.py    ← WAL + индексы + opp_style
  │    ├── 04_export_csv.py
  │    ├── 05_openings.py
  │    ├── 06_middlegame.py
  │    ├── 07_endgame.py
  │    ├── 08_psych_focus.py
  │    ├── 09_psych_state.py
  │    ├── 10_psych_rating.py      ← Оркестратор
  │    ├── 11_psych_opponents.py   ← Оркестратор
  │    ├── 12_coach.py             ← Оркестратор
  │    ├── 13_dashboard_final.py
  │    ├── 14_export_pdf.py        ← ★ НОВЫЙ
  │    │
  │    ├── core/
  │    │    ├── метрики.py         ← game_rating, perf_rating
  │    │    ├── стили.py           ← get_style
  │    │    ├── пороги.py          ← get_threshold
  │    │    └── time_control.py    ← 1+0 / 3+2
  │    │
  │    └── analysis/               ← Пакет анализа
  │         ├── common.py          ← WAL, WINDOWS, RATING_BUCKETS
  │         ├── game.py            ← opp_style, board.peek()
  │         ├── engine_pool.py
  │         ├── cache.py
  │         ├── constants.py
  │         ├── helpers.py
  │         ├── dashboard.py
  │         ├── dashboard_helpers.py ← фасад
  │         ├── dashboard_aggression.py ← НОВЫЙ
  │         ├── dashboard_trends.py     ← НОВЫЙ
  │         ├── dashboards/        ← 9 сборщиков
  │         ├── openings/          ← +cheat_sheets
  │         ├── middlegame/
  │         ├── psych_focus/
  │         ├── psych_state/
  │         ├── psych_rating/      ← НОВЫЙ (6 модулей)
  │         ├── coach/             ← НОВЫЙ (4 модуля)
  │         ├── trainer/           ← НОВЫЙ (smart_deck)
  │         ├── utils/             ← НОВЫЙ (build_cache)
  │         └── opponents/         ← +trainer
  └────────────────────────────────────────────────────────────┘

  ┌─ [REPORT] Отчёты (reports/) ───────────────────────────────┐
  ├── reports/
  │    ├── dashboards/             ← 01..08 (сводки за 5 строк)
  │    ├── graphs/                 ← PNG-графики
  │    ├── reviews/                ← Разборы партий
  │    ├── training/               ← Колода, эндшпиль
  │    ├── dashboard_report.pdf    ← ★ PDF-отчет
  │    └── (txt-отчёты по доменам)
  └────────────────────────────────────────────────────────────┘

================================================================
 ШКАЛА РЕЙТИНГА CHESS.COM И КВАЛИФИКАЦИЙ (v23.1 — ИСПРАВЛЕНО)
================================================================

  ⚠️ ВАЖНО: GameR — это только потенциал точности.
  Реальный рейтинг Chess.com ≈ Perf (Результат).
  Именно рейтинг Chess.com определяет квалификацию.

  2400–2600   КМС                    ← средний рейтинг (2545)
  2600–2800   МФ (мастер ФИДЕ)
  2800–3000   ММ (международный)     ← цель (3000)
  3000–3200   МГ (гроссмейстер)
  3400–3500   Накамура / Карлсен

  Твой средний рейтинг = 2545 (КМС).
  Твой P10 GameR = 2890 — это потенциал, но он не равен рейтингу.
  Разрыв = цейтнот, тильт, агрессия.

  Цель 3000 = поднять реальный рейтинг, а не GameR.
  Путь: держать Δ в ±30, убрать лаги, каскады, цейтнот.
================================================================