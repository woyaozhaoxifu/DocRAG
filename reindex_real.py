"""对真实监控目录执行一次性全量索引，并产出扫描报告 last_scan_report.json。"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config, APP_DIR
from core.store import Store, initial_scan


def main():
    cfg = load_config()
    t0 = time.time()
    store = Store(cfg)

    scanned = [d for d in cfg["monitored_dirs"].values() if os.path.isdir(d)]
    print(f"待扫描目录({len(scanned)}个):")
    for d in scanned:
        print("  -", d)

    count = initial_scan(store, cfg, incremental=True)

    # 各目录文档数
    per_dir = {}
    with store.lock:
        for name in cfg["monitored_dirs"]:
            n = store.conn.execute(
                "SELECT COUNT(*) FROM docs WHERE dir_name=?", (name,)).fetchone()[0]
            per_dir[name] = n

    st = store.stats()
    report = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(time.time() - t0, 1),
        "total": st["total"],
        "vectors": st["vectors"],
        "semantic": st["semantic"],
        "last_index": st["last_index"],
        "per_dir": per_dir,
        "monitored_dirs": cfg["monitored_dirs"],
    }
    out = os.path.join(cfg["data_dir"], "last_scan_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    store.conn.close()
    print("\n=== 扫描完成 ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
