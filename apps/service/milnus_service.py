from pymilvus import DataType, FieldSchema

from apps import AppContext
from apps.repository.milnus_repository import MilvusVectorDB


def create_tender_reference_vector_milvus_db(vector_dim) -> MilvusVectorDB:
    """
    创建一个标书招标文件的向量操作对象
    :param vector_dim: 向量维度
    :return:
    """
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True  # 自动生成ID
        ),
        FieldSchema(
            name="file_id",
            dtype=DataType.INT64,
            max_length=50
        ),
        FieldSchema(
            name="text_content",
            dtype=DataType.VARCHAR,
            max_length=8000  # 文本最大长度
        ),
        FieldSchema(
            name="vector",
            dtype=DataType.FLOAT_VECTOR,
            dim=vector_dim  # 向量维度需与模型输出一致
        )
    ]
    index_params = {
        "index_type": "IVF_PQ",  # 基础索引，适合小数据量
        "metric_type": "COSINE",  # 相似度度量：余弦相似度（文本检索首选）
        "m": 16,
        "params": {"nlist": 128}  # 索引参数，nlist越大查询越准但速度越慢
    }
    return MilvusVectorDB(fields, "tender_reference_vector_collection", "vector", index_params)


def create_tender_topic_vector_milvus_db(vector_dim) -> MilvusVectorDB:
    # 定义字段：主键ID + 文件唯一 + 标识符 + 文件页 + 片段在文档页中的位置 + 片段的文本内容 + 向量字段
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True  # 自动生成ID
        ),
        FieldSchema(
            name="topic_content",
            dtype=DataType.VARCHAR,
            max_length=8000  # 文本最大长度
        ),
        FieldSchema(
            name="start_page",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="end_page",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="tender_file_id",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="vector",
            dtype=DataType.FLOAT_VECTOR,
            dim=vector_dim  # 向量维度需与模型输出一致
        )
    ]
    index_params = {
        "index_type": "IVF_PQ",  # 基础索引，适合小数据量
        "metric_type": "COSINE",  # 相似度度量：余弦相似度（文本检索首选）
        "m": 16,
        "params": {"nlist": 128}  # 索引参数，nlist越大查询越准但速度越慢
    }
    return MilvusVectorDB(fields, "tender_topic_vector_collection", "vector", index_params)


def create_tender_vector_milvus_db(vector_dim) -> MilvusVectorDB:
    # 定义字段：主键ID + 文件唯一 + 标识符 + 文件页 + 片段在文档页中的位置 + 片段的文本内容 + 向量字段
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True  # 自动生成ID
        ),
        FieldSchema(
            name="file_id",
            dtype=DataType.INT64,
            max_length=50
        ),
        FieldSchema(
            name="page",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="start_index",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="text_content",
            dtype=DataType.VARCHAR,
            max_length=8000  # 文本最大长度
        ),
        FieldSchema(
            name="vector",
            dtype=DataType.FLOAT_VECTOR,
            dim=vector_dim  # 向量维度需与模型输出一致
        ),
        FieldSchema(
            name="topic",
            dtype=DataType.VARCHAR,
            max_length=100  # 向量维度需与模型输出一致
        )
    ]
    index_params = {
        "index_type": "IVF_PQ",  # 基础索引，适合小数据量
        "metric_type": "COSINE",  # 相似度度量：余弦相似度（文本检索首选）
        "m": 16,
        "params": {"nlist": 128}  # 索引参数，nlist越大查询越准但速度越慢
    }
    return MilvusVectorDB(fields, "tender_vector_collection", "vector", index_params)


def create_main_topic_vector_milvus_db(vector_dim) -> MilvusVectorDB:
    # 定义字段：主键ID + 文件唯一 + 标识符 + 文件页 + 片段在文档页中的位置 + 片段的文本内容 + 向量字段
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True  # 自动生成ID
        ),
        FieldSchema(
            name="topic",
            dtype=DataType.VARCHAR,
            max_length=8000
        ),
        FieldSchema(
            name="vector",
            dtype=DataType.FLOAT_VECTOR,
            dim=vector_dim  # 向量维度需与模型输出一致
        )
    ]
    index_params = {
        "index_type": "IVF_PQ",  # 基础索引，适合小数据量
        "metric_type": "COSINE",  # 相似度度量：余弦相似度（文本检索首选）
        "m": 16,
        "params": {"nlist": 128}  # 索引参数，nlist越大查询越准但速度越慢
    }
    return MilvusVectorDB(fields, "main_text_vector", "vector", index_params)



def create_rm_text_vector_milvus_db(vector_dim) -> MilvusVectorDB:
    # 定义字段：主键ID + 文件唯一 + 标识符 + 文件页 + 片段在文档页中的位置 + 片段的文本内容 + 向量字段
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True  # 自动生成ID
        ),
        FieldSchema(
            name="text_content",
            dtype=DataType.VARCHAR,
            max_length=8000
        ),
        FieldSchema(
            name="vector",
            dtype=DataType.FLOAT_VECTOR,
            dim=vector_dim  # 向量维度需与模型输出一致
        )
    ]
    index_params = {
        "index_type": "IVF_PQ",  # 基础索引，适合小数据量
        "metric_type": "COSINE",  # 相似度度量：余弦相似度（文本检索首选）
        "m": 16,
        "params": {"nlist": 128}  # 索引参数，nlist越大查询越准但速度越慢
    }
    return MilvusVectorDB(fields, "rm_text_vector", "vector", index_params)



