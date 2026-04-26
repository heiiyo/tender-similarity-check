import re
import sys
from collections import defaultdict
from typing import List

from apps.document_parser.base import HFiledocument, HDocument
from apps.document_parser.base_parser import BaseParser


class MarkDownParser(BaseParser):

    def overlapping_splitting(self, file_document: HFiledocument, chunk_size: int = 2000, overlap: int = 100)\
            -> List[HDocument]:
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
        topic = ""
        pattern = r'^# (?:（?[一二三四五六七八九]+十[一二三四五六七八九]+）?、?|[0-9]+[.)、]|（[0-9]+）)?\s*.*$'
        for page_document in file_document:
            text_content = page_document.page_content
            # 根据换行符来切分文件
            text_chunks = text_content.split('\n')
            for text in text_chunks:
                text = re.sub(r'\s+', ' ', text).strip()
                #text = self.clean_text(text)
                if len(text) < 1:
                    continue
                punctuations: str = r'，  。！？；'
                text_length = len(text)
                current_start = 0
                match_topic = re.match(pattern, text)
                if match_topic:
                    topic = text
                if text_length <= chunk_size:
                    document = HDocument(page_document.file_id, page_document.page, current_start, text[current_start:], topic)
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
                        document = HDocument(page_document.file_id, page_document.page, current_start,
                                             text[current_start:], topic)
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
                    document = HDocument(page_document.file_id, page_document.page, current_start, current_chunk, topic)
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

    def parse(self, filename=None, stream=None, file_id=None) -> HFiledocument:
        """
        文档解析器功能，将文件中的内容转化为可读字符串

        :param filename: 需要解析的文件
        :param stream: 二进制流
        :param file_id: 文件标识id
        :return: 返回解析的文本内容，字符串类型
        :rtype: str
        """
        try:
            if filename:
                text, images, content_list = self._mineru266(file_path=filename)
            elif stream:
                text, images, content_list = self._mineru266(data_stream=stream)
            else:
                return None
            # return self._handle_mineru_data(content_list, file_id)
            return self._handle_mineru_data_test(content_list, file_id)
        except Exception as e:
            raise ValueError(f"标书PDF解析失败：{str(e)}")

    def _handle_mineru_data(self, content_list, file_id) -> HFiledocument:
        """
        处理mineru返回数据
        :param content_list:
        :return:
        """
        valid_page = sys.maxsize
        pattern = r'^(?:[（(]?[一二三四五六七八九十百千万]+[）)]?、?|[0-9]+[.)、]|[（(][0-9]+[）)]?)\s*(xxxxxxx)[^\d]*$'
        pattern2 = r'^(?:[（(]?[一二三四五六七八九十百千万]+[）)]?、?|[0-9]+[.)、]|[（(][0-9]+[）)]?)\s*(xxxxxxx)[^\d]*$'
        # pattern = r'^(?:（?[一二三四五六七八九]+十[一二三四五六七八九]+）?、?|[0-9]+[.)、]|（[0-9]+）)?\s*.*$'
        root_document: HFiledocument = None
        last_document: HFiledocument = root_document
        grouped = defaultdict(list)
        for content in content_list:
            grouped[content['page_idx']].append(content)
        for page_idx, item_list in grouped.items():
            text = ""
            for item in item_list:
                content_type = item["type"]
                content_text = ""
                content_text_level = item.get("text_level", 0)
                if content_type == "text":
                    if content_text_level == 1:
                        if re.match(pattern, item['text']):
                            valid_page = page_idx
                        if not re.match(pattern, item['text']) and re.match(pattern2, item['text']):
                            valid_page = sys.maxsize
                    else:
                        content_text += f"{item['text']}\n"
                if content_type == "list" and item["sub_type"] == "text":
                    for sub_item in item["list_items"]:
                        content_text += f"{sub_item}\n"
                text += content_text
            if page_idx >= valid_page:
                if text:
                    text = text.rstrip('\n\r')
                    if root_document:
                        next_doc = HFiledocument(file_id, page_idx + 1, text)
                        last_document.next = next_doc
                        last_document = next_doc
                    else:
                        root_document = HFiledocument(file_id, page_idx + 1, text)
                        last_document: HFiledocument = root_document
                # FileSaver.save_text(f"documents/{file_id}/{page_idx}.txt", text)
        return root_document


    def _handle_mineru_data_test(self, content_list, file_id) -> HFiledocument:
        """
        处理mineru返回数据
        :param content_list:
        :return:
        """
        root_document: HFiledocument = None
        last_document: HFiledocument = root_document
        grouped = defaultdict(list)
        for content in content_list:
            grouped[content['page_idx']].append(content)
        for page_idx, item_list in grouped.items():
            text = ""
            for item in item_list:
                content_type = item["type"]
                content_text = ""
                if content_type == "text":
                        content_text += f"{item['text']}\n"
                if content_type == "list" and item["sub_type"] == "text":
                    for sub_item in item["list_items"]:
                        content_text += f"{sub_item}\n"
                text += content_text
            if text:
                text = text.rstrip('\n\r')
                if root_document:
                    next_doc = HFiledocument(file_id, page_idx + 1, text)
                    last_document.next = next_doc
                    last_document = next_doc
                else:
                    root_document = HFiledocument(file_id, page_idx + 1, text)
                    last_document: HFiledocument = root_document
                # FileSaver.save_text(f"documents/{file_id}/{page_idx}.txt", text)
        return root_document

    def clean_text(self, text: str) -> str:
        """
        清除掉干扰的内容

        :param text: 需要清除前的文本内容
        :return: 返回清除后的文本内容
        :rtype: str
        """
        cleaned_text = self.remove_item(text)
        cleaned_text = self._remove_top(cleaned_text)
        return cleaned_text.strip()  # 去除首尾空白


