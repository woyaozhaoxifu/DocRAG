import os
import sys
import threading
import traceback

# 强制 stdout/stderr 使用 UTF-8，避免 Windows 控制台(cmd)中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config, APP_DIR
from core.store import Store, initial_scan
from core.watcher import start_watcher
from core.api import Api

CRASH_LOG = os.path.join(APP_DIR, "data", "crash.log")


def _log_crash(typ, value, tb):
    try:
        os.makedirs(os.path.dirname(CRASH_LOG), exist_ok=True)
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write("\n==== crash %s ====\n" % __import__("time").strftime("%Y-%m-%d %H:%M:%S"))
            traceback.print_exception(typ, value, tb, file=f)
    except Exception:
        pass


sys.excepthook = _log_crash


class Manager:
    def __init__(self):
        self.cfg = load_config()
        os.makedirs(self.cfg["data_dir"], exist_ok=True)
        os.makedirs(self.cfg["archive_root"], exist_ok=True)
        self.store = Store(self.cfg)
        self.api = Api(self)
        self.observer = None

    def background_init(self):
        """后台线程：先加载语义模型（懒加载，不阻塞窗口），再做首次扫描。"""
        try:
            # 模型加载（若已下载缓存则很快；否则会回退到关键词检索，绝不报错）
            print("[DocRAG] 正在加载语义模型，请稍候（本地缓存约 5-10 秒）...", flush=True)
            self.store.embedder.load()
            if self.store.embedder.available:
                print("[DocRAG] 语义模型加载完成，混合检索已启用。", flush=True)
            else:
                print("[DocRAG] 语义模型未加载，已回退到关键词检索。", flush=True)
        except Exception:
            _log_crash(*sys.exc_info())
        try:
            initial_scan(self.store, self.cfg)
        except Exception:
            _log_crash(*sys.exc_info())
        # 模型/扫描结束后，刷新一下前端状态（语义开关）
        try:
            import webview

            if webview.windows:
                webview.windows[0].evaluate_js("if(typeof refresh==='function'){refresh();}")
        except Exception:
            pass

    def maybe_archive(self, path):
        """根据配置，对"启动后新出现"的文件执行自动归档。"""
        for name, d in self.cfg["monitored_dirs"].items():
            d_norm = os.path.normpath(d).lower()
            p_norm = os.path.normpath(path).lower()
            if p_norm.startswith(d_norm) and self.cfg["auto_archive"].get(name):
                try:
                    self.store.archive_file(path)
                except Exception:
                    pass
                return

    def start_watcher(self):
        self.observer = start_watcher(self.store, self.cfg, self.maybe_archive)


def main():
    mgr = Manager()
    # 模型加载 + 首次扫描放到后台，窗口先弹出来（避免黑屏/闪退的观感）
    threading.Thread(target=mgr.background_init, daemon=True).start()
    mgr.start_watcher()
    # 可选：若开启智能归档，启动后自动整理一次
    if mgr.cfg.get("smart_archive", {}).get("enabled"):
        threading.Thread(target=mgr.api.smart_archive, daemon=True).start()

    import webview

    webview.create_window(
        "本地文档智能检索",
        os.path.join(APP_DIR, "ui", "index.html"),
        js_api=mgr.api,
        width=1120,
        height=780,
    )
    try:
        webview.start()
    except Exception:
        _log_crash(*sys.exc_info())
        raise


if __name__ == "__main__":
    main()
