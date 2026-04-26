# 核心修改：改用python:3.13-slim（Debian精简版，glibc兼容，稳定支持所有依赖）
FROM python:3.13-slim

# 声明维护者（符合Docker最新规范，无警告）
LABEL maintainer="heiiyo <heiiyo@163.com>"

# 环境变量配置：避免Python缓冲、指定工作目录、统一UTF-8编码
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKDIR=/app/tender \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 创建并切换工作目录
WORKDIR $WORKDIR

# 安装系统依赖：OCR工具（Tesseract+简体中文包+poppler）+ 编译环境（支持sklearn/PyTorch）
# Debian专属apt-get命令，--no-install-recommends 精简依赖，最后清理缓存减小体积
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    poppler-utils \
    gcc \
    g++ \
    libc6-dev \
    liblapack-dev \
    libblas-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# 升级pip并配置清华国内源（加速依赖安装，避免国外源超时）
RUN pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装Python项目依赖（含PyTorch/sklearn/OCR相关，兼容Python3.8）
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制本地项目代码到容器工作目录
COPY . $WORKDIR
WORKDIR /app/tender

EXPOSE 8000
# 容器启动命令（按需替换为你的项目主程序，如main.py/ocr_app.py）
CMD ["python", "main.py"]