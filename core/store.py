import os
import re
import html
import time
import hashlib
import sqlite3
import threading

import jieba

from . import parsers
from .keywords import extract_keywords, expand_query, load_user_dict, set_synonyms
from . import config as cfg_mod
from .vector import Embedder

SCHEMA_VERSION = 3  # 普通表 schema（曾用 FTS5，v3 起改用普通表 + LIKE 检索）


# ---------- 中文分词处理 ----------
def _tokenize(text):
    if not text:
        return ""
    tokens = []
    for w in jieba.cut(text):
        w = w.strip()
        if w and not re.match(r'^[^\w\u4e00-\u9fff]+$', w):
            tokens.append(w)
    return " ".join(tokens)


def _snippet(text, query_tokens, radius=120):
    """从原文提取命中片段并高亮（<b> 标签，与 CSS 一致）。"""
    if not text:
        return ""
    words = [w for w in (query_tokens or "").split() if len(w) > 1]
    if not words:
        return html.escape(text[:240])
    low = text.lower()
    best_pos = -1
    for w in words:
        pos = low.find(w.lower())
        if pos != -1:
            best_pos = pos
            break
    if best_pos == -1:
        return html.escape(text[:240])
    start = max(0, best_pos - radius)
    end = min(len(text), best_pos + radius * 2)
    seg = text[start:end]
    seg = html.escape(seg)
    for w in sorted(set(words), key=len, reverse=True):
        if len(w) <= 1:
            continue
        pat = re.escape(html.escape(w))
        seg = re.sub(pat, lambda m: f"<b>{m.group(0)}</b>", seg, flags=re.IGNORECASE)
    return seg


def _hash_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _is_placeholder(path):
    """检测云盘按需文件占位符 / 符号链接（Windows reparse point）。"""
    try:
        if os.path.islink(path):
            return True
        if os.name == "nt":
            import ctypes
            attr = ctypes.windll.kernel32.GetFileAttributesW(path)
            if attr != -1 and (attr & 0x400):  # FILE_ATTRIBUTE_REPARSE_POINT
                return True
    except Exception:
        pass
    return False


def _score_record(content, filename, title, words):
    """相关度启发式：标题/文件名命中加分，内容命中位置越靠前加分越多。"""
    score = 0.0
    low_c = (content or "").lower()
    low_f = (filename or "").lower()
    low_t = (title or "").lower()
    for w in words:
        wl = w.lower()
        if wl in low_f:
            score += 5
        if wl in low_t:
            score += 3
        pos = low_c.find(wl)
        if pos != -1:
            score += max(0.0, 2.0 - pos / 2000.0)
    return score


class Store:
    def __init__(self, cfg, embedder=None):
        self.cfg = cfg
        self.data_dir = cfg["data_dir"]
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, "docs.db")
        self.lock = threading.RLock()

        load_user_dict(cfg.get("user_dict"))
        set_synonyms(cfg.get("synonyms", {}))

        self.embedder = embedder
        if self.embedder is None and cfg.get("vector", {}).get("enabled"):
            try:
                self.embedder = Embedder(cfg["vector"].get("model", "BAAI/bge-small-zh-v1.5"))
            except Exception:
                self.embedder = None

        self._open_db()

    def _open_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()
        cur = self.conn.execute("SELECT value FROM stats WHERE key='schema_version'").fetchone()
        ver = int(cur[0]) if cur else 0
        if ver < SCHEMA_VERSION:
            self.conn.execute("DROP TABLE IF EXISTS docs")
            self.conn.execute("DROP TABLE IF EXISTS vectors")
            self.conn.commit()
            self._create_schema()
        self._set_stat("schema_version", str(SCHEMA_VERSION))
        self.conn.commit()

    def _create_schema(self):
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS docs(
                path TEXT PRIMARY KEY,
                filename TEXT,
                title TEXT,
                content TEXT,
                keywords TEXT,
                raw_preview TEXT,
                full_text TEXT,
                ext TEXT,
                size INTEGER,
                mtime REAL,
                sha256 TEXT,
                dir_name TEXT,
                is_placeholder INTEGER,
                archived INTEGER,
                archived_path TEXT
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS vectors(
                path TEXT PRIMARY KEY, vec BLOB)"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS manifest(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_path TEXT,
                archive_path TEXT,
                sha256 TEXT,
                ts TEXT,
                restored INTEGER DEFAULT 0)"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS stats(
                key TEXT PRIMARY KEY, value TEXT)"""
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_ext ON docs(ext)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_dir ON docs(dir_name)")

    # ---- 索引决策 ----
    def _should_index(self, path, dir_name=None):
        fname = os.path.basename(path)
        if fname.startswith("~$") or fname.startswith("~"):
            return False
        ext = os.path.splitext(path)[1].lower()
        allowed = set(self.cfg["extensions"]) | set(self.cfg.get("image_exts", []))
        if ext not in allowed:
            return False
        if ext in set(self.cfg.get("exclude_exts", [])):
            return False
        low = path.lower().replace("/", "\\")
        for bad in self.cfg.get("exclude_path_contains", []):
            if bad.lower() in low:
                return False
        parts = set(os.path.normpath(path).split(os.sep))
        for bad in self.cfg.get("exclude_dirs", []):
            if bad in parts:
                return False
        return True

    def _dir_of(self, path):
        low = os.path.normpath(path).lower()
        for name, d in self.cfg["monitored_dirs"].items():
            if low.startswith(os.path.normpath(d).lower()):
                return name
        return "其他"

    # ---- 准备文档 ----
    def _prepare_doc(self, path, archived=False, archived_path=None, dir_name=None):
        if not os.path.exists(path) or os.path.isdir(path):
            return None
        if not self._should_index(path):
            return None
        try:
            text = parsers.extract_text(path, self.cfg["max_text_chars"])
        except Exception:
            text = ""
        raw_text = text or os.path.basename(path)
        keywords = extract_keywords(raw_text, topK=12)
        try:
            size = os.path.getsize(path)
            mtime = os.path.getmtime(path)
        except Exception:
            size, mtime = 0, 0
        sha = _hash_file(path)
        placeholder = 1 if _is_placeholder(path) else 0
        dn = dir_name or self._dir_of(path)
        return {
            "path": path,
            "filename": os.path.basename(path),
            "title": os.path.splitext(os.path.basename(path))[0],
            "content": raw_text,
            "keywords": " ".join(keywords),
            "raw_preview": raw_text[:600],
            "full_text": raw_text,
            "ext": os.path.splitext(path)[1].lower(),
            "size": size,
            "mtime": mtime,
            "sha256": sha,
            "dir_name": dn,
            "is_placeholder": placeholder,
            "archived": 1 if archived else 0,
            "archived_path": archived_path or "",
        }

    def index_file(self, path, archived=False, archived_path=None, dir_name=None):
        doc = self._prepare_doc(path, archived=archived, archived_path=archived_path, dir_name=dir_name)
        if not doc:
            return False
        with self.lock:
            self._upsert(doc)
            self._set_stat("last_index", str(int(time.time())))
            if self.embedder and self.embedder.available:
                try:
                    vec = self.embedder.encode([(doc["title"] + " " + doc["content"])[:512]])
                    if vec is not None:
                        self.conn.execute(
                            "INSERT OR REPLACE INTO vectors(path, vec) VALUES(?,?)",
                            (path, sqlite3.Binary(vec.tobytes())),
                        )
                        self.conn.commit()
                except Exception:
                    pass
        return True

    def _upsert(self, doc):
        self.conn.execute(
            """INSERT OR REPLACE INTO docs(
                path, filename, title, content, keywords, raw_preview, full_text,
                ext, size, mtime, sha256, dir_name, is_placeholder, archived, archived_path)
            VALUES(:path,:filename,:title,:content,:keywords,:raw_preview,:full_text,
                   :ext,:size,:mtime,:sha256,:dir_name,:is_placeholder,:archived,:archived_path)""",
            doc,
        )
        self.conn.commit()

    def remove_by_path(self, path):
        with self.lock:
            self.conn.execute("DELETE FROM docs WHERE path=?", (path,))
            self.conn.execute("DELETE FROM vectors WHERE path=?", (path,))
            self.conn.commit()

    # ---- 搜索（LIKE 子串 + 向量语义融合）----
    def _search_like(self, words, limit, filters=None):
        if not words:
            return {}
        conds = []
        params = []
        for w in words:
            conds.append("(filename LIKE ? OR content LIKE ? OR title LIKE ?)")
            params.extend([f"%{w}%", f"%{w}%", f"%{w}%"])
        sql = ("SELECT path, filename, title, content, keywords, raw_preview, "
               "ext, size, archived, archived_path, mtime, dir_name, is_placeholder, sha256 "
               "FROM docs WHERE " + " OR ".join(conds))
        if filters:
            if filters.get("ext"):
                sql += " AND ext = ?"
                params.append(filters["ext"])
            elif filters.get("exts"):
                ph = ",".join("?" * len(filters["exts"]))
                sql += f" AND ext IN ({ph})"
                params.extend(filters["exts"])
            if filters.get("dir"):
                sql += " AND dir_name = ?"
                params.append(filters["dir"])
        sql += f" LIMIT {int(limit)}"
        out = {}
        with self.lock:
            for row in self.conn.execute(sql, params):
                (path, filename, title, content, keywords, raw_preview, ext, size,
                 archived, archived_path, mtime, dir_name, is_placeholder, sha256) = row
                score = _score_record(content, filename, title, words)
                out[path] = {
                    "path": path, "filename": filename, "ext": ext, "size": size,
                    "keywords": (keywords or "").split(),
                    "archived": bool(archived), "archived_path": archived_path or "",
                    "mtime": mtime, "dir_name": dir_name,
                    "needs_download": bool(is_placeholder),
                    "sha256": sha256, "score": score, "raw_preview": raw_preview,
                }
        return out

    def _vector_search(self, query, limit):
        if not (self.embedder and self.embedder.available):
            return {}
        qvec = self.embedder.encode_query(query)
        if qvec is None:
            return {}
        with self.lock:
            rows = self.conn.execute("SELECT path, vec FROM vectors").fetchall()
        if not rows:
            return {}
        import numpy as np
        paths = [r[0] for r in rows]
        vecs = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        sims = vecs @ qvec
        order = np.argsort(-sims)[:limit]
        out = {}
        for i in order:
            out[paths[i]] = float(sims[i])
        return out

    @staticmethod
    def _rrf(kw_map, vec_map, limit, k=60):
        scores = {}
        for rank, p in enumerate(kw_map.keys()):
            scores[p] = scores.get(p, 0) + 1.0 / (k + rank + 1)
        for rank, p in enumerate(sorted(vec_map, key=lambda x: -vec_map[x])):
            scores[p] = scores.get(p, 0) + 1.0 / (k + rank + 1)
        ranked = sorted(scores, key=lambda x: -scores[x])[:limit]
        return ranked, scores

    def search(self, query, limit=30, filters=None):
        query = (query or "").strip()
        if not query:
            return []
        words = [w for w in expand_query(query) if w.strip()]
        if not words:
            return []
        kw_map = self._search_like(words, limit * 2, filters)
        vec_map = self._vector_search(query, limit * 2)
        if vec_map:
            ranked, scores = self._rrf(kw_map, vec_map, limit)
            result_paths = ranked
            score_lookup = scores
        else:
            result_paths = sorted(kw_map, key=lambda p: -kw_map[p]["score"])[:limit]
            score_lookup = {p: kw_map[p]["score"] for p in kw_map}
        results = []
        q_tokens = " ".join(words)
        for p in result_paths:
            base = kw_map.get(p) or {
                "path": p, "filename": os.path.basename(p), "ext": "",
                "size": 0, "keywords": [], "archived": False,
                "archived_path": "", "mtime": 0, "dir_name": "",
                "needs_download": False, "sha256": "", "score": 0,
                "raw_preview": "",
            }
            snippet = _snippet(base.get("raw_preview") or self._get_preview(p) or "", q_tokens)
            results.append({
                "path": p,
                "filename": base["filename"],
                "ext": base.get("ext", ""),
                "size": base.get("size", 0),
                "keywords": base.get("keywords", []),
                "archived": base.get("archived", False),
                "archived_path": base.get("archived_path", ""),
                "needs_download": base.get("needs_download", False),
                "dir_name": base.get("dir_name", ""),
                "score": round(float(score_lookup.get(p, base.get("score", 0))), 4),
                "snippet": snippet,
            })
        return results

    def _get_preview(self, path):
        with self.lock:
            row = self.conn.execute(
                "SELECT raw_preview FROM docs WHERE path=?", (path,)
            ).fetchone()
        return row[0] if row else ""

    def get_preview(self, path):
        with self.lock:
            row = self.conn.execute(
                "SELECT full_text, ext, size, mtime, dir_name, is_placeholder FROM docs WHERE path=?",
                (path,),
            ).fetchone()
        if not row:
            return {"ok": False, "error": "索引中无此文档"}
        full, ext, size, mtime, dir_name, ph = row
        return {
            "ok": True, "path": path, "text": (full or "")[:8000],
            "ext": ext, "size": size, "mtime": mtime, "dir_name": dir_name,
            "needs_download": bool(ph),
        }

    def recent(self, n=20):
        out = []
        with self.lock:
            cur = self.conn.execute(
                """SELECT path, ext, size, keywords, archived, archived_path, mtime, dir_name, is_placeholder
                   FROM docs ORDER BY mtime DESC LIMIT ?""", (n,)
            )
            for row in cur:
                path, ext, size, keywords, archived, archived_path, mtime, dir_name, ph = row
                out.append({
                    "path": path, "filename": os.path.basename(path), "ext": ext,
                    "size": size, "keywords": (keywords or "").split(),
                    "archived": bool(archived), "archived_path": archived_path or "",
                    "mtime": mtime, "dir_name": dir_name, "needs_download": bool(ph),
                })
        return out

    def suggest(self, q, limit=8):
        q = (q or "").strip()
        if not q:
            with self.lock:
                cur = self.conn.execute(
                    "SELECT keywords FROM docs WHERE keywords != '' LIMIT 200"
                )
                freq = {}
                for (kw,) in cur:
                    for w in (kw or "").split():
                        freq[w] = freq.get(w, 0) + 1
                return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:limit]]
        like = f"%{q}%"
        out = []
        with self.lock:
            cur = self.conn.execute(
                "SELECT DISTINCT keywords FROM docs WHERE keywords LIKE ? LIMIT 100", (like,)
            )
            for (kw,) in cur:
                for w in (kw or "").split():
                    if q in w and w not in out:
                        out.append(w)
            cur = self.conn.execute(
                "SELECT DISTINCT filename FROM docs WHERE filename LIKE ? LIMIT 50", (like,)
            )
            for (fn,) in cur:
                fn = fn.replace(".", " ")
                if q in fn and fn not in out:
                    out.append(fn)
        out = [w for w in out if w]
        out.sort(key=lambda w: (0 if w.startswith(q) else 1, len(w)))
        return out[:limit]

    def duplicates_of(self, sha256):
        if not sha256:
            return []
        with self.lock:
            return [r[0] for r in self.conn.execute(
                "SELECT path FROM docs WHERE sha256=? AND sha256 != ''", (sha256,))]

    def stats(self):
        with self.lock:
            total = self.conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
            archived = self.conn.execute("SELECT COUNT(*) FROM manifest WHERE restored=0").fetchone()[0]
            vec = self.conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
            cur = self.conn.execute("SELECT value FROM stats WHERE key='last_index'").fetchone()
        return {
            "total": total, "archived": archived, "vectors": vec,
            "semantic": bool(self.embedder and self.embedder.available),
            "last_index": int(cur[0]) if cur else 0,
        }

    def _set_stat(self, key, value):
        self.conn.execute(
            "INSERT OR REPLACE INTO stats(key,value) VALUES(?,?)", (key, value)
        )
        self.conn.commit()

    # ---- 安全归档 / 还原 ----
    def _safe_copy(self, src, dest):
        import shutil
        shutil.copy2(src, dest)
        if os.path.getsize(dest) != os.path.getsize(src):
            if os.path.exists(dest):
                os.remove(dest)
            raise IOError("拷贝校验失败，已中止")

    def _dedupe(self, path):
        if not os.path.exists(path):
            return path
        d, base = os.path.split(path)
        stem, suffix = os.path.splitext(base)
        n = 1
        cand = path
        while os.path.exists(cand):
            cand = os.path.join(d, f"{stem}_{n}{suffix}")
            n += 1
        return cand

    def archive_file(self, path):
        if not os.path.exists(path) or os.path.isdir(path):
            return {"ok": False, "error": "文件不存在"}
        if os.path.abspath(path).startswith(os.path.abspath(self.cfg["archive_root"])):
            return {"ok": False, "error": "已在归档库内，无需再归档"}
        ext = os.path.splitext(path)[1].lower().lstrip(".") or "other"
        rel = time.strftime("%Y/%m")
        dest_dir = os.path.join(self.cfg["archive_root"], rel, ext)
        os.makedirs(dest_dir, exist_ok=True)
        dest = self._dedupe(os.path.join(dest_dir, os.path.basename(path)))
        try:
            sha = _hash_file(path)
            self._safe_copy(path, dest)
            os.remove(path)
        except Exception as e:
            return {"ok": False, "error": f"归档失败: {e}"}
        with self.lock:
            self.conn.execute(
                "INSERT INTO manifest(original_path,archive_path,sha256,ts,restored) VALUES(?,?,?,?,0)",
                (path, dest, sha, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            self.conn.commit()
        self.remove_by_path(path)
        self.index_file(dest, archived=True, archived_path=path)
        return {"ok": True, "archive_path": dest, "original_path": path}

    def restore(self, archive_path):
        row = self.conn.execute(
            "SELECT original_path FROM manifest WHERE archive_path=? AND restored=0",
            (archive_path,),
        ).fetchone()
        original = row[0] if row else None
        if original:
            target = self._dedupe(original)
            target_dir = os.path.dirname(target)
        else:
            target_dir = os.path.join(self.cfg["archive_root"], "restored")
            target = self._dedupe(os.path.join(target_dir, os.path.basename(archive_path)))
        os.makedirs(target_dir, exist_ok=True)
        try:
            self._safe_copy(archive_path, target)
            os.remove(archive_path)
        except Exception as e:
            return {"ok": False, "error": f"还原失败: {e}"}
        with self.lock:
            self.conn.execute(
                "UPDATE manifest SET restored=1 WHERE archive_path=?", (archive_path,)
            )
            self.conn.commit()
        self.remove_by_path(archive_path)
        self.index_file(target, archived=False)
        return {"ok": True, "restored_path": target}


def initial_scan(store, cfg, progress_cb=None, incremental=True):
    """索引/增量更新（不移动任何文件）。incremental=True 时移除已删除文件。"""
    count = 0
    seen = set()
    batch = []
    sql = """INSERT OR REPLACE INTO docs(
                path, filename, title, content, keywords, raw_preview, full_text,
                ext, size, mtime, sha256, dir_name, is_placeholder, archived, archived_path)
             VALUES(:path,:filename,:title,:content,:keywords,:raw_preview,:full_text,
                    :ext,:size,:mtime,:sha256,:dir_name,:is_placeholder,:archived,:archived_path)"""
    with store.lock:
        for name, d in cfg["monitored_dirs"].items():
            if not os.path.isdir(d):
                continue
            for root, dirs, files in os.walk(d):
                dirs[:] = [
                    dd for dd in dirs
                    if dd not in cfg_mod.SKIP_DIRS
                    and dd not in set(cfg.get("exclude_dirs", []))
                    and not dd.startswith(".")
                ]
                for f in files:
                    p = os.path.join(root, f)
                    if not store._should_index(p):
                        continue
                    seen.add(p)
                    try:
                        doc = store._prepare_doc(p, dir_name=name)
                        if doc:
                            batch.append(doc)
                            count += 1
                            if len(batch) >= 50:
                                store.conn.executemany(sql, batch)
                                batch = []
                    except Exception:
                        pass
                    if progress_cb:
                        progress_cb(count)
        if batch:
            store.conn.executemany(sql, batch)
        if store.embedder and store.embedder.available:
            try:
                rows = store.conn.execute(
                    "SELECT path, title, content FROM docs WHERE path NOT IN (SELECT path FROM vectors)"
                ).fetchall()
                if rows:
                    texts = [(r[1] + " " + r[2])[:512] for r in rows]
                    vecs = store.embedder.encode(texts)
                    if vecs is not None:
                        store.conn.executemany(
                            "INSERT OR REPLACE INTO vectors(path, vec) VALUES(?,?)",
                            [(r[0], sqlite3.Binary(vecs[i].tobytes())) for i, r in enumerate(rows)],
                        )
            except Exception:
                pass
        if incremental:
            existing = [r[0] for r in store.conn.execute("SELECT path FROM docs")]
            for p in existing:
                if p not in seen and not os.path.exists(p):
                    store.remove_by_path(p)
        store.conn.commit()
        store._set_stat("last_index", str(int(time.time())))
    return count
