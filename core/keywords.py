import os

import jieba
import jieba.analyse

jieba.setLogLevel(60)  # 关闭 jieba 的日志噪音

_USER_DICT_LOADED = False
_SYNONYMS = {}


def load_user_dict(path):
    """加载用户专有名词词典（青隼电源、十五五…），只加载一次。"""
    global _USER_DICT_LOADED
    if _USER_DICT_LOADED:
        return
    try:
        if path and os.path.exists(path):
            jieba.load_userdict(path)
    except Exception:
        pass
    _USER_DICT_LOADED = True


def set_synonyms(syn_map):
    global _SYNONYMS
    _SYNONYMS = syn_map or {}


def extract_keywords(text, topK=12):
    """基于 TF-IDF 抽取中文关键词。"""
    if not text:
        return []
    try:
        return jieba.analyse.extract_tags(text, topK=topK, withWeight=False)
    except Exception:
        return []


def expand_query(q, syn_map=None):
    """把查询词按同义词表扩展，返回扩展后的词列表（用于召回更多相关文档）。"""
    syn_map = syn_map or _SYNONYMS
    if not q:
        return []
    words = [w for w in jieba.cut(q) if w.strip()]
    out = list(words)
    if syn_map:
        for w in words:
            for key, vals in syn_map.items():
                if not vals:
                    continue
                if w == key or w in vals:
                    for v in vals:
                        if v not in out:
                            out.append(v)
    return out


def tokenize(text):
    return [w for w in jieba.cut(text) if w.strip()]
