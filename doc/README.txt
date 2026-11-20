================================================================
 CHESS ANALYTICS PROJECT — README
 Версия: v26.0 (Полная автоматизация GitHub Actions)
 Обновлён: 2026-11-20
================================================================

🌐 ССЫЛКИ НА ПРОЕКТ:
  • GitHub Repository: https://github.com/Ayrat1986/Analyze
  • Streamlit Dashboard: https://analyze-9xd3ohlvpzsie2mxuyvpmz.streamlit.app/

ЦЕЛЬ ПРОЕКТА:
  Анализ партий chess.com для игрока ~2500-2600 в bullet (1+0).
  Конечная цель игрока: 3000 рейтинга Chess.com.
  Проект = инструмент анализа, а не игра за игрока.

ТЕКУЩАЯ СИТУАЦИЯ (Ноябрь 2026):
  Игрок вошел в "Фазу Калибровки Паттернов". Он сознательно замедлился 
  (Δ > +100), чтобы очистить мусорные автоматизмы. Винрейт временно 
  просел, но GameR (точность) вырос до 2600+. Задача: зафиксировать 
  новые паттерны и начать постепенно ускорять AvgT, сжимая Δ к ±30.

ИГРОК:
  • Играет ТОЛЬКО на телефоне (Android).
  • ОСНОВНОЙ КОНТРОЛЬ: 1+0 (bullet). База времени = 60 сек.
  • Стиль: быстрый интуит, сильный дебют, слабый миттельшпиль.
  • Главная слабость: каскадный тильт (73.0%), аллергия на агрессию (21%), 
    лаги (34.6% партий).

================================================================
 ОБЛАЧНАЯ ИНФРАСТРУКТУРА (v26.0)
================================================================
  Проект полностью автоматизирован в облаке:
  1. GitHub Repository: Ayrat1986/Analyze (Хранение кода и базы).
  2. GitHub Actions: Файл .github/workflows/update.yml. 
     Теперь запускает ПОЛНЫЙ цикл (python run.py) на серверах Ubuntu.
     Каждые 3 часа он скачивает партии, ставит Linux-версию Stockfish,
     считает ACPL, обновляет дашборды и пушит результат в репозиторий.
  3. Streamlit Cloud: Хостинг веб-дашборда. Доступен с телефона по 
     ссылке (не требует включенного ПК). Автоматически обновляется
     при появлении новых коммитов (нужен Reboot при необходимости).

================================================================
 АРХИТЕКТУРА (src/)
================================================================
  chess.com API -> data/chess_api_cache.json
       │
       ▼
  data/stockfish_cache.json (Stockfish, ACPL, зевки, PGN, clocks)
       │
       ▼
  data/chess.db (SQLite — единый источник для отчётов и дашборда)
       │
       ▼
  Streamlit Dashboard (Облако) / GitHub Actions (Автоматический расчет)

  ── ЯДРО (src/analysis/) ────────────────────────────────────
    game.py            — доменная модель партии (opp_style, time=30.0)
    engine_pool.py     — пул Stockfish (защита от BrokenPipe)
    cache.py           — кэширование промежуточных результатов
    constants.py       — константы (DEPTH, пороги зевков)
    helpers.py         — доменно-нейтральные утилиты
    common.py          — WAL-режим, WINDOWS, RATING_BUCKETS

  ── КЛЮЧЕВЫЕ МОДУЛИ ────────────────────────────────────────
    analysis/utils/build_cache.py    — Хэши для инкрементальной сборки
    analysis/dashboard_aggression.py — Агрессия (вынесено)
    analysis/dashboard_trends.py     — Тренды и графики (вынесено)
    analysis/coach/                  — Пакет тренера (4 модуля)
    analysis/psych_rating/           — Пакет рейтинга (6 модулей)
    analysis/openings/cheat_sheets.py — Шпаргалки D00, D02, D10
    analysis/opponents/trainer.py    — Тренажер анти-агрессора
    src/_common.py                   — Проверка STOCKFISH_PATH (env)
    .github/workflows/update.yml     — Облачный CI/CD (полный цикл)

  ── СБОРКА ДАШБОРДОВ ────────────────────────────────────────
    analysis/dashboard.py          — оркестратор
    analysis/dashboard_helpers.py  — фасад (SQL для 00_INDEX)
    analysis/dashboards/           — 9 сборщиков

  ── ДОМЕНЫ ──────────────────────────────────────────────────
    openings/       — anatomy, reports, planner, cheat_sheets
    middlegame/     — 6 модулей (advantage_speed, transition, ...)
    psych_focus/    — blunder_anatomy, first_blunder, missed, review
    psych_state/    — time_management, speed_rating, combined_rating
    opponents/      — weakness, trainer
    psych_rating/   — monitoring (снапшоты)

  ── ОРКЕСТРАЦИЯ ─────────────────────────────────────────────
    run.py               — конвейер (--fast, --force, кэш)
    13_dashboard_final.py — тонкий оркестратор

================================================================
 СХЕМА БАЗЫ ДАННЫХ
================================================================
  games (основная таблица):
    url, end_time, white, black, opening, eco, my_rating, opp_rating, 
    opp_username, won, draw, reason, is_lag, is_cheater, acpl, 
    acpl_opening, acpl_middlegame, acpl_endgame, accuracy, 
    critical_moments, max_eval_advantage, min_eval_advantage, 
    momentum_after_blunder, eval_after_opening, opening_line, pgn, 
    clocks, eval_history, time_control, flag_result, my_clock_at_timeout, 
    opp_clock_at_timeout, opp_style

  blunders (зевки):
    game_url, move_num, move_uci, loss_cp, pattern_tag, is_my_blunder, 
    time_spent, next_move_time, fen_before, best_move_uci, missed_threat

  monitoring_log (Снапшоты):
    date, games, avg_my_rating, avg_opp_rating, perf_rating, acpl, 
    game_r, speed_r, combined_r, delta, stddev_acpl, aggression, 
    hunter_pct, notes

  checkins (дневник):
    date, sleep_hours, mood, energy, stress, note

  trainer_progress (UI-состояние тренировок):
    task_hash, task_type, fen, status, attempts, last_seen, 
    next_review, created_at

================================================================
 КЛЮЧЕВЫЕ ЦИФРЫ (на 2026-11-20, окно 90 дней)
================================================================
  Партий в базе:            2453 (без лагов/читеров)
  Средний рейтинг (90д):    2541
  ACPL общий:               65 CP
  ACPL миттельшпиля:        74 CP (главная дыра)
  StdDev ACPL:              30.5 (цель 15)
  Winrate общий:            48.7%
  Скорость:                 1.18 сек/ход
  Каскады в миттельшпиле:   73.0%
  Лаги:                     34.6% партий (winrate −16%)
  
  МЕТРИКИ МОНИТОРИНГА:
  • CombR:    2548 (90д) / 2653 (пик)
  • Delta:    +10 (баланс 90д) / +182 (сейчас, Калибровка)
  • Агрессия: 6.8 - 7.9 (Охотник 38%)

================================================================
 ТОП-3 СЛАБОСТИ (по данным)
================================================================
  1. Каскадный тильт в миттельшпиле (73.0%)
     → psych_state/psych_tilt.py → cascade_tilt
     → лечение: правило «3 секунды после зевка».

  2. Слив перевеса (+3.0) (36.2%)
     → middlegame/win_loss_conversion.py
     → лечение: при +3.0 — держи ритм (не замедляйся без причины).

  3. Цейтнот (просрочки) (25.3%)
     → psych_state/time_management.py
     → лечение: на 20-м ходу при <15 сек — форсируй размен.
     
  Бонус: «Час X» — первый зевок в среднем на 17-м ходу.
     → лечение: на ходах 10-15 — замедлись в 2 раза, проверь угрозы.

================================================================
 БЫСТРЫЙ СТАРТ
================================================================
  # Внимание: Основной расчет теперь идет в облаке!
  # Локально запускаем только для тестов или ручного разбора.

  # Стянуть свежие данные из облака (утром):
  # GitHub Desktop -> Pull origin

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

  # Запуск веб-дашборда (Streamlit)
  python -m streamlit run web_dashboard/app.py

================================================================
 КАРТА ПРОЕКТА (что где лежит)
================================================================

  ┌─ [DOC] Корневые документы (читать первыми) ────────────────┐
  ├── START_HERE.txt        ← ★ НАЧНИ ЗДЕСЬ (5 шагов) ★
  ├── README.txt            ← ВЫ ЗДЕСЬ
  ├── PROJECT_RULES.txt     ← Что НЕ предлагать
  ├── LIMITS.txt            ← Потолок аналитики, путь к 3000
  ├── CODEX.txt             ← Кодекс Пули (Интерфейс Мастера)
  ├── 00_INDEX.txt          ← DASHBOARD INDEX
  └────────────────────────────────────────────────────────────┘

  ┌─ [DATA] Данные (не трогать руками) ────────────────────────┐
  ├── data/
  │    ├── chess.db                ← SQLite (games, blunders, checkins)
  │    ├── chess_api_cache.json    ← Сырые ответы API
  │    ├── stockfish_cache.json    ← Результаты Stockfish
  │    ├── combined_rating_coefs.json ← Коэффициенты CombinedR
  │    ├── codex_rules.json        ← «Кодекс Пули» (JSON)
  │    ├── config.json             ← player, email, stockfish_path
  │    ├── build_cache/            ← Хэши шагов (для run.py)
  │    └── backup/                 ← Бэкапы (5 последних)
  └────────────────────────────────────────────────────────────┘

  ┌─ [CORE] Код анализа (src/) ────────────────────────────────┐
  ├── src/
  │    ├── _common.py
  │    ├── _chess_utils.py
  │    ├── run.py                  ← Оркестратор
  │    ├── update_light.py         ← (Legacy) облегченный апдейт
  │    ├── 00_data_quality.py
  │    ├── 01_fetch_chess_api.py
  │    ├── 02_analyze_stockfish.py
  │    ├── 02a_check_cheaters.py
  │    ├── 03_migrate_sqlite.py    ← WAL + индексы + ON CONFLICT
  │    ├── 04_export_csv.py
  │    ├── 05_openings.py
  │    ├── 06_middlegame.py
  │    ├── 07_endgame.py
  │    ├── 08_psych_focus.py
  │    ├── 09_psych_state.py
  │    ├── 10_psych_rating.py      ← Оркестратор + снапшот
  │    ├── 11_psych_opponents.py   ← Оркестратор
  │    ├── 12_coach.py             ← Оркестратор
  │    ├── 13_dashboard_final.py
  │    │
  │    ├── core/
  │    │    ├── метрики.py         ← game_rating, speed_rating, perf
  │    │    ├── стили.py           ← get_style
  │    │    ├── пороги.py          ← get_threshold
  │    │    └── time_control.py    ← 1+0 / 3+2
  │    │
  │    └── analysis/               ← Пакет анализа
  │         ├── common.py          ← WAL, WINDOWS, RATING_BUCKETS
  │         ├── game.py            ← opp_style, time=30.0
  │         ├── engine_pool.py
  │         ├── cache.py
  │         ├── constants.py
  │         ├── helpers.py
  │         ├── dashboard.py
  │         ├── dashboard_helpers.py ← фасад
  │         ├── dashboard_aggression.py
  │         ├── dashboard_trends.py
  │         ├── dashboards/        ← 9 сборщиков
  │         ├── openings/          ← +cheat_sheets
  │         ├── middlegame/
  │         ├── psych_focus/
  │         ├── psych_state/
  │         ├── psych_rating/      ← 6 модулей
  │         ├── coach/             ← 4 модуля
  │         ├── trainer/           ← smart_deck
  │         ├── utils/             ← build_cache
  │         └── opponents/         ← +trainer
  └────────────────────────────────────────────────────────────┘

  ┌─ [REPORT] Отчёты (reports/) ───────────────────────────────┐
  ├── reports/
  │    ├── dashboards/             ← 01..08 (сводки за 5 строк)
  │    ├── reviews/                ← Разборы партий
  │    ├── training/               ← Колода, эндшпиль
  │    └── (txt-отчёты по доменам)
  └────────────────────────────────────────────────────────────┘

  ┌─ [WEB] Веб-интерфейс (web_dashboard/) ─────────────────────┐
  ├── web_dashboard/
  │    ├── app.py                  ← Главная (Overview)
  │    ├── pages/                  ← Страницы Streamlit
  │    │    ├── 1_Overview.py      ← Общий обзор метрик
  │    │    ├── 2_Openings.py      ← Дебюты
  │    │    ├── 3_ACPL.py          ← Точность по фазам
  │    │    ├── 4_Endurance.py     ← Выносливость и тильт
  │    │    ├── 5_Blunders.py      ← Зевки и колода (st.radio)
  │    │    ├── 6_Analysis.py      ← Анализ FEN/PGN
  │    │    ├── 7_Blitz.py         ← Игра против Stockfish
  │    │    ├── 8_Session_Tracker.py ← Микро-сессии
  │    │    ├── 9_Coach.py         ← План тренера
  │    │    ├── 10_Opponents.py    ← Психология соперников
  │    │    ├── 11_Trainer.py      ← Тренажер (тап + drag)
  │    │    ├── 12_Metrics_Trend.py ← Тренды GameR/SpeedR
  │    │    ├── 13_Blunder_Map.py  ← Карта зевков
  │    │    ├── 14_Daily_Rhythm.py ← Суточный ритм и каскады
  │    │    ├── 15_Review.py       ← Разбор партии
  │    │    └── 16_Monitoring.py   ← Графики динамики (снапшоты)
  │    └── utils/
  │         ├── db.py              ← Подключение к SQLite
  │         ├── chess_vis.py       ← Отрисовка SVG-доски
  │         ├── engine.py          ← Пул Stockfish (для веба)
  │         └── trainer_db.py      ← Сохранение прогресса
  └────────────────────────────────────────────────────────────┘

================================================================
 ШКАЛА РЕЙТИНГА CHESS.COM И КВАЛИФИКАЦИЙ (v26.0)
================================================================
  ⚠️ ВАЖНО: GameR — это только потенциал точности.
  Реальный рейтинг Chess.com ≈ Perf (Результат).
  Именно рейтинг Chess.com определяет квалификацию.

  2400–2600   КМС                    ← средний рейтинг (2541)
  2600–2800   МФ (мастер ФИДЕ)
  2800–3000   ММ (международный)     ← цель (3000)
  3000–3200   МГ (гроссмейстер)
  3400–3500   Накамура / Карлсен

  Твой средний рейтинг = 2541 (КМС).
  Твой P10 GameR = 2891 — это потенциал, но он не равен рейтингу.
  Разрыв = цейтнот, тильт, агрессия.

  Цель 3000 = поднять реальный рейтинг, а не GameR.
  Путь: держать Δ в ±30, убрать лаги, каскады, цейтнот.
================================================================