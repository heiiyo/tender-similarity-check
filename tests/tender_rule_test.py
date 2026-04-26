import asyncio
import datetime
import time

import pytest
from sqlalchemy import text

from apps import AppContext, ConcurrencyManager
from apps.algorithms.embedding import QwenEmbeddingVectorizer
from apps.document_parser.markdown_parser import MarkDownParser
from apps.model_action.vllm_service import handel_compliance_check
from apps.service.milnus_service import create_tender_topic_vector_milvus_db, create_rm_text_vector_milvus_db, \
    create_main_topic_vector_milvus_db
from apps.service.tender_compliance_service import parser_tender_topic, parser_document, insert_into_milvus, \
    compliance_validation
from apps.service.tender_service import TenderFile, CheckTask

from logger_config import get_logger

logger = get_logger(name=__package__)

tender_file_id = 15562


@pytest.fixture
def content():
    return AppContext().init_context()


def test_pdf_into_images(content: AppContext):
    md_parser = MarkDownParser()
    print(f"开始执行:{datetime.datetime.now()}")
    asyncio.run(md_parser.to_images(tender_file_id=tender_file_id))
    # ids = await md_parser.to_images(file_path=file_path2)
    assert 396 == len(md_parser.image_ids)
    print(f"执行完成:{md_parser.image_ids}")


def test_pdf_parse(content: AppContext):
    asyncio.run(compliance_validation(tender_file_id))


def test_topic_insert_vec(content: AppContext):
    # result = asyncio.run(parser_tender_topic(tender_file_id))
    # print(f"topic:{result}")
    print(f"解析标书")
    documents = parser_document(tender_file_id)
    print(f"解析完成")
    # data_list = insert_into_milvus(tender_file_id, result, documents)

    # logger.info(data_list)


def test_and_main_topic(content: AppContext):
    embedding = QwenEmbeddingVectorizer()
    text_content = [
        '技术文件',
        '技术方案',
        '项目实施方案',
        '投标设备技术性能指标',
        '投标设备技术性能指标的详细描述',
        '实施方案',
        '解决方案',
        '详细技术参数响应表',
        '项目实施进度计划',
        '总体技术方案',
        '项目组织机构与人员配置',
        '质量安全管理体系',
        '风险管理与应急预案',
        '技术优势与创新点',
    ]
    # emds = embedding.encode_group(text_content)
    rm_text_vector_milvus_db = create_main_topic_vector_milvus_db(embedding.get_vector_dim())
    # rm_text_vector_milvus_db.insert_info([text_content, emds])
    emds = embedding.encode_group(["技术文件"])
    result = rm_text_vector_milvus_db.search_similar("", emds, ['topic'], 1)
    print(f"结果:{result}")



def test_topic(content: AppContext):
    # result = asyncio.run(parser_tender_topic(tender_file_id))
    # logger.info(result)
    embedding = QwenEmbeddingVectorizer()
    text_content = [
        '出厂编号',
        '产口编号',
        '技术文件',
    ]
    emds = embedding.encode_group(text_content)
    rm_text_vector_milvus_db = create_rm_text_vector_milvus_db(embedding.get_vector_dim())
    rm_text_vector_milvus_db.insert_info([text_content, emds])


def chunk_generator(data, size):
    for i in range(0, len(data), size):
        yield data[i:i + size]


async def main_task(asyncio_task_list, semaphore):
    print(f"任务数量：{len(asyncio_task_list)}")
    # 这里所有任务和信号量都运行在当前这个 asyncio.run 创建的循环内
    return await asyncio.gather(*[t(semaphore) for t in asyncio_task_list])


def test_handel_compliance_check(content: AppContext):

    # 【关键修复】检查并强制将 Semaphore 绑定到即将由 asyncio.run 创建的新循环上下文
    # 虽然不能在外部显式绑定，但可以通过创建一个临时 wrapper 来隔离
    async def safe_execute(func, *args, **kwargs):
        # 在这个局部作用域创建一个全新的 Semaphore，确保它与 asyncio.run 的 Loop 一致
        return await func(*args, **kwargs)

    def get_wrapper(image_url_list, remake):
        """返回一个接受 signal 参数的 async 函数"""

        async def wrapped_call(semaphore):
            async with semaphore:
                return await safe_execute(handel_compliance_check, image_url_list, remake)
        return wrapped_call

    with content.db_session_factory() as session:
        stmt = text("""
            SELECT 
                d.file_path
            FROM 
                tender_pdf_image_entity t
            LEFT JOIN 
                file_record d ON t.file_id = d.id 
            WHERE 
                t.page_number >= :start_page 
                AND t.page_number <= :end_page 
                AND t.tender_file_id = :tender_id
            ORDER BY 
                t.page_number ASC
        """)

        result = session.execute(stmt, {"start_page": 23, "end_page": 104, "tender_id": 19060})
        rows = result.fetchall()
    # 使用示例
    # 创建信号量，限制最大并发数为 5
    asyncio_task = []
    for group in chunk_generator(rows[0: 10], 1):
        image_url_list = []
        for item in group:
            image_url_list.append({
                "url": f"http://127.0.0.1:30009/tender/{item[0]}"
            })
        asyncio_task.append(get_wrapper(image_url_list, """
                                                        1. 检测触发条件
                                                        以文档内容是否含有关键字段 “法定代表人或其委托代理人” 作为是否需要进行签字检测的唯一依据。
                                                        2. 判定逻辑
                                                        无需检测：若全文未匹配到上述关键字，判断为无需检测。
                                                        合规：若已匹配到关键字，且对应位置已完成签字或盖有法人章，判定为合规。
                                                        不合规：若已匹配到关键字，但对应位置缺失签字且未识别出法人章，判定为不合规。
                                                        3. 注意事项
                                                        公司章与法人章含义不同
                                                        """))

    async def entry_point():
        # ✅ 在这个新的 loop 上下文中创建信号量
        local_semaphore = asyncio.Semaphore(4)
        return await main_task(asyncio_task, local_semaphore)
    # 转换为字符串格式 (例如：2026-04-15 10:30:45)
    now = datetime.datetime.now()
    formatted_time = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"开始时间：{formatted_time}")
    start = time.perf_counter()  # 高精度计时
    asyncio.run(entry_point())
    end = time.perf_counter()
    now_end = datetime.datetime.now()
    formatted_time_end = now_end.strftime("%Y-%m-%d %H:%M:%S")
    print(f"结束时间：{formatted_time_end}")
    print(f"耗时：{end - start:.6f} 秒")


def test_summarize_answer(content: AppContext):
    result = asyncio.run(parser_tender_topic(tender_file_id))
