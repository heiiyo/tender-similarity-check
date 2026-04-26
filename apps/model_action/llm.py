from abc import ABC
from typing import Union, List

import httpx
import requests

from apps import ConcurrencyManager
from apps.algorithms.embedding import BaseVectorizer
from apps.model_action.vllm_service import PromptTemplate, HumanMessage

from logger_config import get_logger

logger = get_logger(name=__package__)





class BaseModel(ABC):

    def __init__(self, model_name, url, api_key):
        self.model_name = model_name
        self.url = url
        self.api_key = api_key
        self.concurrency_manager = ConcurrencyManager()

    async def invoke(self, content: Union[str, PromptTemplate]):
        pass


class EmbeddingModel(BaseModel):

    async def invoke(self, content: Union[str, PromptTemplate, List[str]]):
        # 调用通义千问API生成向量...
        """
        获取文本的向量表示。使用 Qwen3-Embedding。
        :param content: 文本内容
        :return: 文本向量
        """
        # 构造API请求参数
        payload = {
            "model": self.model_name,
            "input": content
        }

        try:
            # logger.info(f"模型输入参数：{data}")
            headers = {'Content-Type': 'application/json', "Authorization": f"Bearer {self.api_key}"}
            # 1. 创建异步客户端
            async with httpx.AsyncClient(
                    headers=headers,
                    timeout=httpx.Timeout(timeout=30000)
            ) as client:
                # 1. 发起请求并等待完整响应
                response = await client.post(self.url, json=payload)
                # 2. 检查状态码
                if response.status_code != 200:
                    error_text = response.json()
                    raise Exception(f"LLM Error [{response.status_code}]: {error_text}")
                # 3. 解析 JSON 响应
                result = response.json()
                # 提取向量
                embeddings = [item["embedding"] for item in result["data"]]
            return embeddings
        except requests.exceptions.RequestException as e:
            raise ValueError(f"API调用失败：{str(e)}")
        except KeyError as e:
            raise ValueError(f"响应解析失败：缺失字段{e}")


class LLMModel(BaseModel):

    async def invoke(self, content: Union[str, PromptTemplate]):
        """
        大模型调用
        :param content: 输入内容
        :return:
        """
        api_key = self.api_key
        if isinstance(content, str):
            message = PromptTemplate([HumanMessage(content)])
        else:
            message = content
        if not message:
            return None
        data = {
            "model": self.model_name,
            "messages": message.to_dict(),
            "response_format": {
                "type": "json_object"
            },
            # "temperature": 0,   # 必须设为 0 或很低以保证确定性
            "stream": False,
            "temperature": 0,
            "top_p": 1,
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.1,
            "chat_template_kwargs": {"enable_thinking": False}
        }

        # logger.info(f"模型输入参数：{data}")
        headers = {'Content-Type': 'application/json', "Authorization": f"Bearer {api_key}"}
        # 1. 创建异步客户端
        async with httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(timeout=30000)
        ) as client:
            # 1. 发起请求并等待完整响应
            response = await client.post(self.url, json=data)
            # 2. 检查状态码
            if response.status_code != 200:
                error_text = response.json()
                raise Exception(f"LLM Error [{response.status_code}]: {error_text}")
            # 3. 解析 JSON 响应
            result = response.json()
            # logger.info(f"模型输出结果：{result}")
        return result