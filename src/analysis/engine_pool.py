# ============================================================
# analysis/engine_pool.py — Пул Stockfish-движков (v19.5)
# Защита от BrokenPipeError / OSError.
# ============================================================
import queue
import threading
import chess.engine


class EnginePool:
    """
    Пул движков Stockfish для параллельного анализа.
    Если движок упал (BrokenPipe/OSError), он заменяется новым (до MAX_DEATHS раз).
    """

    MAX_DEATHS = 3

    def __init__(self, stockfish_path: str, size: int = 4,
                 threads_per_engine: int = 1, hash_mb: int = 64):
        self.stockfish_path = stockfish_path
        self.size = size
        self.threads_per_engine = threads_per_engine
        self.hash_mb = hash_mb
        self.pool = queue.Queue(maxsize=size)
        self.engines = []
        self._lock = threading.Lock()
        self._deaths = 0

        for i in range(size):
            eng = self._spawn(i)
            if eng is not None:
                self.pool.put(eng)
                self.engines.append(eng)

        if not self.engines:
            raise RuntimeError(f"Не удалось запустить ни одного Stockfish из {stockfish_path}")

        print(f"✅ EnginePool: {len(self.engines)}/{size} движков готовы")

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
            self._deaths += 1
            if self._deaths < self.MAX_DEATHS:
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
            self._deaths += 1
            if self._deaths < self.MAX_DEATHS:
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