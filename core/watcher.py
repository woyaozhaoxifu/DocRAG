import os
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class _Handler(FileSystemEventHandler):
    def __init__(self, store, cfg, archive_cb):
        self.store = store
        self.cfg = cfg
        self.archive_cb = archive_cb
        self.timers = {}
        self.lock = threading.Lock()

    def _schedule(self, path):
        if os.path.isdir(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.cfg["extensions"]:
            return
        with self.lock:
            old = self.timers.get(path)
            if old:
                old.cancel()
            t = threading.Timer(self.cfg["settle_seconds"], self._process, (path,))
            self.timers[path] = t
            t.start()

    def _process(self, path):
        if not os.path.exists(path) or os.path.isdir(path):
            return
        try:
            self.store.index_file(path)
        except Exception:
            pass
        # 仅对"启动后新出现"的文件，按配置决定是否自动归档
        try:
            self.archive_cb(path)
        except Exception:
            pass

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule(event.dest_path)


def start_watcher(store, cfg, archive_cb):
    """监听所有被监控目录，返回 Observer（已启动）。"""
    observer = Observer()
    handler = _Handler(store, cfg, archive_cb)
    for name, d in cfg["monitored_dirs"].items():
        if os.path.isdir(d):
            observer.schedule(handler, d, recursive=True)
    observer.daemon = True
    observer.start()
    return observer
