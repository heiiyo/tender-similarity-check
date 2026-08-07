import asyncio
from io import BytesIO
from typing import List

from docx import Document as DocxDocument

from apps import AppContext
from apps.document_parser.base import HFiledocument, HDocument
from apps.document_parser.base_parser import BaseParser
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__name__)


class DocParser(BaseParser):
    """
    Word文档解析器（支持.docx和.doc格式）
    使用python-docx库解析文档内容
    """

    def __init__(self):
        super().__init__()
        self.image_ids = []

    def parse(self, filename=None, stream=None, file_id=None) -> HFiledocument:
        """
        解析Word文档为结构化数据

        :param filename: 文件路径
        :param stream: 二进制流
        :param file_id: 文件ID
        :return: HFiledocument链表结构
        """
        try:
            if stream:
                doc = DocxDocument(stream)
            elif filename:
                doc = DocxDocument(filename)
            else:
                raise ValueError("必须提供filename或stream参数")

            return self._extract_content(doc, file_id)

        except Exception as e:
            logger.error(f"Word文档解析失败: {str(e)}", exc_info=True)
            return None

    def _extract_content(self, doc: DocxDocument, file_id: int) -> HFiledocument:
        """
        从docx文档中提取内容，按段落组织

        :param doc: docx文档对象
        :param file_id: 文件ID
        :return: HFiledocument链表
        """
        root_document = None
        last_document = None

        # 按段落提取文本，简单按段落分组（每页作为一个节点）
        # 由于docx没有明确的页概念，我们按段落数量估算分页
        paragraphs_per_page = 30  # 估算每页30个段落

        current_page = 1
        current_paragraphs = []
        page_texts = {}

        for idx, paragraph in enumerate(doc.paragraphs):
            current_paragraphs.append(paragraph.text)

            # 当达到每页段落数或到达文档末尾时，保存页面内容
            if len(current_paragraphs) >= paragraphs_per_page or idx == len(doc.paragraphs) - 1:
                page_text = "\n".join(current_paragraphs)
                if page_text.strip():  # 只保存非空页面
                    page_texts[current_page] = page_text
                current_paragraphs = []
                current_page += 1

        # 构建HFiledocument链表
        for page_num, text in sorted(page_texts.items()):
            if text.strip():
                if root_document:
                    next_doc = HFiledocument(file_id, page_num, text)
                    last_document.next = next_doc
                    last_document = next_doc
                else:
                    root_document = HFiledocument(file_id, page_num, text)
                    last_document = root_document

        return root_document

    def to_images(self, tender_file_id: int, zoom=1.5):
        """
        Word文档转换为图片（占位实现）
        由于Word转图片需要额外的依赖（如LibreOffice），这里先返回空列表
        如果需要此功能，可以后续集成LibreOffice或Microsoft Office API

        :param tender_file_id: 标书文件ID
        :param zoom: 缩放倍率（暂不使用）
        :return: 图片ID列表
        """
        logger.warning(f"Word文档(tender_file_id={tender_file_id})不支持直接转图片，跳过此步骤")
        self.image_ids = []
        return []

    def overlapping_splitting(self, file_document: HFiledocument, chunk_size: int = 2000, overlap: int = 100) -> List[HDocument]:
        """
        重叠切片逻辑，与PDF保持一致

        :param file_document: Word解析后的文件数据
        :param chunk_size: 切片大小
        :param overlap: 重叠部分的长度
        :return: HDocument列表
        """
        documents: list[HDocument] = []

        for page_document in file_document:
            text_content = page_document.page_content
            text_chunks = text_content.split('\n')

            for text in text_chunks:
                text = ' '.join(text.split())  # 清理多余空格
                if not text or len(text) < 1:
                    continue

                punctuations = r'，。！？；\n'
                text_length = len(text)
                current_start = 0

                if text_length <= chunk_size:
                    document = HDocument(page_document.file_id, page_document.page, current_start, text)
                    documents.append(document)
                    continue

                punctuation_pattern = __import__('re').compile(f'[{punctuations}]')
                chunks = []

                while current_start < text_length:
                    target_end = current_start + chunk_size

                    if target_end >= text_length:
                        chunks.append(text[current_start:])
                        document = HDocument(page_document.file_id, page_document.page, current_start, text[current_start:])
                        documents.append(document)
                        break

                    if text[target_end] in punctuations:
                        split_end = target_end + 1
                    else:
                        match = punctuation_pattern.search(text, target_end, target_end + 200)
                        if match:
                            split_end = match.end()
                        else:
                            split_end = target_end

                    current_chunk = text[current_start:split_end]
                    chunks.append(current_chunk)
                    document = HDocument(page_document.file_id, page_document.page, current_start, current_chunk)
                    documents.append(document)

                    current_start = split_end - overlap
                    if current_start < 0:
                        current_start = 0

                    if current_start >= text_length or (len(chunks) >= 2 and current_start == chunks[-2]):
                        break

        return documents
