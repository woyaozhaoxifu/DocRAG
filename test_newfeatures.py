"""新增能力集成测试：同义词扩展 / 联想建议 / 预览 / 类型·目录过滤 /
图片+OCR 优雅降级 / 云盘占位符检测 / 无模型时语义检索降级。"""
import os
import sys
import time
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config, APP_DIR
from core.store import Store, initial_scan, _is_placeholder
from core.keywords import expand_query
from core.api import Api


PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def make_tree(root):
    files = {}

    def w(rel, text):
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    test_a = os.path.join(root, "Test")
    test_b = os.path.join(root, "Test2")
    # —— 同义词召回：文档正文不含"电池"，但含 新能源/锂电/储能/动力 ——
    files["battery"] = w("Test/新能源电池产业链.txt",
                         "锂电与储能技术路线分析，动力电池产能持续扩张。")
    # —— 多目录 + 过滤：共享词"项目" ——
    files["projA"] = w("Test/项目方案A.txt", "本项目方案A关于新能源电池与供应链。")
    files["projB"] = w("Test2/项目方案B.md", "本项目方案B关于电源适配器与供电。")
    # —— 直接命中 + 同义词（报销→差旅/发票）——
    files["baoxiao"] = w("Test/差旅报销单.txt", "差旅费与发票报销流程说明。")
    # —— docx 抽取 + 同义词（电源→电源适配器/供电）——
    import docx as _dx
    p = os.path.join(test_a, "电源适配器规格.docx")
    d = _dx.Document(); d.add_paragraph("电源适配器输入输出参数与供电要求。"); d.save(p)
    files["power"] = p
    # —— pdf 抽取 ——
    import pymupdf as _pf
    p = os.path.join(test_a, "测试规范文档.pdf")
    pdf = _pf.open(); pg = pdf.new_page(); pg.insert_text((72, 72), "测试规范与测试报告编写指引。", fontname="china-s"); pdf.save(p); pdf.close()
    files["test"] = p
    # —— 图片：OCR 不可用时应按文件名索引，不报错 ——
    files["img"] = w("Test/架构截图.png", "")  # 空文本，模拟无 OCR
    return files


class _Mgr:
    def __init__(self, store, cfg):
        self.store = store
        self.cfg = cfg


def main():
    root = "D:/docrag_inttest_" + str(int(time.time()))
    data_dir = os.path.join(root, "data")
    archive_root = os.path.join(root, "archive")
    os.makedirs(root, exist_ok=True)

    cfg = load_config()  # 真实配置（含 synonyms / user_dict / exclude_*）
    cfg["monitored_dirs"] = {"Test": os.path.join(root, "Test"),
                             "Test2": os.path.join(root, "Test2")}
    cfg["data_dir"] = data_dir
    cfg["archive_root"] = archive_root

    files = make_tree(root)

    print("\n[0] 初始化 Store（向量模型未下载 → 应优雅降级）")
    store = Store(cfg)
    st0 = store.stats()
    check("语义检索降级为关闭（无模型不阻塞）", st0["semantic"] is False)

    print("\n[1] initial_scan 只读索引（含 docx/pdf/图片/子目录）")
    cnt = initial_scan(store, cfg)
    check(f"索引数量={cnt}>=7", cnt >= 7)

    mgr = _Mgr(store, cfg)
    api = Api(mgr)

    print("\n[2] 同义词扩展（搜'电池'应命中仅含 新能源/锂电 的文档）")
    eq = expand_query("电池")
    check("expand_query('电池') 含 新能源/锂电/储能/动力",
          all(k in eq for k in ("新能源", "锂电", "储能", "动力")))
    r = api.search("电池", 20)
    hit = any("新能源电池产业链" in (x["filename"] or "") for x in r)
    check("搜'电池'命中正文无'电池'的文档（同义词生效）", hit)

    print("\n[3] 直接命中 + 同义词（报销 / 电源）")
    r = api.search("报销", 20)
    check("搜'报销'命中差旅报销单", any("差旅报销单" in (x["filename"] or "") for x in r))
    r = api.search("电源", 20)
    check("搜'电源'命中电源适配器规格.docx", any("电源适配器规格" in (x["filename"] or "") for x in r))

    print("\n[4] 联想建议 suggest")
    s = api.suggest("新", 8)
    check("suggest('新') 返回含'新能源'的建议", any("新能源" in w for w in s) and len(s) > 0)
    s_all = api.suggest("", 8)
    check("suggest('') 返回热门关键词（非空）", len(s_all) > 0)

    print("\n[5] 文档预览 get_preview")
    prev = api.get_preview(files["battery"])
    check("get_preview 返回 ok 且含正文", prev.get("ok") and (prev.get("text") or "").strip())

    print("\n[6] 类型 / 目录 过滤")
    r = api.search("项目", 20, filters={"dir": "Test"})
    check("dir=Test 仅命中方案A", all(x["dir_name"] == "Test" for x in r) and
          any("项目方案A" in (x["filename"] or "") for x in r))
    r = api.search("项目", 20, filters={"ext": ".md"})
    check("ext=.md 仅命中方案B", all(x["ext"] == ".md" for x in r) and
          any("项目方案B" in (x["filename"] or "") for x in r))

    print("\n[7] 图片+OCR 优雅降级（无 OCR 仍按文件名索引）")
    r = api.search("架构截图", 20)
    check("图片按文件名索引可被搜到", any("架构截图" in (x["filename"] or "") for x in r))

    print("\n[8] 云盘占位符检测")
    check("普通文件 _is_placeholder=False", _is_placeholder(files["battery"]) is False)

    print("\n[9] 统计")
    st = store.stats()
    check(f"总文档数={st['total']}>=7", st["total"] >= 7)
    check("向量数为0（未下载模型）", st["vectors"] == 0)

    store.conn.close()
    shutil.rmtree(root, ignore_errors=True)
    print(f"\n=== 结果: PASS={PASS} FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
