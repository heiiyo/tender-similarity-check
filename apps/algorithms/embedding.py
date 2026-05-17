import abc
from typing import List, Union

import numpy as np
import requests
from openai import OpenAI


class BaseVectorizer(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def get_vector_dim(self) -> int:
        """获取向量维度（必须实现）"""
        pass

    @abc.abstractmethod
    def encode(self, texts: Union[str, List[str]])-> List[List[float]]:
        """
        生成文本向量（核心方法）
        :param texts: 单个文本字符串 或 文本列表
        :return: 向量数组（shape: [文本数, 向量维度]）
        """
        pass

    def encode_group(self, texts: List[str], group_size=50) -> List[List[float]]:
        if len(texts) <= group_size:
            return self.encode(texts)
        groups = [texts[i:i + group_size] for i in range(0, len(texts), group_size)]
        all_ems = []
        for item in groups:
            ems = self.encode(item)
            all_ems.extend(ems)
        return all_ems


class QwenEmbeddingVectorizer(BaseVectorizer):
    """
    QwenEmbeddingVectorizer
    """
    def __init__(
            self,
            api_key: str = "ms-9c27e58a-3c49-426a-9d39-2631c44c0073",
            model_name: str = "Qwen/Qwen3-Embedding-8B",
            base_url: str = "http://127.0.0.1:30041/v1"
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

    def get_vector_dim(self) -> int:
        return 4096

    def encode(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """
        获取文本的向量表示。使用 OpenAI 客户端调用 Embedding API。
        :param texts: 单个文本字符串或文本列表
        :return: 文本向量列表
        """
        # 统一转为列表
        if isinstance(texts, str):
            texts = [texts]
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=texts
            )
            # 提取向量
            embeddings = [item.embedding for item in response.data]
            return embeddings
        except Exception as e:
            raise ValueError(f"Embedding API调用失败：{str(e)}")

