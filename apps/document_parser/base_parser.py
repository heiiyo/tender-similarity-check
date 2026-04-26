import asyncio
import bisect
import json
from abc import ABC, abstractmethod
import re
from io import BytesIO
from typing import List

import fitz
import requests

from apps import AppContext
from apps.document_parser.base import HDocument, HFiledocument
from apps.repository.entity.file_entity import FileRecordEntity


class BaseParser(ABC):
   
    def __init__(self):
        self.image_ids = []

    @abstractmethod
    def parse(self, filename=None, stream=None, file_id=None) -> HFiledocument:
        """
        文档解析器功能，将文件中的内容转化为可读字符串
        
        :param filename: 需要解析的文件
        :param stream: 二进制流
        :param file_id: 文件标识id
        :return: 返回解析的文本内容，字符串类型
        :rtype: str
        """ 
        pass

    def parse_topic(self):
        """
        文档解析器功能，将文件中的内容转化为可读字符串

        :param filename: 需要解析的文件
        :param stream: 二进制流
        :param file_id: 文件标识id
        :return: 返回解析的文本内容，字符串类型
        :rtype: str
        """
        self.image_ids
        pass

    def remove_item(self, text: str):
        """
        移除目录
        :param text: 文本内容
        :return:
        """
        pattern = re.compile(
            r'.*[.|·]+\s*\d+$',  # 匹配任意字符 + 空格/点号 + 页码
            re.MULTILINE  # 支持多行匹配
        )
        # 替换为空字符串
        cleaned_text = re.sub(pattern, '', text)
        cleaned_text = cleaned_text.strip().replace("\n", "").replace("\r", "")
        return cleaned_text

    def _remove_top(self, text: str):
        pattern = re.compile(
            r'^\s*(\d+|[一二三四五六七八九十]+)、.*',
            re.MULTILINE  # 支持多行匹配
        )
        # 替换为空字符串目录
        cleaned_text = re.sub(pattern, '', text)
        cleaned_text = re.sub(r'^(\d+(\.\d+)*\.\s*)+(.*)', r'', cleaned_text, flags=re.MULTILINE)
        cleaned_text.strip().replace("\n", " ").replace("\r", "")
        return cleaned_text

    def clean_text(self, text: str) -> str:
        """
        清除掉干扰的内容

        :param text: 需要清除前的文本内容
        :return: 返回清除后的文本内容
        :rtype: str
        """
        #cleaned_text = self.remove_item(text)
        #cleaned_text = self._remove_top(cleaned_text)
        #return cleaned_text.strip()  # 去除首尾空白
        pass
    
    def topic_splitting(self, text: str):
        """
        主题切分，将文档按照主题章节进行切分
        
        :param text: 文档内容
        :type text: str
        :return: 切分后的片段数据，数组类型
        :rtype: list[str]
        """
        pass

    def _get_stop_words(self):
        """加载中文停用词（无实际语义的词，如：的、了、在）"""
        stop_words = [
            '的', '了', '在', '是', '我', '你', '他', '她', '它', '我们', '你们', '他们',
            '和', '或', '但', '如果', '就', '都', '也', '还', '只', '个', '本', '该',
            '及', '与', '等', '对', '对于', '关于', '根据', '按照', '为了', '由于',
            '之', '其', '所', '以', '而', '并', '又', '且', '即', '则', '因', '故'
        ]
        return stop_words
    
    def preprocess_text(self, text):
        """
        文本预处理：去特殊符号、去多余空格、统一格式
        :param text: 预处理文本内容
        """
        # 去除特殊符号（保留中文、英文、数字）
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', ' ', text)
        # 去除多余空格（多个空格合并为一个，首尾空格去除）
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    
    def tender_overlapping_splitting(self: str, text:str, max_length=200, overlap=10) -> List[str]:
        """
            将文本按固定长度切分，允许重叠部分。

            参数:
                text (str): 输入文本
                max_length (int): 每个片段的最大长度（字数）
                overlap (int): 片段之间的重叠字数

            返回:
                List[str]: 分割后的文本片段列表
            """
        result = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + max_length
            fragment = text[start:end]
            result.append(fragment)
            start = end - overlap  # 滑动窗口
            start = max(start, 0)  # 确保 start >= 0
        return result

    
    def overlapping_splitting(self, file_document: HFiledocument, chunk_size: int = 2000, overlap: int = 100) -> List[HDocument]:
        """
        重叠切片逻辑，将长文本内容切割成不同的小段，选择重叠切片，真强语义的连贯性
        :param file_document: pdf解析后的文件数据
        :param chunk_size: 切片大小
        :type chunk_size: int
        :param overlap: 重叠部分的长度
        :type overlap: int
        :return: 返回字符串数组，为切好的多片段数据
        :rtype: list[str]
        """
        documents: list[HDocument] = []
        for page_document in file_document:
            text_content = page_document.page_content
            # 根据换行符来切分文件
            text_chunks = text_content.split('\n')
            for text in text_chunks:
                text = re.sub(r'\s+', ' ', text).strip()
                # text = self.clean_text(text)
                if not text or len(text) < 1:
                    continue
                punctuations: str = r'，  。！？；\n'
                text_length = len(text)
                current_start = 0
                if text_length <= chunk_size:
                    document = HDocument(page_document.file_id, page_document.page, current_start, text[current_start:])
                    documents.append(document)
                    continue
                # 编译正则：匹配任意结束标点（用于快速查找）
                punctuation_pattern = re.compile(f'[{punctuations}]')
                chunks = []

                while current_start < text_length:
                    # 1. 计算目标结束位置（当前起始 + 目标长度）
                    target_end = current_start + chunk_size

                    # 2. 处理边界：如果目标结束超过文本长度，直接取剩余部分
                    if target_end >= text_length:
                        chunks.append(text[current_start:])
                        document = HDocument(page_document.file_id, page_document.page, current_start, text[current_start:])
                        documents.append(document)
                        break

                    # 3. 检查目标结束位置是否是标点
                    if text[target_end] in punctuations:
                        split_end = target_end + 1  # 包含标点
                    else:
                        # 4. 向后找最近的标点（最多搜索200字符，避免无标点极端情况）
                        match = punctuation_pattern.search(text, target_end, target_end + 200)
                        if match:
                            split_end = match.end()  # 匹配到的标点结束位置
                        else:
                            # 兜底：找不到标点则按目标长度切分
                            split_end = target_end

                    # 5. 截取当前块并加入列表
                    current_chunk = text[current_start:split_end]
                    chunks.append(current_chunk)
                    document = HDocument(page_document.file_id, page_document.page, current_start, current_chunk)
                    documents.append(document)
                    # 6. 更新下一块的起始位置（当前结束 - 重叠长度）
                    current_start = split_end - overlap

                    # 防护：避免起始位置回退过多（比如重叠长度大于当前块）
                    if current_start < 0:
                        current_start = 0
                    # 防护：避免死循环（相邻起始位置无变化）
                    if current_start >= text_length or (len(chunks) >= 2 and current_start == chunks[-2]):
                        break
            
        return documents

    async def to_images(self, tender_file_id, zoom=3.0):
        """
        使用 PyMuPDF 快速转换 PDF 为图片
        :param tender_file_id 标书文件id
        :param zoom: 缩放倍率 (zoom=3.0 约等于 300 DPI，视原图大小而定)
        """
        app_context = AppContext()
        minio_client = app_context.minio_client
        with app_context.db_session_factory() as session:
            task_record: FileRecordEntity = session.get(FileRecordEntity, tender_file_id)
        with minio_client.get_object(task_record.business_id, task_record.file_path) as response:
            file_data = response.read()  # 自动 close + release_conn
        pdf_stream = BytesIO(file_data)
        from apps.service.file_service import task_upload
        doc: fitz.Document = fitz.open(stream=pdf_stream)
        res = []
        for i in range(0, len(doc), 20):
            batch_tasks = []
            for page_num in range(i, min(i + 20, len(doc))):
                page: fitz.Page = doc.load_page(page_num)
                # 设置变换矩阵，控制分辨率
                # zoom=3.0 对应约 300 DPI (72 * 3 = 216, 实际效果取决于文档原始定义)
                mat = fitz.Matrix(zoom, zoom)
                pix: fitz.Pixmap = page.get_pixmap(matrix=mat)
                batch_tasks.append(task_upload(pix.tobytes(), "png", "images", page_num+1, tender_file_id))
            results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            res.extend(results)
        self.image_ids = res
        return res

    # 调用接口处理PDF文件
    def _mineru266(self, file_path=None, data_stream=None):
        text = ""
        url = "http://127.0.0.1:8001/file_parse"
        data = {
            'server_url': 'http://vllm-server:8000',
            "backend": "vlm-http-client",
            "table_enable": True,
            "parse_method": "auto",
            "lang_list": "ch",
            "return_images": True,
            "return_middle_json": True,
            "return_content_list": True
        }
        if file_path:
            with open(file_path, "rb") as f:
                files = {"files": f}
                res = requests.post(url, files=files, data=data)
                item = res.json()
                print(f"_mineru266 解析结果{item}")
                for k1 in item["results"]:
                    text = item["results"][k1]["md_content"]
                    images = item["results"][k1]["images"]
                    content_list = item["results"][k1]["content_list"]
            return text, images, json.loads(content_list)
        else:
            files = {"files": data_stream}
            res = requests.post(url, files=files, data=data)
            item = res.json()
            for k1 in item["results"]:
                text = item["results"][k1]["md_content"]
                images = item["results"][k1]["images"]
                content_list = item["results"][k1]["content_list"]
            return text, images, json.loads(content_list)

    def is_scanned_pdf(self, filename=None, stream=None):
        """
        判断 PDF 是否为扫描件
        返回 True: 是扫描件 (图片为主)
        返回 False: 是文本 PDF
        """
        doc = fitz.open(filename=filename, filetype="pdf", stream=stream)
        if doc.is_encrypted:
            raise Exception("PDF 文件被加密")

        total_chars = 0
        # 采样检查前 3 页即可
        sample_pages = min(3, len(doc))

        for page_num in range(sample_pages):
            page = doc[page_num]
            # 提取纯文本
            text = page.get_text()
            total_chars += len(text.strip())

            # 优化：如果某页已经有大量文本，直接判定为文本型
            if len(text.strip()) > 200:
                doc.close()
                return False

        # 设置阈值：如果采样页总字符数极少，认为是扫描件
        # 阈值可根据业务调整，一般 < 100 个字符视为无文本层
        doc.close()
        threshold = 50
        return total_chars < threshold
