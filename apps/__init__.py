from fastapi import FastAPI
from minio import Minio, S3Error
from pathlib import Path
from pymilvus import connections
from sqlalchemy import create_engine, QueuePool
from sqlalchemy.orm import sessionmaker

from apps.tools.asyncio_tool import ConcurrencyManager


class AppContext:

    _instance = None  # ← 类变量，存储唯一实例

    project_root = Path(__file__).parent.parent

    def __new__(cls, app: FastAPI = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.app = app
        return cls._instance

    @staticmethod
    def start(app):
        app_context = AppContext(app).init_context()
        from apps.web.api import file_api, tender_api, tender_compliance_api
        app_context.app.include_router(file_api.file_router)
        app_context.app.include_router(tender_api.tender_router)
        app_context.app.include_router(tender_compliance_api.tender_compliance_router)

    def init_context(self):
        from config import (data_config, milvus_config, minio_config,
                            mysql_config, llm_model_config, embedding_config, mineru_config, orc_model_config)
        if self.app:
            self.app.state.app_context = self
            self.app.state.app_config = data_config
            self.app.state.milvus_config = milvus_config
            self.app.state.minio_config = minio_config
            self.app.state.mysql_config = mysql_config
            self.app.state.llm_model_config = llm_model_config
            self.app.state.embedding_config = embedding_config
            self.app.state.orc_model_config = orc_model_config
        self.app_config = data_config
        self.milvus_config = milvus_config
        self.minio_config = minio_config
        self.mysql_config = mysql_config
        self.llm_model_config = llm_model_config
        self.embedding_config = embedding_config
        self.mineru_config = mineru_config
        self.orc_model_config = orc_model_config
        self._init()
        return self

    def _init(self):
        # 设置异步管理器，限制协程并发数
        self.concurrency_manager = ConcurrencyManager()
        self._init_mysql()
        self._init_milvus()
        self._init_minio()
        self._init_llm()
        self._init_embedding()
        self._init_agent_model()
        self._init_ocr_model()


    def _init_mysql(self):
        """
        初始化mysql数据库连接，配置连接池
        """
        mysql_conf = self.mysql_config

        # 连接池配置参数
        pool_size = mysql_conf.get("pool_size", 10)  # 连接池大小，默认10
        max_overflow = mysql_conf.get("max_overflow", 20)  # 超出pool_size后最多可创建的连接数，默认20
        pool_timeout = mysql_conf.get("pool_timeout", 30)  # 获取连接的超时时间（秒），默认30秒
        pool_recycle = mysql_conf.get("pool_recycle", 300)  # 连接回收时间（秒），防止MySQL 8小时超时，默认300秒
        pool_pre_ping = mysql_conf.get("pool_pre_ping", True)  # 每次使用前检查连接是否有效，默认True
        echo = mysql_conf.get("echo", False)  # 是否打印SQL日志，生产环境建议False

        # 创建引擎，配置连接池
        engine = create_engine(
            mysql_conf["database_url"],
            poolclass=QueuePool,  # 使用队列连接池（推荐用于生产环境）
            pool_size=pool_size,  # 连接池大小
            max_overflow=max_overflow,  # 最大溢出连接数
            pool_timeout=pool_timeout,  # 获取连接超时时间
            pool_recycle=pool_recycle,  # 连接回收时间
            pool_pre_ping=pool_pre_ping,  # 自动重连
            echo=echo,  # SQL日志
            pool_use_lifo=True,  # 使用LIFO算法，提高连接复用率
        )

        self.engine = engine

        # 创建会话工厂
        db_session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False  # 提交后不立即过期对象，提高性能
        )

        if self.app:
            self.app.state.db_engine = engine
            self.app.state.db_session_factory = db_session_factory

        self.db_engine = engine
        self.db_session_factory = db_session_factory

        # 自动建表（仅开发环境建议使用！）
        from apps.repository.entity import Base
        from apps.repository.entity.file_entity import FileRecordEntity
        from apps.repository.entity.tender_entity import BidPlagiarismCheckTask, SubBidPlagiarismCheckTask, DocumentSimilarityRecord, TenderRuleConfiguration, TenderPDFImageEntity
        Base.metadata.create_all(bind=engine)

    def _init_milvus(self):
        host = self.milvus_config["host"]
        port = self.milvus_config["port"]
        db_name = self.milvus_config["db_name"]
        connections.connect(
            alias="default",
            host=host,
            port=port,
            db_name=db_name
        )
        if self.app:
            self.app.state.milvus_connections = connections
        self.milvus_connections = connections

    def _init_minio(self):
        """
        初始化minio
        """
        minio_client = Minio(
            endpoint=self.minio_config["host"],
            access_key=self.minio_config["access_key"],
            secret_key=self.minio_config["secret_key"],
            secure=False
        )
        if self.app:
            self.app.state.minio_client = minio_client
        self.minio_client = minio_client
        try:
            if not minio_client.bucket_exists(self.minio_config["bucket_name"]):
                minio_client.make_bucket(self.minio_config["bucket_name"])
        except S3Error as e:
            if "BucketAlreadyOwnedByYou" not in str(e):
                raise

    def _init_llm(self):
        from apps.model_action.llm import LLMModel
        llm_model_config = self.llm_model_config
        self.llm_model = LLMModel(url=llm_model_config['llm_url'], model_name=llm_model_config['llm_model_name'], api_key=llm_model_config['api_key'])

    def _init_agent_model(self):
        from langchain_siliconflow import ChatSiliconFlow
        llm_model_config = self.llm_model_config
        self.agent_model = ChatSiliconFlow(
                                    base_url=llm_model_config['llm_url'],
                                    model=llm_model_config['llm_model_name'],
                                    api_key=llm_model_config['api_key'],
                                    temperature=llm_model_config['temperature'],
                                    max_tokens=llm_model_config['max_tokens'],
                                    timeout=llm_model_config['timeout'],
                                    extra_body=llm_model_config['extra_body'])

    def _init_embedding(self):
        from apps.algorithms.embedding import QwenEmbeddingVectorizer
        embedding_model_config = self.embedding_config
        self.embedding_vectorizer = QwenEmbeddingVectorizer(
            api_key=embedding_model_config['api_key'],
            model_name=embedding_model_config['model_name'],
            base_url=embedding_model_config['url']
        )

    def _init_ocr_model(self):
        """
        初始化OCR视觉大模型
        """
        from langchain_siliconflow import ChatSiliconFlow
        orc_config = self.orc_model_config

        # 从配置中读取base_url，如果包含/chat/completions则去掉
        base_url = orc_config['url']
        if base_url.endswith('/chat/completions'):
            base_url = base_url.replace('/chat/completions', '')

        self.ocr_model = ChatSiliconFlow(
            base_url=base_url,
            model=orc_config['model_name'],
            api_key=orc_config['api_key'],
            temperature=0,
            max_tokens=1000,
            timeout=300
        )

