import base64
import os
import io
from typing import Optional


class Base64ImageUtils:
    """
    Base64 与图片文件互转工具类
    兼容 Python 3.8+
    """

    @staticmethod
    def image_to_base64(image_path: str, include_prefix: bool = False) -> str:
        """
        将本地图片文件转换为 Base64 字符串

        :param image_path: 图片文件路径
        :param include_prefix: 是否包含 data:image/...;base64, 前缀
        :return: Base64 字符串
        """
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
                base64_str = base64.b64encode(image_data).decode('utf-8')

            if include_prefix:
                # 简单推断图片类型，实际可根据 os.path.splitext 获取
                ext = os.path.splitext(image_path)[1].lower().lstrip('.')
                mime_type = f"image/{ext}" if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp'] else "image/octet-stream"
                return f"data:{mime_type};base64,{base64_str}"

            return base64_str
        except FileNotFoundError:
            raise FileNotFoundError(f"图片文件不存在：{image_path}")
        except Exception as e:
            raise RuntimeError(f"图片转 Base64 失败：{e}")

    @staticmethod
    def base64_to_image(base64_str: str, output_path: str) -> bool:
        """
        将 Base64 字符串转换为图片并保存

        :param base64_str: Base64 字符串 (可包含 data: 前缀)
        :param output_path: 输出图片保存路径
        :return: 成功返回 True
        """
        try:
            # 1. 去除可能的 data: 前缀
            if ',' in base64_str:
                base64_str = base64_str.split(',', 1)[1]

            # 2. 解码
            image_data = base64.b64decode(base64_str)

            # 3. 保存文件
            with open(output_path, "wb") as f:
                f.write(image_data)

            return True
        except Exception as e:
            print(f"Base64 转图片失败：{e}")
            return False

    @staticmethod
    def base64_to_image_io(base64_str: str) -> Optional[io.BytesIO]:
        """
        将 Base64 字符串转换为 BytesIO 对象 (不保存文件，适合内存处理)

        :param base64_str: Base64 字符串
        :return: io.BytesIO 对象
        """
        try:
            if ',' in base64_str:
                base64_str = base64_str.split(',', 1)[1]
            image_data = base64.b64decode(base64_str)
            return io.BytesIO(image_data)
        except Exception as e:
            print(f"Base64 转 BytesIO 失败：{e}")
            return None