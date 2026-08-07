import asyncio
import datetime
import json
import re
from collections import defaultdict
from itertools import groupby
from typing import List

import requests

from apps import AppContext
from apps.algorithms.embedding import QwenEmbeddingVectorizer
from apps.document_parser.base import HFiledocument
from apps.document_parser.base_parser import HDocument
from apps.document_parser.markdown_parser import MarkDownParser
from apps.document_parser.pdf_parser import PdfParser
from apps.document_parser.pdf_parser_test import PdfParserTest
from apps.document_parser.text_parser import TextParser
from apps.service.milnus_service import create_tender_vector_milvus_db
from apps.service.tender_compliance_service import parser_document
from apps.splitting import overlapping_splitting



def text_parser():
    AppContext().init_context()
    file_path = "document/22.txt"
    text_parser = TextParser()
    texts = text_parser.parse(filename=file_path)
    pattern = r'<table.*?>.*?</table>'
    texts = re.sub(pattern, '', texts, flags=re.DOTALL)
    top_chunks = text_parser.topic_splitting(texts)
    chunks = text_parser.overlapping_splitting(texts,  70, 0)
    vectorizer = QwenEmbeddingVectorizer()
    milvus_vector_db = create_tender_vector_milvus_db(4096)
    file_id = 16
    file_ids = []
    pages = []
    start_indexes = []
    texts = []
    vec_list = []
    for chunk in top_chunks:
        print(f"[片段内容：{chunk}---------字符长度：{len(chunk)}]")
        vec = vectorizer.encode(chunk)
        vec_list.append(vec)
        file_ids.append(file_id)
        pages.append(0)
        start_indexes.append(0)
        texts.append(chunk)
    data_array = [file_ids, pages, start_indexes, texts, vec_list]
    milvus_vector_db.insert_info(data_array)


def pdf_parser():
    #AppContext().init_context()
    file_path = "D:/heiiyo/tender-similarity-check/tests/text/xxxxxxxxxxxxx.pdf"
    pdf_parser = PdfParser()
    file_document = pdf_parser.parse(filename=file_path, file_id=2026011106)
    #file_document: HFiledocument = pdf_parser.parse(filename=file_path, file_id=2026011106)
    print(file_document)
    #documents: list[HDocument] = pdf_parser.overlapping_splitting(file_document, 100, 0)
    # milvus_vector_db = create_tender_vector_milvus_db(4096)
    # milvus_vector_db.insert_data(documents)
    #for document in documents:
        #print(f"文件页数：{str(document.page)}，开始位置：{document.start_index}", f"文本内容：{document.text}")

def query_milvus_data():
    AppContext().init_context()
    milvus_vector_db = create_tender_vector_milvus_db(4096)
    milnvs_data_03 = milvus_vector_db.query_data("file_id == 3", ["file_id", "page", "start_index", "text_content", "vector"])
    vectorizer = QwenEmbeddingVectorizer()
    #print(milnvs_data_03)
    for item in milnvs_data_03:
        result = milvus_vector_db.search_similar("file_id == 4", [item["vector"]])
        for info in result:
            if info['similarity']>0.7:
                print(f"[源文本-页数-{item['page']}：{item['text_content']}\n对比文本-页数-{info['page']}:{info['text']}\n相似度:{info['similarity']}]\n\n")

def text_splite():
    file_path = "D:/pyproject/tender-similarity-check/document/xxxxxxxxxxxxxxxxxxxxxxx.pdf"
    pdf_parser = PdfParser()
    pdf_test = pdf_parser.parse(filename=file_path, file_id="2026011103")
    chunks = overlapping_splitting(pdf_test, 2000)   #100个字符拆分一个片段，重叠25个字符拆分
    print(f"片段数量：{chunks}")
    for chunk in chunks:
        print(f"[处理前片段：{chunk}---------字符长度：{len(chunk)}]")
        result_text = pdf_parser.preprocess_text(chunk)
        print(f"[处理后片段：{result_text}---------字符长度：{len(result_text)}]")
        #get_embedding(chunk)


def md_parser_test():
    file_path = "D:/heiiyo/tender-similarity-check/tests/text/09155bc54b404beaa291798d72f150fd.pdf"
    md_parser = MarkDownParser()
    doc: HFiledocument = md_parser.parse(filename=file_path, file_id=202603111147)
    if doc:
        chunks: List[HDocument] = md_parser.overlapping_splitting(doc, 100, 0)
        # 必须先用 topic 排序
        sorted_chunks = sorted(chunks, key=lambda x: x.topic)
        # 分组
        grouped = {
            topic: list(group)
            for topic, group in groupby(sorted_chunks, key=lambda x: x.topic)
        }
    print("")


# 调用接口处理PDF文件
def mineru266(file_path=None, data_stream=None):
    text = ""
    mineru_config = AppContext().mineru_config
    url = mineru_config['nodes'][0]['url']
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

def test_parser_document():
    AppContext().init_context()
    documents = parser_document(1236)
    assert len(documents) == 383
