import re
from apps.document_parser.base_parser import BaseParser


class TextParser(BaseParser):
    def parse(self, filename=None, stream=None, file_id=None) -> str:
        # 指定编码格式（如 GBK、Latin-1）
        with open(filename, 'r', encoding='utf-8') as file:
             content = file.read()
        return content

    def topic_splitting(self, text: str):
        text_chunks = text.split('\n')
        result = []
        for chunk in text_chunks:
            if chunk and len(chunk) > 0:
                pattern = r'<table.*?>.*?</table>'
                chunk_a = re.sub(pattern, '', chunk, flags=re.DOTALL)
                result.append(chunk_a)
        return result

    def overlapping_splitting(self, text, chunk_size: int = 50, overlap: int = 10):
        """
        重叠切片逻辑，将长文本内容切割成不同的小段，选择重叠切片，真强语义的连贯性

        :param text: 需要切片的文本内容
        :type text: str
        :param chunk_size: 切片大小
        :type chunk_size: int
        :param overlap: 重叠部分的长度
        :type overlap: int
        :return: 返回字符串数组，为切好的多片段数据
        :rtype: list[str]
        """
        texts = []
        punctuations: str = r'，  。！？；… \n'
        text = re.sub(r'\s+', ' ', text).strip()
        text_length = len(text)
        current_start = 0
        if text_length <= chunk_size:
            texts.append(text[current_start:])
        # 编译正则：匹配任意结束标点（用于快速查找）
        punctuation_pattern = re.compile(f'[{punctuations}]')
        chunks = []

        while current_start < text_length:
            # 1. 计算目标结束位置（当前起始 + 目标长度）
            target_end = current_start + chunk_size

            # 2. 处理边界：如果目标结束超过文本长度，直接取剩余部分
            if target_end >= text_length:
                texts.append(text[current_start:])
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
            texts.append(current_chunk)
            # 6. 更新下一块的起始位置（当前结束 - 重叠长度）
            current_start = split_end - overlap

            # 防护：避免起始位置回退过多（比如重叠长度大于当前块）
            if current_start < 0:
                current_start = 0
            # 防护：避免死循环（相邻起始位置无变化）
            if current_start >= text_length or (len(chunks) >= 2 and current_start == chunks[-2]):
                break

        return texts

