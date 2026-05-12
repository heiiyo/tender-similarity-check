import asyncio
import datetime
import time

import pytest
from sqlalchemy import text

from apps import AppContext, ConcurrencyManager
from apps.algorithms.embedding import QwenEmbeddingVectorizer
from apps.document_parser.markdown_parser import MarkDownParser
from apps.model_action.vllm_service import handel_compliance_check, handle_rule
from apps.repository.entity.tender_entity import TenderRuleConfiguration
from apps.service.milnus_service import create_tender_topic_vector_milvus_db, create_rm_text_vector_milvus_db, \
    create_main_topic_vector_milvus_db
from apps.service.tender_compliance_service import parser_tender_topic, parser_document, insert_into_milvus, \
    compliance_validation
from apps.service.tender_service import TenderFile, CheckTask

from logger_config import get_logger

logger = get_logger(name=__package__)

tender_file_id = 1


@pytest.fixture
def content():
    return AppContext().init_context()


def test_pdf_into_images(content: AppContext):
    md_parser = MarkDownParser()
    print(f"开始执行:{datetime.datetime.now()}")
    asyncio.run(md_parser.to_images(tender_file_id=tender_file_id))
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


@pytest.mark.asyncio
async def test_handle_rule_basic(content: AppContext):
    """
    测试 handle_rule 函数的基本功能
    验证规则执行、结果返回和数据库写入
    """
    # 准备测试数据
    test_tender_file_id = 1
    test_sub_compliance_task_id = None
    test_bid_plagiarism_task_id = None
    
    # 从数据库获取一个已启用的规则
    with content.db_session_factory() as session:
        rule = session.query(TenderRuleConfiguration).filter(
            TenderRuleConfiguration.status == 1
        ).first()
        
        if not rule:
            pytest.skip("没有可用的测试规则")
        
        logger.info(f"使用测试规则: id={rule.id}, name={rule.rule_name}, skill={rule.skill_name}")
        
        # 创建子任务用于测试
        from apps.repository.entity.tender_entity import SubComplianceCheckTask, BidPlagiarismCheckTask
        
        # 创建主任务
        main_task = BidPlagiarismCheckTask(
            check_type=1,
            task_name="测试任务",
            file_name_list="测试文件",
            file_id_list="1",
            tender_reference_file_id=None,
            task_type=rule.rule_type
        )
        session.add(main_task)
        session.flush()
        test_bid_plagiarism_task_id = main_task.id
        
        # 创建子任务
        sub_task = SubComplianceCheckTask(
            bid_plagiarism_check_task_id=test_bid_plagiarism_task_id,
            tender_file_id=test_tender_file_id,
            tender_file_name="测试标书"
        )
        session.add(sub_task)
        session.flush()
        test_sub_compliance_task_id = sub_task.id
        session.commit()
    
    try:
        # 执行 handle_rule
        logger.info(f"开始执行 handle_rule，规则ID: {rule.id}")
        result = await handle_rule(
            rule=rule,
            tender_file_id=test_tender_file_id,
            sub_compliance_check_task_id=test_sub_compliance_task_id,
            bid_plagiarism_check_task_id=test_bid_plagiarism_task_id
        )
        
        # 验证返回结果
        assert result is not None, "handle_rule 应该返回结果"
        logger.info(f"handle_rule 执行成功，返回结果类型: {type(result).__name__}")
        
        # 验证数据库中是否写入了风险记录
        with content.db_session_factory() as session:
            from apps.repository.entity.tender_entity import TenderComplianceRiskRecord
            
            risk_records = session.query(TenderComplianceRiskRecord).filter(
                TenderComplianceRiskRecord.sub_compliance_check_task_id == test_sub_compliance_task_id,
                TenderComplianceRiskRecord.rule_id == rule.id
            ).all()
            
            logger.info(f"查询到 {len(risk_records)} 条风险记录")
            assert len(risk_records) > 0, "应该有至少一条风险记录"
            
            # 验证记录字段
            for record in risk_records:
                assert record.tender_file_id == test_tender_file_id
                assert record.rule_id == rule.id
                assert record.bid_plagiarism_check_task_id == test_bid_plagiarism_task_id
                assert record.check_basis is not None
                logger.info(f"记录验证通过: is_compliant={record.is_compliant}, page={record.page_number}")
    
    finally:
        # 清理测试数据
        with content.db_session_factory() as session:
            # 删除风险记录
            session.query(TenderComplianceRiskRecord).filter(
                TenderComplianceRiskRecord.sub_compliance_check_task_id == test_sub_compliance_task_id
            ).delete()
            
            # 删除子任务
            session.query(SubComplianceCheckTask).filter(
                SubComplianceCheckTask.id == test_sub_compliance_task_id
            ).delete()
            
            # 删除主任务
            session.query(BidPlagiarismCheckTask).filter(
                BidPlagiarismCheckTask.id == test_bid_plagiarism_task_id
            ).delete()
            
            session.commit()
            logger.info("测试数据清理完成")


@pytest.mark.asyncio
async def test_handle_rule_with_invalid_skill(content: AppContext):
    """
    测试 handle_rule 在技能名称无效时的行为
    """
    test_tender_file_id = 1
    test_sub_compliance_task_id = 1
    test_bid_plagiarism_task_id = 1
    
    # 创建一个无效的规则
    invalid_rule = None
    with content.db_session_factory() as session:
        invalid_rule = session.get(TenderRuleConfiguration, 4)
    
    if not invalid_rule:
        pytest.skip("未找到测试用的规则 ID=4")

    logger.info("开始测试无效技能的处理")

    # 直接 await 确保协程完全执行
    try:
        result = await handle_rule(
            rule=invalid_rule,
            tender_file_id=test_tender_file_id,
            sub_compliance_check_task_id=test_sub_compliance_task_id,
            bid_plagiarism_check_task_id=test_bid_plagiarism_task_id
        )
        # 验证结果
        assert result is not None, "handle_rule 应该返回结果"
        logger.info(f"handle_rule 执行完成，返回结果类型: {type(result).__name__}")
        
        # 验证数据库中是否写入了风险记录
        with content.db_session_factory() as session:
            from apps.repository.entity.tender_entity import TenderComplianceRiskRecord
            
            risk_records = session.query(TenderComplianceRiskRecord).filter(
                TenderComplianceRiskRecord.sub_compliance_check_task_id == test_sub_compliance_task_id,
                TenderComplianceRiskRecord.rule_id == invalid_rule.id
            ).all()
            
            logger.info(f"查询到 {len(risk_records)} 条风险记录")
            assert len(risk_records) > 0, "应该有至少一条风险记录"
    
    except Exception as e:
        logger.error(f"测试中捕获到异常: {type(e).__name__}: {str(e)}")
        raise


def test_handle_rule_parameter_validation(content: AppContext):
    """
    测试 handle_rule 参数验证
    """
    with content.db_session_factory() as session:
        rule = session.query(TenderRuleConfiguration).filter(
            TenderRuleConfiguration.status == 1
        ).first()
        
        if not rule:
            pytest.skip("没有可用的测试规则")
        
        # 验证规则对象的关键属性
        assert rule.id is not None, "规则ID不能为空"
        assert rule.skill_name is not None and len(rule.skill_name) > 0, "技能名称不能为空"
        assert rule.rule_name is not None and len(rule.rule_name) > 0, "规则名称不能为空"
        
        logger.info(f"参数验证通过: rule_id={rule.id}, skill_name={rule.skill_name}")
