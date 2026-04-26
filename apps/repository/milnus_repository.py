from typing import List

from pymilvus import (
    Collection,
    CollectionSchema,
    utility, MilvusException
)

from apps.algorithms.embedding import OllamaQwenEmbeddingVectorizer, QwenEmbeddingVectorizer
from apps.document_parser.base import HDocument

# ------------------- 1. 初始化配置 -------------------
TOP_K = 10  # 查询返回Top3相似结果


# ------------------- 3. Milvus 核心操作 -------------------
class MilvusVectorDB:
    def __init__(self, fields, collection_name, index_field_name, index_params):
        # 连接Milvus服务
        self.fields = fields
        self.collection_name = collection_name
        self.index_field_name = index_field_name
        self.index_params = index_params
        self.collection = None
        self.get_collection()
    
    def get_collection(self) -> Collection:
        if utility.has_collection(self.collection_name):
            if not self.collection:
                self.collection = Collection(name=self.collection_name)
        else:
            self.collection = self._create_collection()
        if not self._has_index_safe(self.index_field_name):
            # 创建索引
            self._create_index(self.index_field_name, self.index_params)
        return self.collection

    def _has_index_safe(self, index_name: str) -> bool:
        try:
            # describe_index 会返回索引信息列表，若无则抛异常
            indexes = self.collection.indexes
            return any(idx.index_name == index_name for idx in indexes)
        except MilvusException:
            return False

    def _create_collection(self):
        """创建Milvus集合（表）"""
        
        # 定义集合Schema
        schema = CollectionSchema(self.fields, description="标书文本向量集合")
        collection = Collection(name=self.collection_name, schema=schema)
        return collection
    
    def _create_index(self, field_name, index_params):
        """
        创建索引
        # 创建向量索引（必须创建索引才能高效查询）
        index_params = {
            "index_type": "IVF_FLAT",  # 基础索引，适合小数据量
            "metric_type": "COSINE",   # 相似度度量：余弦相似度（文本检索首选）
            "params": {"nlist": 128}   # 索引参数，nlist越大查询越准但速度越慢
        }
        """
        self.collection.create_index(field_name=field_name, index_params=index_params)

    def insert_info(self, data, batch_size=700):
        print(f"插入向量库的总数据量{len(data[0])}")
        length = len(data[0])
        for i in range(0, length, batch_size):
            batch_list = []
            for item in data:
                batch_list.append(item[i:i + batch_size])
            insert_result = self.get_collection().insert(batch_list)
            print(f"插入成功，插入数量：{len(insert_result.primary_keys)}")
            self.collection.flush()  # 刷盘，确保数据持久化
        print(f"集合总数据量：{self.collection.num_entities}")
        self.collection.load()

    def insert_data(self, documents: List[HDocument]):
        """插入文本数据（存储）"""
        # 文本转向量
        vectorizer = QwenEmbeddingVectorizer()
         # 构造插入数据
        data = []
        vec_list = []
        file_ids = []
        pages = []
        start_indexes = []
        texts = []
        for document in documents:
            if document.text.strip():
                print(f"文件页数：{str(document.page)}，开始位置：{document.start_index}", f"文本内容：{document.text}")
                vectors = vectorizer.encode(document.text)
                vec_list.extend(vectors)
                file_ids.append(document.file_id)
                pages.append(document.page)
                start_indexes.append(document.start_index)
                texts.append(document.text)
       
        # 插入Milvus
        insert_result = self.get_collection().insert([file_ids, pages, start_indexes, texts, vec_list])
        self.collection.flush()  # 刷盘，确保数据持久化
        print(f"插入成功，插入数量：{len(insert_result.primary_keys)}")
        print(f"集合总数据量：{self.collection.num_entities}")
        self.collection.load()
        return insert_result
    
    def query_data(self, expr: str, output_fields: List[str] = None):
        self.collection.load()
        return self.collection.query(expr=expr, output_fields=output_fields)

    def search_similar(self, expr, query_vector, output_fields=["page", "start_index", "text_content"], top_k=TOP_K):
        """相似性查询"""
        # 2. 加载集合到内存（查询前必须加载）
        self.collection.load()
        # 3. 定义查询参数
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 128}  # 查询参数，nprobe越大越准但速度越慢
        }
        # 4. 执行查询
        results = self.collection.search(
            data=query_vector,          # 查询向量
            expr=expr,
            anns_field="vector",   # 向量字段名
            param=search_params,
            limit=top_k,                # 返回TopK
            output_fields=output_fields  # 返回的字段（除向量外）
        )
        # 5. 解析结果
        search_results = []
        for hits in results:
            for hit in hits:
                item = {
                    "id": hit.id,
                    "similarity": hit.score,  # 相似度得分（余弦相似度：0~1，越高越相似）
                }
                # 2. 动态遍历 output_fields 进行赋值
                # 兼容不同版本的 SDK 字段访问方式 (hit.fields 或 hit.entity)
                source_data = getattr(hit, 'fields', None) or getattr(hit, 'entity', None)
                if source_data:
                    if output_fields:
                        for field_name in output_fields:
                            # 安全获取，防止字段不存在报错
                            item[field_name] = source_data.get(field_name, None)
                    # 3. 如果 output_fields 为空但仍有实体数据，可选择保留所有返回字段
                elif hasattr(hit, 'fields'):
                    item.update(hit.fields)
                search_results.append(item)
        return search_results

