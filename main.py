# app/main.py
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from apps import AppContext
from logger_config import get_logger

logger = get_logger(name=__name__)


@asynccontextmanager
async def start_app(app_context: FastAPI):
    AppContext.start(app_context)
    yield

app = FastAPI(
    title="标书检测应用",
    version="1.0.0",
    lifespan=start_app
)

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境建议指定具体域名）
    allow_credentials=True,  # 允许携带凭证（如 Cookie）
    allow_methods=["*"],  # 允许所有 HTTP 方法（GET, POST, PUT 等）
    allow_headers=["*"],  # 允许所有请求头
)

# 注册子路由（自动带全局前缀）
if __name__ == "__main__":
    """启动 FastAPI 应用"""
    logger.info("--------------tender 服务启动-------------------")
    uvicorn.run(
        "main:app",      # 模块:实例
        host="0.0.0.0",
        port=8000,
        reload=True,         # 开发时开启自动重载
        log_level="info",
        log_config=None
    )

