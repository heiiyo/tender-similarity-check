import yaml
import os
from typing import Dict, List, Optional, Union


class YamlHandler:
    """YAML文件解析工具类"""
    def __init__(self, encoding: str = "utf-8"):
        """
        :param encoding: 文件编码（默认utf-8，解决中文乱码）
        """
        self.encoding = encoding
        # 指定YAML加载器（避免安全警告）
        self.loader = yaml.SafeLoader

    def read_yaml(self, file_path: str) -> Optional[Union[Dict,List]]:
        """
        读取YAML文件
        :param file_path: YAML文件路径
        :return: 解析后的字典/列表（文件不存在/解析失败返回None）
        """
        # 校验文件是否存在
        if not os.path.exists(file_path):
            print(f"错误：YAML文件 {file_path} 不存在！")
            return None
        
        try:
            with open(file_path, "r", encoding=self.encoding) as f:
                # 解析YAML（支持嵌套结构、中文、注释）
                data = yaml.load(f, Loader=self.loader)
            print(f"成功读取YAML文件：{file_path}")
            return data
        except yaml.YAMLError as e:
            print(f"YAML解析失败：{e}")
            return None
        except Exception as e:
            print(f"读取文件失败：{e}")
            return None

    def write_yaml(
        self,
        data: Union[Dict,List],
        file_path: str,
        sort_keys: bool = False,  # 是否按字母排序key（默认不排序，保留原顺序）
        indent: int = 4           # 缩进空格数（美化格式）
    ) -> bool:
        """
        将数据写入YAML文件
        :param data: 要写入的数据（字典/列表）
        :param file_path: 输出文件路径
        :param sort_keys: 是否排序key
        :param indent: 缩进数
        :return: 成功返回True，失败返回False
        """
        try:
            # 确保目录存在
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)
            
            with open(file_path, "w", encoding=self.encoding) as f:
                yaml.dump(
                    data,
                    f,
                    encoding=self.encoding,
                    sort_keys=sort_keys,
                    indent=indent,
                    default_flow_style=False,  # 禁用流式格式（更易读）
                    allow_unicode=True         # 支持中文
                )
            print(f"成功写入YAML文件：{file_path}")
            return True
        except Exception as e:
            print(f"写入YAML失败：{e}")
            return False


# ------------------- 扩展：配置验证（适配你的场景） -------------------
def validate_vector_config(config: Dict) -> bool:
    """
    验证向量生成配置的YAML（示例：适配你之前的向量模块）
    :param config: 解析后的YAML配置字典
    :return: 合法返回True，否则False
    """
    required_keys = ["type", "params"]
    # 校验必填字段
    for key in required_keys:
        if key not in config:
            print(f"配置缺失必填字段：{key}")
            return False
    
    # 校验向量类型合法性
    valid_types = ["doc2vec", "sentencebert", "openai", "qwen-embedding-8b"]
    if config["type"] not in valid_types:
        print(f"不支持的向量类型：{config['type']}，可选：{valid_types}")
        return False
    
    # 校验qwen-embedding-8b的参数
    if config["type"] == "qwen-embedding-8b" and "api_key" not in config["params"]:
        print("qwen-embedding-8b配置缺失api_key！")
        return False
    
    return True


yaml_handler = YamlHandler(encoding="utf-8")
data_config = yaml_handler.read_yaml("application.yml")
print(data_config)
milvus_config = data_config["milvus"]
minio_config = data_config["minio"]
mysql_config = data_config["mysql"]
llm_model_config = data_config["llm_model"]
embedding_config = data_config["embedding"]


__all__ = ["data_config", "milvus_config", "minio_config", "mysql_config", "embedding_config", "llm_model_config"]
