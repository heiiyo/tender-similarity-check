from minio import Minio

# 依赖函数：返回 MinIO 客户端
def get_minio_client() -> Minio:
    from main import app
    return app.state.minio_client