================================================================
 CHESS ANALYTICS PROJECT — README
 Версия: v19.2 (Sprint L: Dashboard Context, INDEX и WebUI)
 Обновлён: 2026-11-06
================================================================

ЦЕЛЬ ПРОЕКТА:
  Анализ партий chess.com для игрока ~2600 в блице (bullet).
  Конечная цель игрока: 3000 рейтинга (GameR ≈ Chess.com).
  Проект = инструмент анализа, а не игра за игрока.

ИГРОК:
  • Играет ТОЛЬКО на телефоне (Android)
  • Blitz/bullet, преимущественно 1+0 и 3+2
  • Средняя скорость: 1.13–1.17 сек/ход
  • Стиль: быстрый интуит, сильный дебют, слабый миттельшпиль
  • Главная слабость: каскадный тильт, аллергия на агрессию

================================================================
 АРХИТЕКТУРА (src/analysis/)
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
    game.py            — доменная модель партии (центральная сущность)
    engine_pool.py     — пул процессов Stockfish
    cache.py           — кэширование промежуточных результатов
    constants.py       — константы (группировка дебютов = 6)
    helpers.py         — доменно-нейтральные утилиты (Stockfish, PGN)
    common.py          — ReportContext, read_report_file
    __init__.py        — публичный API пакета

  ── СБОРКА ДАШБОРДОВ (v19.2) ────────────────────────────────
    analysis/dashboard.py          — оркестратор (write_index + build_all)
    analysis/dashboard_helpers.py  — SQL для 00_INDEX (тренд, топ-3, StdDev)
    analysis/dashboards/           — 8 групп (01_openings ... 08_coach)
    analysis/dashboards/index.py   — сборщик 00_INDEX.txt

    Каждый дашборд (01..08) — это склейка отчётов одного домена
    в один текстовый файл в reports/dashboards/.
    В корне проекта лежит 00_INDEX.txt (Executive Summary).

  ── ДОМЕНЫ (src/analysis/<domain>/) ─────────────────────────
    Каждый домен = common.py + атомарные модули-отчёты.

    openings/
      anatomy.py         — группировка линий по 6 ходам
      reports.py         — 6 SQL-отчётов по дебютам
      planner.py         — план в миттельшпиль + 18 SQL-запросов
      planner_output.py  — вывод отчёта и домашних заданий

    middlegame/          (12 модулей — самый нагруженный домен)
      phase_deep.py, advantage_speed.py, transition.py,
      tactics.py, win_loss_conversion.py, positional_weaknesses.py,
      plan_retention.py, piece_activity.py, position_types.py,
      long_vs_short.py, summary.py

    psych_focus/
      blunder_anatomy.py, first_blunder.py, missed.py,
      review.py, graphs.py

    psych_state/
      time_management.py, hours_days.py, endurance.py,
      psych_tilt.py, daily_checkin.py
      __init__.py        — экспортирует run_* + write_checkin

    opponents/
      weakness.py, style.py, anti.py, position_type.py, time_deficit.py

  ── ОРКЕСТРАЦИЯ ─────────────────────────────────────────────
    run.py               — конвейер (01..13)
    13_dashboard_final.py — тонкий оркестратор (вызывает build_all)
    web_dashboard/       — Streamlit интерфейс (10 страниц)

================================================================
 СХЕМА БАЗЫ ДАННЫХ
================================================================

  games (основная таблица):
    url, end_time, white, black, opening, eco,
    my_rating, opp_rating, opp_username, won, draw, reason,
    is_lag, is_cheater,
    acpl, acpl_opening, acpl_middlegame, acpl_endgame,
    accuracy, critical_moments, max_eval_advantage, min_eval_advantage,
    momentum_after_blunder, eval_after_opening, opening_line,
    pgn, clocks, eval_history,
    flag_result, my_clock_at_timeout, opp_clock_at_timeout

  blunders (зевки):
    game_url, move_num, move_uci, loss_cp,
    pattern_tag, is_my_blunder, time_spent, next_move_time,
    fen_before, best_move_uci, missed_threat

  checkins (дневник):
    date, sleep_hours, mood, energy, stress, note

================================================================
 ТЕКУЩИЙ СТАТУС
================================================================

  ✅ Sprint A (дешёвые отчёты + ядро): завершён
  ✅ Sprint B (чек-ин + инфраструктура): завершён
  ✅ Sprint C (flag_result, missed_threat, clocks_at_timeout): завершён
  ✅ Sprint D (style_position_type, style_time_deficit, lag_report,
              crushed_by): завершён
  ✅ Sprint E–J (Модуляризация 05..13, ReportContext): завершён
  ✅ Sprint K / v19.1 (Перевод всех доменов на ReportContext)
  ✅ Sprint L / v19.2 (Дашборды и WebUI):
       • Выделен analysis/dashboard.py и analysis/dashboards/
       • Генерируется 00_INDEX.txt (Executive Summary) в корне
       • 8 файлов дашбордов в reports/dashboards/ (01..08)
       • Web Dashboard v19.2: 10 страниц (добавлены Coach и Opponents)
       • Добавлен график StdDev ACPL и GameR vs Perf
       • Обновлен вывод ошибок и фильтров в Blunders

================================================================
 ИСПРАВЛЕННЫЕ КРИТИЧЕСКИЕ БАГИ
================================================================

  • middlegame/common.py (эндшпиль) — «космический» ACPL эндшпиля.
  • opponents/anti.py — время соперника вместо своего.
  • opponents/time_deficit.py — дефицит всегда 0 (неверный индекс).
  • engine_pool.py — missed_threat считал шах, а не мат.
  • psych_state/time_management.py — panic_curve включал берсерк.
  • middlegame/advantage_speed.py — неверные индексы clocks (1.36 сек).
  • engine_pool.py → next_move_time — теперь заполняется (95.5%).
  • openings/anatomy.py → line_anatomy — группирует по 6 ходам (79 линий).

================================================================
 КЛЮЧЕВЫЕ ЦИФРЫ (на 2026-11-06 14:02, окно 90 дней)
================================================================

  Партий в базе:            2310 (без лагов/читеров)
  Средний рейтинг в окне:   2553
    • на начало 90д:        2596
    • последний:            2458 (тренд отрицательный)
  ACPL общий:               65 CP
  ACPL миттельшпиля:        75 CP ← главная дыра
  Winrate общий:            48.7%
  Скорость:                 1.13–1.17 сек/ход
  Победы по флагу:          35.7%
  Каскады в миттельшпиле:   59.4% (главная психологическая дыра)
  StdDev ACPL:              30.5 (высокий разброс — главная цель)
  Моментум после зевка:     125 CP (тильт)

================================================================
 ТОП-3 СЛАБОСТИ (по данным)
================================================================

  1. Каскадный тильт в миттельшпиле (59.4%)
     → psych_state/psych_tilt.py → cascade_tilt
     → лечение: правило «3 секунды после зевка»

  2. Слив перевеса (+3.0) (36.2%)
     → middlegame/win_loss_conversion.py
     → лечение: ставить цель на 2-3 хода при перевесе

  3. Аллергия на агрессию (18.0% winrate против aggressive)
     → opponents/style.py
     → лечение: план на 10-15 ходу против агрессоров

================================================================
 БЫСТРЫЙ СТАРТ
================================================================

  # Полный прогон (CLI)
  python run.py --keep-going

  # Только пересборка дашбордов и индекса
  python 13_dashboard_final.py

  # Только конкретный домен (v19.1)
  python -c "from src.analysis.psych_state import run_psych_tilt; run_psych_tilt()"
  python -c "from src.analysis.openings import run_openings; run_openings()"

  # Чек-ин
  python -c "from src.analysis.psych_state import write_checkin, _parse_checkin; write_checkin(_parse_checkin('сон=7,энергия=6,стресс=3'))"

  # Веб-дашборд
  streamlit run web_dashboard/app.py

================================================================
 КАРТА ПРОЕКТА (что где лежит и куда смотреть)
================================================================

  Легенда:
    [CORE]   — код ядра и доменов (python)
    [WEB]    — веб-интерфейс (Streamlit)
    [REPORT] — сгенерированные отчёты (txt)
    [DATA]   — сырые данные и БД (НЕ редактировать руками)
    [DOC]    — документация и правила
    [INPUT]  — конфиги для настройки проекта

  ┌─ [DOC] Корневые документы (читать в первую очередь) ───────┐
  ├── README.txt            ← ВЫ ЗДЕСЬ. Обзор проекта.
  ├── PROJECT_RULES.txt     ← Что НЕ предлагать (антипаттерны)
  ├── LIMITS.txt            ← Потолок аналитики, цель 3000
  ├── 00_INDEX.txt          ← DASHBOARD INDEX (executive summary)
  └── dashboard_FINAL.txt   ← Архив всех отчётов (~300КБ, legacy)
  └────────────────────────────────────────────────────────────┘

  ┌─ [DATA] Данные (не трогать руками) ────────────────────────┐
  ├── data/
  │    ├── chess.db                ← SQLite: games, blunders, checkins
  │    ├── chess_api_cache.json    ← Сырые ответы chess.com API
  │    ├── stockfish_cache.json    ← Результаты анализа Stockfish
  │    ├── stockfish_positions_cache.json.gz ← FEN-кэш для planner
  │    ├── cheaters.txt            ← Список забаненных соперников
  │    ├── codex_rules.json        ← Правила «Кодекса Пули»
  │    ├── config.json             ← [INPUT] player, email, stockfish_path
  │    └── backup/                 ← Бэкапы chess.db (5 последних)
  └────────────────────────────────────────────────────────────┘

  ┌─ [CORE] Код анализа (src/) ────────────────────────────────┐
  ├── src/
  │    ├── _common.py              ← BASE_DIR, REPORTS_DIR, CONFIG
  │    ├── _chess_utils.py         ← Парсинг PGN, clocks, стиль соперника
  │    ├── run.py                  ← Оркестратор конвейера (01..13)
  │    ├── 00_data_quality.py      ← Проверки целостности БД
  │    ├── 01_fetch_chess_api.py   ← Скачивание партий
  │    ├── 02_analyze_stockfish.py ← Stockfish-анализ (ACPL, зевки)
  │    ├── 02a_check_cheaters.py   ← Проверка статусов соперников
  │    ├── 03_migrate_sqlite.py    ← Запись в chess.db
  │    ├── 04_export_csv.py        ← Экспорт для внешних ИИ
  │    ├── 05_openings.py          ← → analysis/openings/
  │    ├── 06_middlegame.py        ← → analysis/middlegame/
  │    ├── 07_endgame.py           ← Эндшпиль (in-place)
  │    ├── 08_psych_focus.py       ← → analysis/psych_focus/
  │    ├── 09_psych_state.py       ← → analysis/psych_state/
  │    ├── 10_psych_rating.py      ← Рейтинг и прогресс (in-place)
  │    ├── 11_psych_opponents.py   ← → analysis/opponents/
  │    ├── 12_coach.py             ← Тренер: план, колода (in-place)
  │    ├── 13_dashboard_final.py   ← Тонкий оркестратор build_all()
  │    │
  │    ├── core/                   ← Общие метрики
  │    │    ├── метрики.py         ← game_rating, perf_rating, anchor
  │    │    ├── стили.py           ← Стиль соперника (PGN → стиль)
  │    │    └── пороги.py          ← get_threshold (из config.json)
  │    │
  │    └── analysis/               ← Пакет анализа (главный код)
  │         ├── __init__.py        ← Экспорт: DEPTH, build_all
  │         ├── game.py            ← [CORE] Модель партии → analyze_game()
  │         ├── engine_pool.py     ← [CORE] Пул Stockfish-движков
  │         ├── cache.py           ← [CORE] Загрузка/сохранение кэша
  │         ├── constants.py       ← [CORE] DEPTH, пороги зевков
  │         ├── helpers.py         ← [CORE] Оценка PGN, паттерны зевков
  │         ├── common.py          ← [CORE] ReportContext, read_report_file
  │         │
  │         ├── dashboard.py       ← Сборка 00_INDEX + 8 файлов
  │         ├── dashboard_helpers.py ← SQL для INDEX (тренд, StdDev)
  │         ├── dashboards/        ← 9 сборщиков: 00_index, 01_openings...
  │         │    ├── index.py, openings.py, middlegame.py, endgame.py
  │         │    ├── psych_focus.py, psych_state.py, psych_rating.py
  │         │    └── opponents.py, coach.py
  │         │
  │         ├── openings/          ← Дебюты
  │         │    ├── anatomy.py      ← Группировка линий по 6 ходам
  │         │    ├── reports.py      ← 6 SQL-отчётов по дебютам
  │         │    ├── planner.py      ← Opening Planner (18 SQL + Stockfish)
  │         │    └── planner_output.py ← Вывод planner + домашка
  │         │
  │         ├── middlegame/        ← Миттельшпиль (12 модулей)
  │         │    ├── phase_deep.py, advantage_speed.py, transition.py
  │         │    ├── tactics.py, win_loss_conversion.py
  │         │    ├── positional_weaknesses.py, plan_retention.py
  │         │    ├── piece_activity.py, position_types.py
  │         │    ├── long_vs_short.py, summary.py
  │         │    └── common.py
  │         │
  │         ├── psych_focus/       ← Зевки
  │         │    ├── blunder_anatomy.py, first_blunder.py
  │         │    ├── missed.py, review.py, graphs.py
  │         │    └── common.py
  │         │
  │         ├── psych_state/       ← Время/режим/тильт
  │         │    ├── time_management.py, hours_days.py
  │         │    ├── endurance.py, psych_tilt.py, daily_checkin.py
  │         │    └── common.py, __init__.py
  │         │
  │         └── opponents/         ← Соперники
  │              ├── weakness.py, style.py, anti.py
  │              ├── position_type.py, time_deficit.py
  │              └── common.py
  └────────────────────────────────────────────────────────────┘

  ┌─ [REPORT] Сгенерированные отчёты (reports/) ──────────────┐
  ├── reports/
  │    ├── dashboards/             ← 01_openings.txt ... 08_coach.txt
  │    ├── graphs/                 ← PNG-графики из psych_focus
  │    ├── reviews/                ← Разборы партий (psych_focus/review)
  │    ├── training/               ← Колода, тренажёр эндшпиля
  │    ├── opening_training/       ← Домашка по дебютам (planner)
  │    ├── ai_export/
  │    │    ├── latest/            ← CSV (последний экспорт)
  │    │    └── YYYY-MM-DD/        ← Срез за дату
  │    ├── time_report_windows.txt, hours_overview.txt, ...
  │    └── (все txt-отчёты по доменам)
  └────────────────────────────────────────────────────────────┘

  ┌─ [WEB] Веб-интерфейс (web_dashboard/) ─────────────────────┐
  ├── web_dashboard/
  │    ├── app.py                  ← Главная (10 страниц, INDEX)
  │    ├── requirements.txt        ← streamlit, plotly, python-chess
  │    ├── run_web.bat             ← Запуск в Windows
  │    ├── pages/
  │    │    ├── 1_Overview.py      ← Метрики + тренд + совет
  │    │    ├── 2_Openings.py      ← Дебюты + Planner
  │    │    ├── 3_ACPL.py          ← ACPL + StdDev + GameR vs Perf
  │    │    ├── 4_Endurance.py     ← Выносливость + каскады
  │    │    ├── 5_Blunders.py      ← 4 вкладки: зевки, колода,
  │    │    │                        первый зевок, missed_threats
  │    │    ├── 6_Analysis.py      ← Lichess iframe (FEN/PGN)
  │    │    ├── 7_Blitz.py         ← Игра против Stockfish
  │    │    ├── 8_Session_Tracker.py ← Последняя сессия (GameR)
  │    │    ├── 9_Coach.py         ← План недели + Кодекс
  │    │    └── 10_Opponents.py    ← Crushed_by + стиль vs рейтинг
  │    └── utils/
  │         ├── db.py              ← query_df (кэш по mtime)
  │         ├── chess_vis.py       ← SVG-доска, FEN из PGN
  │         └── engine.py          ← Stockfish (lazy)
  └────────────────────────────────────────────────────────────┘

  ┌─ ⚡ КУДА СМОТРЕТЬ ПЕРВЫМ (для нового чата) ────────────────┐
  │  1. README.txt (вы здесь) → цели проекта и архитектура      │
  │  2. PROJECT_RULES.txt → что НЕ предлагать                   │
  │  3. LIMITS.txt → потолок аналитики, цель 3000               │
  │  4. 00_INDEX.txt → сводка: рейтинг, слабости, план          │
  │  5. reports/dashboards/01_openings.txt ... 08_coach.txt     │
  │  6. web_dashboard/app.py → 10 страниц UI                    │
  │                                                             │
  │  ⚠️ data/chess.db — менять ТОЛЬКО через run.py.             │
  │  ⚠️ reports/*.txt — генерируются, не редактировать руками.  │
  │  ⚠️ Анализ — src/analysis/. Домены зафиксированы.           │
  └─────────────────────────────────────────────────────────────┘


================================================================
 ШКАЛА GameR (точность игры)
================================================================

  Важно: GameR ≈ рейтинг Chess.com на данных игрока.
    • Средний GameR (90 дней): 2546
    • Средний рейтинг:         2553
    • Разница: 7 пунктов — в пределах шума.

  2400–2600   КМС                    ← средний GameR игрока
  2600–2800   МФ (мастер ФИДЕ)
  2800–3000   ММ (международный)     ← P10 игрока (2893)
  3000–3200   МГ (гроссмейстер)
  3400–3500   Накамура / Карлсен / Фируджа

  Цель 3000 = стабилизировать P10, сократить разрыв P10–P90.
================================================================