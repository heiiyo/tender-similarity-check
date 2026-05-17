# 核心修改：改用python:3.13-slim（Debian精简版，glibc兼容，稳定支持所有依赖）
FROM python:3.13-slim AS builder

# 声明维护者
LABEL maintainer="heiiyo <heiiyo@163.com>"

# 环境变量配置
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKDIR=/app/tender \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 创建并切换工作目录
WORKDIR $WORKDIR

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    gcc \
    g++ \
    libc6-dev \
    liblapack-dev \
    libblas-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# 升级pip并配置清华国内源
RUN pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装Python项目依赖
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# ========== 第二阶段：运行时镜像 ==========
FROM python:3.13-slim

LABEL maintainer="heiiyo <heiiyo@163.com>"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKDIR=/app/tender \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR $WORKDIR

# 安装运行时必需的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制项目代码（排除大文件）
COPY . $WORKDIR

# 创建 .dockerignore 中指定的文件不会被复制
# 在 .dockerignore 中添加：
# models/
# *.pt
# *.safetensors
# .git/
# __pycache__/
# *.pyc
# logs/
# tests/

EXPOSE 8000
CMD ["python", "main.py"]
