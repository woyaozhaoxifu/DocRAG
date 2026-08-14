import os
import time

from .store import _is_placeholder


class Api:
    """暴露给前端 JS 的接口（pywebview js_api）。"""

    def __init__(self, mgr):
        self.mgr = mgr

    # ---- 检索 ----
    def search(self, q, limit=30, filters=None):
        q = (q or "").strip()
        if not q:
            return []
        return self.mgr.store.search(q, int(limit or 30), filters=filters)

    def suggest(self, q, limit=8):
        return self.mgr.store.suggest(q, int(limit or 8))

    def get_preview(self, path):
        return self.mgr.store.get_preview(path)

    def get_stats(self):
        return self.mgr.store.stats()

    def list_recent(self, n=20, filters=None):
        return self.mgr.store.recent(int(n or 20), filters=filters)

    # ---- 文件操作 ----
    def open_file(self, path):
        if not path or not os.path.exists(path):
            return {"ok": False, "error": "文件不存在或已移动"}
        if _is_placeholder(path):
            return {
                "ok": False,
                "error": "该文件为云盘占位符，请先在网盘客户端将其「释放/始终保留在此设备」后再打开",
            }
        try:
            os.startfile(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def archive_file(self, path):
        return self.mgr.store.archive_file(path)

    def restore(self, archive_path):
        return self.mgr.store.restore(archive_path)

    def smart_archive(self):
        cfg = self.mgr.cfg
        sa = cfg.get("smart_archive", {})
        if not sa.get("enabled"):
            return {
                "ok": True,
                "archived": 0,
                "note": "智能归档未启用：在 config.json 将 smart_archive.enabled 改为 true 即可",
            }
        days = int(sa.get("days_unused", 30))
        dirs = sa.get("dirs", [])
        cutoff = time.time() - days * 86400
        done = 0
        store = self.mgr.store
        for name in dirs:
            d = cfg["monitored_dirs"].get(name)
            if not d:
                continue
            with store.lock:
                rows = store.conn.execute(
                    "SELECT path FROM docs WHERE dir_name=? AND mtime<? AND archived=0",
                    (name, cutoff),
                ).fetchall()
            for (p,) in rows:
                if os.path.exists(p):
                    r = store.archive_file(p)
                    if r.get("ok"):
                        done += 1
        return {"ok": True, "archived": done}

    def reindex(self):
        self.mgr.initial_scan()
        return self.mgr.store.stats()

    def get_config(self):
        return self.mgr.cfg
