
# ===== 第一阶段：构建依赖 =====
FROM python:3.13-slim AS builder

LABEL maintainer="heiiyo <heiiyo@163.com>"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /build

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc6-dev \
    liblapack-dev \
    libblas-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# 先升级pip
RUN pip install --upgrade pip

# 复制并安装依赖（利用Docker缓存层）
COPY requirements.txt .
RUN pip install -r requirements.txt

# ===== 第二阶段：运行时镜像 =====
FROM python:3.13-slim

LABEL maintainer="heiiyo <heiiyo@163.com>"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    APP_HOME=/app/tender

WORKDIR $APP_HOME

# 安装运行时系统依赖（OCR和PDF处理必需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 从builder阶段复制已安装的Python包
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 创建非root用户（安全最佳实践）
RUN groupadd -r appuser && useradd -r -g appuser -d $APP_HOME -s /sbin/nologin appuser

# 复制项目文件
COPY . $APP_HOME

# 设置权限
RUN chown -R appuser:appuser $APP_HOME

# 切换到非root用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# 生产环境启动命令
CMD ["python", "main.py"]