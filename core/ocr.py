"""
OCR 模块（优雅降级）：为图片 / 扫描版 PDF 抽取文字。

- 若本机已安装 PaddleOCR，则对图片抽取文字；
- 否则 extract() 返回 None，调用方忽略该文件（仅按文件名索引，不报错）。
"""
import os


def available():
    try:
        import paddleocr  # noqa: F401
        return True
    except Exception:
        return False


def extract_image(path):
    """对图片抽取文字，返回字符串；不可用或失败时返回 None。"""
    try:
        from paddleocr import PaddleOCR
    except Exception:
        return None
    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr.ocr(path, cls=True)
        if not result:
            return None
        lines = []
        for block in result:
            if not block:
                continue
            for box in block:
                if box and len(box) >= 2 and box[1]:
                    lines.append(box[1][0])
        return "\n".join(lines) if lines else None
    except Exception:
        return None


def extract_pdf(path):
    """对 PDF 先尝试文本层；若文本层为空（扫描版），用 OCR 抽图。"""
    try:
        import pymupdf
        doc = pymupdf.open(path)
        try:
            txt = "\n".join(p.get_text() for p in doc)
        finally:
            doc.close()
        if txt and txt.strip():
            return txt  # 有文本层，无需 OCR
    except Exception:
        return None
    # 文本层为空 → 退化为图片 OCR（逐页转图再识别），较重
    try:
        import pymupdf
        doc = pymupdf.open(path)
        try:
            lines = []
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                tmp = os.path.join(
                    os.environ.get("TEMP", "."), f"_ocr_{os.path.basename(path)}_{page.number}.png"
                )
                pix.save(tmp)
                t = extract_image(tmp)
                if t:
                    lines.append(t)
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            return "\n".join(lines) if lines else None
        finally:
            doc.close()
    except Exception:
        return None
