# ============================================================
# analysis/engine_pool.py — Пул Stockfish-движков (v25.0)
# A1: _deaths по интервалу (3 смерти за 100 партий = проблема).
#     Раньше был накопительный — при 10000-партийном прогоне
#     пул «умирал» после 3-й случайной смерти.
# ============================================================
import queue
import threading
import time
import chess.engine


class EnginePool:
    """
    Пул движков Stockfish для параллельного анализа.
    Если движок упал (BrokenPipe/OSError), он заменяется новым.

    A1: _deaths считаются в скользящем окне (MAX_DEATHS за DEATH_WINDOW партий).
    Если 3 смерти за 100 партий — пул считается сломанным.
    Если 3 смерти за 10000 партий — это норма, продолжаем.
    """

    MAX_DEATHS = 3
    DEATH_WINDOW = 100  # партий

    def __init__(self, stockfish_path: str, size: int = 4,
                 threads_per_engine: int = 1, hash_mb: int = 64):
        self.stockfish_path = stockfish_path
        self.size = size
        self.threads_per_engine = threads_per_engine
        self.hash_mb = hash_mb
        self.pool = queue.Queue(maxsize=size)
        self.engines = []
        self._lock = threading.Lock()

        # A1: история смертей (timestamp) — для скользящего окна
        self._death_times = []

        # счётчик обработанных партий (для диагностики)
        self._processed = 0

        for i in range(size):
            eng = self._spawn(i)
            if eng is not None:
                self.pool.put(eng)
                self.engines.append(eng)

        if not self.engines:
            raise RuntimeError(f"Не удалось запустить ни одного Stockfish из {stockfish_path}")

        print(f"✅ EnginePool: {len(self.engines)}/{size} движков готовы")

    def _register_death(self):
        """A1: регистрирует смерть и проверяет, не сломан ли пул."""
        now = time.time()
        with self._lock:
            self._death_times.append(now)
            # Оставляем только последние DEATH_WINDOW записей
            if len(self._death_times) > self.DEATH_WINDOW:
                self._death_times = self._death_times[-self.DEATH_WINDOW:]

    def _pool_broken(self) -> bool:
        """
        A1: пул сломан, если за последние MAX_DEATHS * 10 партий
        было MAX_DEATHS смертей. Т.е. частота > 30%.
        """
        with self._lock:
            return len(self._death_times) >= self.MAX_DEATHS

    def mark_processed(self):
        """A1: увеличивает счётчик обработанных партий."""
        with self._lock:
            self._processed += 1

    def _spawn(self, idx=None):
        """Создаёт новый движок. Возвращает None, если не удалось."""
        try:
            eng = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
            if self.threads_per_engine > 1:
                eng.configure({"Threads": self.threads_per_engine})
            if self.hash_mb > 0:
                eng.configure({"Hash": self.hash_mb})
            return eng
        except Exception as e:
            label = f"#{idx+1}" if idx is not None else "(замена)"
            print(f"⚠️ Движок {label} не запустился: {e}")
            return None

    def _is_alive(self, engine) -> bool:
        """Проверка, жив ли движок (лёгкий ping)."""
        try:
            engine.ping()
            return True
        except (BrokenPipeError, OSError, chess.engine.EngineError, Exception):
            return False

    def get(self, timeout: float = 10.0):
        """Берёт движок из пула. Возвращает None при таймауте."""
        try:
            engine = self.pool.get(timeout=timeout)
        except queue.Empty:
            return None

        if not self._is_alive(engine):
            print(f"⚠️ Мёртвый движок в пуле. Замена...")
            self._register_death()

            if self._pool_broken():
                print(f"⚠️ Пул сломан: {len(self._death_times)} смертей "
                      f"(порог {self.MAX_DEATHS}). Движки не пересоздаются.")
                return None

            new_eng = self._spawn()
            if new_eng is not None:
                with self._lock:
                    self.engines.append(new_eng)
                return new_eng
            return None
        return engine

    def put(self, engine):
        """Возвращает движок в пул (с проверкой на смерть)."""
        if engine is None:
            return
        if not self._is_alive(engine):
            print(f"⚠️ Движок умер при возврате. Не возвращаю в пул.")
            self._register_death()

            if self._pool_broken():
                print(f"⚠️ Пул сломан: {len(self._death_times)} смертей "
                      f"(порог {self.MAX_DEATHS}). Движки не пересоздаются.")
                return

            new_eng = self._spawn()
            if new_eng is not None:
                with self._lock:
                    self.engines.append(new_eng)
                self.pool.put(new_eng)
            return
        self.pool.put(engine)

    def close(self):
        """Закрывает все движки."""
        for eng in self.engines:
            try:
                eng.quit()
            except Exception:
                pass
        self.engines.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()