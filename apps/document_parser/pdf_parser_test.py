import re
import sys

import fitz
from pymupdf import Document

from apps.document_parser.base import HFiledocument
from apps.document_parser.base_parser import BaseParser


class PdfParserTest(BaseParser):

    def __init__(self):
        
        # 1. 标书页码正则（覆盖标书常见样式）
        self.page_num_pattern = re.compile(
            r'^\s*'
            r'('
            # 基础页码：1、- 5 -、Page 8、第9页、-第10页-
            r'(\d+)|([-/|_]\s*\d+\s*[-/|_])|(page\s*\d+)|(\d+\s*page)|'
            r'(第?\s*\d+\s*页?)|([-/|_]\s*第?\s*\d+\s*页?\s*[-/|_])|'
            # 标书混合样式：包含项目名/章节名+页码（匹配数字核心）
            r'.*(\d+).*(页|页码|Page|pg).*'
            r')'
            r'\s*$',
            re.IGNORECASE
        )
        
        # 2. 标书页眉页脚特征词（可根据实际标书补充）
        self.header_footer_keywords = [
            "招标文件", "投标文件", "项目名称", "章节", "技术要求", 
            "商务部分", "页码", "Page", "日期", "公司名称"
        ]
    
    def _is_header_footer(self, page: fitz.Page, text: str, bbox: fitz.Rect) -> bool:
        """
        判断文本块是否是标书的页眉/页脚/页码
        核心逻辑：位置（上下15%） + 文本特征（短文本+关键词/页码）
        """
        page_rect = page.rect
        # 标书页眉页脚区域：上下15%
        top_margin = page_rect.height * 0.15
        bottom_margin = page_rect.height * 0.85
        text_mid_y = (bbox.y0 + bbox.y1) / 2

        # 条件1：文本在上下15%区域
        if not (text_mid_y < top_margin or text_mid_y > bottom_margin):
            return False
        
        # 条件2：文本是短文本块（标书页眉页脚通常<30字符）
        text_stripped = text.strip()
        if len(text_stripped) > 30:
            return False
        
        # 条件3：包含页码特征 或 标书页眉页脚关键词
        has_page_num = bool(self.page_num_pattern.match(text_stripped))
        has_keyword = any(keyword in text_stripped for keyword in self.header_footer_keywords)
        
        return has_page_num or has_keyword

    def excel_handle(self, page):
        """
        pdf中的处理表格
        :param page: pdf某一个对象
        :return:
        """
        blocks = page.get_text("blocks")
        cdrawings = page.get_cdrawings()
        left_point = (sys.maxsize, sys.maxsize)
        right_point = (0, 0)
        # 计算出表格的边界
        for cdrawing in cdrawings:
            left_x, left_y, right_x, right_y = cdrawing["rect"]
            left_x_mix, left_y_mix = left_point
            right_x_max, right_y_max = right_point
            if left_x_mix > left_x:
                left_x_mix = left_x
            if left_y_mix > left_y:
                left_y_mix = left_y
            left_point = (left_x_mix, left_y_mix)

            if right_x_max < right_x:
                right_x_max = right_x
            if right_y_max < right_y:
                right_y_max = right_y
            right_point = (right_x_max, right_y_max)

        left_x_mix, left_y_mix = left_point
        right_x_max, right_y_max = right_point
        result = []
        for block in blocks:
            left_point_x,  left_point_y, right_point_x,  right_point_y, text, index, a = block
            if left_point_x > left_x_mix and left_point_y > left_y_mix and right_point_x < right_x_max and right_point_y < right_y_max:
                continue
            else:
                result.append(block)
        return result


    def parse_tender(self, filename=None, stream=None):
        """
        简单标书纯文本解析， 不需要过滤信息
        :param filename: 需要解析的文件，使用路径
        :param stream: 数据流（可选）,如果要解析的是二进制流则使用该参数
        :return:
        """
        try:
            doc: Document = fitz.open(filename=filename, filetype="pdf", stream=stream)
            text_all = ""
            for page_num, page in enumerate(doc):
                text: str = page.get_text().strip()
                if text:
                    # 清理当前页空行，避免冗余
                    text = re.sub(r'\n+', '\n', text).strip()
                    text = self.remove_item(text)
                    text_all += text
            return text_all
        except Exception:
            return ""



    def parse(self, filename=None, stream=None, file_id = None) -> HFiledocument:
        """
        文档解析器功能，将文件中的内容转化为可读字符串
        :param filename: 需要解析的文件，使用路径
        :param stream: 数据流（可选）,如果要解析的是二进制流则使用该参数
        :param file_id: 文件在数据库表中的id
        :return: 返回解析的文本内容，字符串类型
        :rtype: str
        """ 
        try:
            doc: Document = fitz.open(filename=filename, filetype="pdf", stream=stream)
            file_document = None
            top = None
            valid_page = 0
            for page_num, page in enumerate(doc):
                page_num = page_num + 1
                # 按文本块提取（保留位置信息）
                page: fitz.Page = page

                text: str = page.get_text().strip()
                if text:
                    page_clean_text = ""
                    # 表格处理， 移除表格的内容
                    text_blocks = self.excel_handle(page)
                    for block in text_blocks:
                        block_text = block[4].strip()
                        block_bbox = fitz.Rect(block[:4])

                        # 过滤页眉/页脚/页码
                        if not self._is_header_footer(page, block_text, block_bbox):
                            page_clean_text += block_text + "\n"

                    # 清理当前页空行，避免冗余
                    page_clean_text = re.sub(r'\n+', '\n', page_clean_text).strip()
                    page_clean_text = self.remove_item(page_clean_text)
                    # 十、项目实施方案
                    # 十一、业绩要求证明材料
                    # if "十、项目实施方案" in page_clean_text:
                    #     valid_page = page_num
                    # if "十一、业绩要求证明材料" in page_clean_text:
                    #     valid_page = sys.maxsize
                    if page_num >= valid_page:
                        if file_document:
                            current = HFiledocument(file_id, page_num, page_clean_text)
                            current_parent = file_document
                            current_parent.next = current
                            file_document = current
                        else:
                            file_document = HFiledocument(file_id, page_num, page_clean_text)
                            top = file_document

                else:
                    # 扫描件处理
                    pass
                #full_clean_text += page_clean_text + "\n\n"

            # 最终清理：移除多余空行，返回纯文本
            #full_clean_text = re.sub(r'\n{3,}', '\n\n', full_clean_text).strip()

            return top

        except Exception as e:
            raise ValueError(f"标书PDF解析失败：{str(e)}")