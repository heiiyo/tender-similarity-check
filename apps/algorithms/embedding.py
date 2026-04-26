import abc
from typing import List, Optional, Union

import numpy as np
import requests



class BaseVectorizer(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def get_vector_dim(self) -> int:
        """获取向量维度（必须实现）"""
        pass

    @abc.abstractmethod
    def encode(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        生成文本向量（核心方法）
        :param texts: 单个文本字符串 或 文本列表
        :return: 向量数组（shape: [文本数, 向量维度]）
        """
        pass

class QwenEmbeddingVectorizer(BaseVectorizer):
    def __init__(self, api_key: str = "ms-9c27e58a-3c49-426a-9d39-2631c44c0073", model_name: str = "Qwen/Qwen3-Embedding-8B"):
        self.api_key = api_key
        self.model_name = model_name
        # 初始化通义千问客户端...

    def get_vector_dim(self) -> int:
        return 4096  # 通义千问向量维度

    def encode_group(self, texts: List[str], group_size=50):
        if len(texts) <= group_size:
            return self.encode(texts)
        groups = [texts[i:i + group_size] for i in range(0, len(texts), group_size)]
        all_ems = []
        for item in groups:
            ems = self.encode(item)
            all_ems.extend(ems)
        return all_ems

    def encode(self, texts: Union[str, List[str]]) -> List[float]:
        # 调用通义千问API生成向量...
        """
        获取文本的向量表示。使用 Qwen3-Embedding。
        :param texts: 文本内容
        :return: 文本向量
        """

        # 构造API请求参数
        payload = {
            "model": "qwen3-8b-embd",
            "input": texts
        }

        try:
            # 发送POST请求
            response = requests.post(
                "http://127.0.0.1:30041/v1/embeddings",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30  # 批量请求延长超时
            )
            response.raise_for_status()  # 抛出HTTP错误
            result = response.json()
            # embs = [embedding["embedding"] for embedding in result["data"]]
            # emb = result["data"][0]["embedding"]

            # 提取向量
            embeddings = [item["embedding"] for item in result["data"]]
            return embeddings
        except requests.exceptions.RequestException as e:
            raise ValueError(f"API调用失败：{str(e)}")
        except KeyError as e:
            raise ValueError(f"响应解析失败：缺失字段{e}")

class OllamaQwenEmbeddingVectorizer(BaseVectorizer):
    def get_vector_dim(self) -> int:
        return 4096  # 通义千问向量维度

    def encode(
        self,
        texts: Union[str, List[str]]
    ) -> List[float]:
        """
        生成文本向量
        :param texts: 单个文本/文本列表
        :param normalize: 是否归一化向量
        :return: 向量数组（shape：单文本→(1,1536)，批量→(n,1536)）
        """
        # 统一转为列表
        # if isinstance(texts, str):
        #     texts = [texts]
        
        # 构造API请求参数
        payload = {
            "model": "qwen3-8b-embd",
            "input": texts
        }

        try:
            # 发送POST请求
            response = requests.post(
                "http://127.0.0.1:30041/v1/embeddings",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30  # 批量请求延长超时
            )
            response.raise_for_status()  # 抛出HTTP错误
            result = response.json()

            # 提取向量
            #embeddings = [item["embedding"] for item in result["embeddings"]]
            return result["embedding"]
        except requests.exceptions.RequestException as e:
            raise ValueError(f"API调用失败：{str(e)}")
        except KeyError as e:
            raise ValueError(f"响应解析失败：缺失字段{e}")