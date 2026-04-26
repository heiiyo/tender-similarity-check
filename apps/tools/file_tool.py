import os
import json
import aiohttp
import aiofiles
import asyncio


class FileSaver:
    """字符串文件保存工具类"""

    @staticmethod
    def save_text(filename: str, content: str, mode: str = "w", encoding: str = "utf-8") -> bool:
        """
        保存文本内容到文件
        :param filename: 文件名
        :param content: 字符串内容
        :param mode: 写入模式 (w=覆盖, a=追加)
        :param encoding: 编码格式
        """
        try:
            os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
            with open(filename, mode, encoding=encoding) as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"保存失败：{e}")
            return False

    @staticmethod
    def save_json(filename: str, data: dict, indent: int = 2) -> bool:
        """保存 JSON 数据到文件"""
        try:
            json_str = json.dumps(data, ensure_ascii=False, indent=indent)
            return FileSaver.save_text(filename, json_str)
        except Exception as e:
            print(f"JSON 保存失败：{e}")
            return False


def read_md_file(file_path: str, encoding: str = 'utf-8') -> str:
    """
    直接读取 .md 文件内容为字符串
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError:
        # 兼容部分中文旧文档 GBK 编码
        with open(file_path, 'r', encoding='gbk') as f:
            return f.read()
    except Exception as e:
        raise FileNotFoundError(f"无法读取文件：{file_path}")


async def upload_single_file(file_path, start_page=None, end_page=None):
    url = "http://xxxxxxxx:8001/file_parse"

    async with aiohttp.ClientSession() as session:
        # 异步读取文件
        async with aiofiles.open(file_path, 'rb') as f:
            file_data = await f.read()

        # 构建表单
        form = aiohttp.FormData()
        form.add_field('files', file_data, content_type='application/pdf')
        form.add_field('server_url', 'http://vllm-server:8000')
        form.add_field('backend', 'vlm-http-client')
        form.add_field('table_enable', 'true')
        form.add_field('parse_method', 'auto')
        # form.add_field('start_page_id', f'{start_page}')
        # form.add_field('end_page_id', f'{end_page}')
        form.add_field('lang_list', 'ch')
        form.add_field('return_images', 'true')
        form.add_field('return_middle_json', 'true')
        form.add_field('return_content_list', 'true')

        async with session.post(url, data=form) as response:
            result = await response.json()
            print(f"响应: {result['results']}")
    return result['results']


async def concurrent_upload(file_path_list):
    tasks = [upload_single_file(file_path) for file_path in file_path_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

