import os
import json

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\DocRAG

DEFAULT_CONFIG = {
    "monitored_dirs": {
        "Downloads": "D:/Downloads",
        "Documents": "C:/Users/llia/Documents",
        "Desktop": "D:/Desktop",
        "OneDrive": "C:/Users/llia/OneDrive",
        "WPSCloud": "C:/Users/llia/WPS Cloud Files",
        "BaiduPan": "C:/Users/llia/百度网盘",
        "BaiduDownload": "D:/BaiduNetdiskDownload",
    },
    # 自动归档：仅对开启的目录，且只针对"监听启动后新出现"的文件
    "auto_archive": {
        "Downloads": False, "Documents": False, "Desktop": False,
        "OneDrive": False, "WPSCloud": False, "BaiduPan": False, "BaiduDownload": False,
    },
    "archive_root": "D:/DocRAG/archive",
    "data_dir": "D:/DocRAG/data",
    # 文档类（文本抽取索引）
    "extensions": [
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".txt", ".md", ".csv", ".json", ".html", ".htm", ".rtf",
    ],
    # 图片类（仅当 OCR 引擎可用时才抽取文字，否则只按文件名索引）
    "image_exts": [".png", ".jpg", ".jpeg", ".bmp", ".gif"],
    "max_text_chars": 200000,
    "settle_seconds": 3,
    # ---- 忽略规则（避免把软件配置/云盘缓存当文档索引） ----
    "exclude_dirs": [
        "WeChat Files", "Tencent Files", "QQ", "node_modules",
        ".431317168", ".cache", "__pycache__", ".git",
        "Codex", "LCEDA", "Rockstar",
        "英雄联盟", "wps", "BaiduNetdisk", "百度网盘", "WPS Cloud Files",
    ],
    "exclude_path_contains": [
        "Tencent Files", "WeChat Files", "Codex", "LCEDA", "Rockstar",
        "英雄联盟", "BaiduNetdisk", "百度网盘", "WPS Cloud Files",
        ".431317168",
    ],
    "exclude_exts": [".tmp", ".crdownload", ".lnk", ".part", ".download", ".msi", ".mts"],
    # ---- 中文分词增强 ----
    "user_dict": "user_dict.txt",  # 专有名词词典（青隼电源、十五五…）
    "synonyms": {                    # 同义词扩展：搜 A 也能命中 B
        "电池": ["新能源", "动力", "储能", "锂电"],
        "报销": ["差旅", "差旅费", "费用", "发票"],
        "电源": ["电源适配器", "供电", "充电", "电源兼容"],
        "实习": ["实习报告", "实习日志", "见习"],
        "测试": ["测试报告", "测试规范", "验证"],
    },
    # ---- 语义检索（向量） ----
    "vector": {
        "enabled": True,
        "model": "BAAI/bge-small-zh-v1.5",
        "top_k": 25,
        "weight": 0.4,  # 向量分在混合排序中的权重
    },
    # ---- OCR（图片/扫描版 PDF） ----
    "ocr": {"enabled": True},
    # ---- 智能归档 ----
    "smart_archive": {"enabled": False, "days_unused": 30, "dirs": ["Downloads"]},
}

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# 递归扫描时跳过的目录
SKIP_DIRS = set(DEFAULT_CONFIG["exclude_dirs"]) | {
    "node_modules", ".git", "AppData", "Library", ".cache", "venv",
    "__pycache__", ".workbuddy", "Microsoft", "Windows",
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            for k, v in cfg.items():
                if k in ("monitored_dirs", "auto_archive"):
                    merged[k].update(v)
                else:
                    merged[k] = v
            # 保证新字段存在
            for k, v in DEFAULT_CONFIG.items():
                merged.setdefault(k, v)
            return merged
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
