# 本地文档智能检索系统（Local RAG）

纯本地、不上传任何文档的桌面文档检索工具。自动索引你电脑里的文档，输入关键词/文件名即可搜到并一键打开，支持中文分词、关键词检索、语义检索（可选）、图片 OCR（可选）、按类型/目录筛选、自动补全、正文预览、安全归档与还原。

> 全程本地运行，文档不出电脑。本仓库**仅包含搜索引擎代码**，不含任何个人文档、模型权重、本机路径或专有名词配置。

## 功能

- **多格式索引**：PDF / Word / Excel / PPT / TXT / MD / CSV / JSON / HTML / RTF，以及图片（开启 OCR 后可提取文字）
- **中文智能搜索**：jieba 分词 + 同义词扩展（如搜「电池」也能命中「新能源」「储能」）
- **语义检索（可选）**：安装模型后升级为「关键词 + 向量语义」混合检索（搜「报销」可命中「差旅费」）
- **一键打开**：点「打开」用系统默认程序打开原文件
- **关键词抽取**：每篇文档自动用 jieba(TF-IDF) 抽取关键词
- **自动补全 / 热词**：输入时下拉提示已索引关键词
- **筛选**：按类型（PDF/Word/Excel/PPT/文本/图片）或目录过滤
- **正文预览**：点卡片标题弹窗查看文档正文（前 8000 字）
- **安全归档与还原**：手动或按规则把文件移入 `archive/`，写可逆清单，一键还原；**绝不删除未校验文件**
- **自动监控**：监听目录新增文件，自动增量索引
- **云盘占位符识别**：OneDrive 等按需文件会被标记「需释放」，打开前拦截提示

## 安装与运行

```bash
# 1. 克隆仓库
git clone <你的仓库地址>
cd DocRAG

# 2. 创建并激活虚拟环境（推荐）
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 准备个人配置（仓库不含 config.json，需自行创建）
copy config.example.json config.json        # Windows
# cp config.example.json config.json        # macOS / Linux
# 然后编辑 config.json，把 monitored_dirs 改成你自己的目录

# 5. 启动
python app.py
# 或直接双击 start.bat（会优先使用 venv 内的 python）
```

> 首次启动会后台扫描 `monitored_dirs` 建立索引，窗口会立即弹出，索引在后台进行。

## 目录结构

```
DocRAG/
├── app.py                # 入口：pywebview 原生窗口 + 后台监听/索引服务
├── start.bat             # 启动脚本（优先用 venv，否则系统 python）
├── install_models.bat    # 一键安装语义检索模型（可选）
├── config.example.json   # 配置模板（config.json 不入库，请复制改名）
├── user_dict.example.txt # 专有名词词典模板（user_dict.txt 不入库）
├── requirements.txt      # 依赖清单
├── core\
│   ├── config.py         # 配置加载（默认相对路径，不依赖任何个人目录）
│   ├── parsers.py        # 文档文本抽取（含 OCR 钩子）
│   ├── keywords.py       # 关键词 + 同义词扩展
│   ├── store.py          # SQLite 普通表 + LIKE 子串检索（中文友好）+ 向量语义融合（可选）+ 归档/还原
│   ├── vector.py         # 语义向量 Embedder（优雅降级）
│   ├── ocr.py            # OCR 模块（优雅降级）
│   ├── watcher.py        # 文件监听
│   └── api.py            # 前端接口
├── ui\                   # 暗色主题搜索界面
├── data\                 # 索引库（docs.db），运行时生成，不入库
└── archive\              # 归档存放目录，运行时生成，不入库
```

## 配置（config.json）

`config.json` 与 `user_dict.txt` **不会上传到仓库**（见 `.gitignore`），请从 `config.example.json` / `user_dict.example.txt` 复制后自行填写。

| 字段 | 说明 |
|---|---|
| `monitored_dirs` | 监控目录（下载/文档/桌面/云盘…）。改成你自己的真实路径 |
| `auto_archive` | 各目录是否自动归档新文件。**默认全 false（只索引不移动）** |
| `exclude_dirs` / `exclude_path_contains` / `exclude_exts` | 忽略规则，避免把微信/游戏/云盘缓存当文档索引 |
| `user_dict` | 专有名词词典路径，提升分词准确率 |
| `synonyms` | 同义词表，扩展召回 |
| `vector.enabled` | 语义检索开关（需先运行 install_models.bat 下载模型）|
| `ocr.enabled` | 图片/扫描PDF 文字识别开关（需装 PaddleOCR）|
| `smart_archive` | 智能归档：`enabled:true` 后，下载目录 N 天未动的文件自动归档 |

## 进阶开启

**语义检索**（推荐）：双击 `install_models.bat`，按提示装好后会自动下载中文 embedding 模型（约 130MB）。重启后界面顶部「语义」显示「开」，搜索升级为混合检索。

**图片 OCR**：编辑 `install_models.bat` 取消最后一行注释后运行（PaddleOCR 体积较大，按需开启）。

**智能归档**：把 config.json 里 `smart_archive.enabled` 改为 `true`，界面点「智能归档」按钮即整理下载目录中长时间未变动的文件。

## 隐私与安全

- 全部索引与检索在本地完成，文档不上传。
- 本仓库仅含源代码与通用配置模板，**不含任何个人文档内容、模型权重、本机绝对路径或专有名词**。
- 归档是「移动 + 写可逆清单」，永不删除未校验文件；点「还原」即可放回原路径。
- 自动归档默认关闭；如需开启请改 `auto_archive` 对应目录为 `true`。

## 已知限制

- 未安装模型时无语义检索（仅关键词）；未装 OCR 时图片不提取文字。
- OneDrive 等云盘的「按需文件」本地只是占位符，需先在客户端「释放/始终保留在此设备」才能打开。
- 旧版 `.doc`（非 docx）无文本层时抽取为空，建议转 docx。
