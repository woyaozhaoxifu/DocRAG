@echo off
REM 一键安装「语义向量检索」依赖（中文 embedding 模型）。
REM 安装后首次搜索会自动下载模型 BAAI/bge-small-zh-v1.5（约 130MB），
REM 之后顶部"语义"指示灯会变绿，搜索升级为「关键词 + 语义」混合检索。
REM
REM 注意：OCR（图片/扫描PDF文字识别）依赖 PaddleOCR，体积大（数百MB），
REM 默认不装。如需开启，去掉下面最后一行注释后保存再运行。

set PIP=pip

echo [1/2] 安装 sentence-transformers（语义检索核心）...
"%PIP%" install --no-cache-dir sentence-transformers

REM echo [2/2] 安装 PaddleOCR（图片/扫描版PDF识别，可选，体积大）...
REM "%PIP%" install --no-cache-dir paddleocr paddlepaddle

echo.
echo 安装完成。双击 start.bat 重启，顶部"语义"将显示「开」。
pause
