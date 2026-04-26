import asyncio
import json
import re
from io import BytesIO
from typing import List

from fastapi import BackgroundTasks
from sqlalchemy.sql.operators import and_

from apps import AppContext
from apps.algorithms.embedding import QwenEmbeddingVectorizer
from apps.document_parser.base import HFiledocument, HDocument
from apps.document_parser.markdown_parser import MarkDownParser
from apps.model_action.tender_model_vo import TenderTopicInfo
from apps.model_action.vllm_service import handle_rule, handel_topic
from apps.repository.entity.file_entity import FileRecordEntity
from apps.repository.entity.tender_entity import TenderPDFImageEntity, TenderTopic, TenderRuleConfiguration, \
    SubComplianceCheckTask, BidPlagiarismCheckTask, TenderComplianceRiskRecord
from apps.repository.minio_repository import get_file_url_http, get_file_url
from apps.service.milnus_service import create_tender_topic_vector_milvus_db, create_tender_vector_milvus_db
from apps.web.dto.compliance_dto import TenderComplianceDTO, ComplianceRulesConditionDTO, ComplianceInfoConditionDto
from apps.web.dto.tender_task import BasePageDto, TenderTaskDto
from apps.web.vo.compliance_respose import ComplianceRulesPage, ComplianceRulesVO, ComplianceInfoPage, \
    TenderComplianceInfoVO, ComplianceInfoVO
from apps.web.vo.similarity_respose import TenderTaskPage, FileRecordVO

from logger_config import get_logger

logger = get_logger(name=__package__)
app_context = AppContext()


def calculate_pages_int(total, per_page=10):
    """
    计算页数
    :param total:
    :param per_page:
    :return:
    """
    if total == 0:
        return 0
    return (total + per_page - 1) // per_page

def add_compliance_rule(tender_compliance: TenderComplianceDTO):
    """
    添加合规规则
    :param tender_compliance: 规则信息
    :return:
    """
    # 获取所有已启动的合规规则库
    with app_context.db_session_factory() as session:
        session.add(TenderRuleConfiguration(
            name=tender_compliance.rule_name,
            remake=tender_compliance.rule_description,
            topic=tender_compliance.rule_topic,
            skill=tender_compliance.md,
            status=tender_compliance.status
        ))
        session.commit()


def update_compliance_rule_info(tender_compliance: TenderComplianceDTO):
    rule_id = None
    with app_context.db_session_factory() as session:
        rule: TenderRuleConfiguration = session.get(TenderRuleConfiguration, tender_compliance.id)
        if tender_compliance.rule_name:
            rule.name = tender_compliance.rule_name
        if tender_compliance.rule_description:
            rule.remake = tender_compliance.rule_description
        if tender_compliance.rule_topic:
            rule.topic = tender_compliance.rule_topic
        if tender_compliance.md:
            rule.skill = tender_compliance.md
        rule.status = tender_compliance.status
        session.add(rule)
        session.commit()
        rule_id = rule.id
    return rule_id


def query_compliance_rules_list(rules_condition_dto: ComplianceRulesConditionDTO):
    page = rules_condition_dto.page_offset  # 当前页码（从 1 开始）
    per_page = rules_condition_dto.page_size  # 每页记录数
    # 计算偏移量
    offset = (page - 1) * per_page
    condition_array = []
    result_data = []
    # 筛选任务类型
    if rules_condition_dto.rule_name:
        condition_array.append(TenderRuleConfiguration.name == rules_condition_dto.rule_name)
    with app_context.db_session_factory() as session:
        if condition_array and len(condition_array) == 1:
            rules = session.query(TenderRuleConfiguration).filter(*condition_array).offset(offset).limit(
                per_page).all()
            count = session.query(TenderRuleConfiguration).filter(*condition_array).count()
        else:
            rules = session.query(TenderRuleConfiguration).offset(offset).limit(
                per_page).all()
            count = session.query(TenderRuleConfiguration).count()
        for rule in rules:
            result_data.append(
                ComplianceRulesVO(id=rule.id, rule_name=rule.name,
                              rule_description=rule.remake, status=rule.status))
    page = ComplianceRulesPage(
        page_offset=rules_condition_dto.page_offset,
        page_size=len(result_data),
        page_num=calculate_pages_int(count, per_page),
        total=count,
        data=result_data
    )
    return page


def create_compliance_check_task(tender_task_dto: TenderTaskDto, background_tasks: BackgroundTasks):
    task_id = None
    if tender_task_dto.file_ids and len(tender_task_dto.file_ids) > 0:
        with app_context.db_session_factory() as session:
            file_record_list = session.query(FileRecordEntity).filter(
                FileRecordEntity.id.in_(tender_task_dto.file_ids)).all()
            file_name_list = [file_record.file_name for file_record in file_record_list]
            file_id_list = [file_record.id for file_record in file_record_list]
            task = BidPlagiarismCheckTask(
                check_type=tender_task_dto.task_type,
                task_name=tender_task_dto.task_name,
                file_name_list=",".join(file_name_list),
                file_id_list=','.join(map(str, file_id_list)),
                tender_reference_file_id=tender_task_dto.tender_reference_id
            )
            session.add(task)
            session.commit()
            task_id = task.id
        for tender_file_id in tender_task_dto.file_ids:
            background_tasks.add_task(compliance_background_task, tender_file_id, task_id)
    return task_id


def compliance_background_task(tender_file_id, task_id):
    # try:
    with app_context.db_session_factory() as session:
        file_record = session.get(FileRecordEntity, tender_file_id)
        if not file_record:
            return
        sub_compliance = SubComplianceCheckTask(
            bid_plagiarism_check_task_id=task_id,
            tender_file_id=tender_file_id,
            tender_file_name=file_record.file_name
        )
        session.add(sub_compliance)
        session.commit()
        sub_compliance_id = sub_compliance.id
    # 执行合规分析
    asyncio.run(compliance_validation(tender_file_id))
    # 更新任务状态，以及风险数量
    with app_context.db_session_factory() as session:
        if sub_compliance_id:
            sub_compliance_old: SubComplianceCheckTask = session.get(SubComplianceCheckTask, sub_compliance_id)
            sub_compliance_old.process_status = "completed"
            risk_number = session.query(TenderComplianceRiskRecord)\
                .filter(and_(TenderComplianceRiskRecord.sub_compliance_check_task_id == sub_compliance_id,
                             TenderComplianceRiskRecord.status == 1)
                ).count()
            sub_compliance_old.risk_number = risk_number
            session.add(sub_compliance_old)
            session.commit()
    # except Exception as e:
    #     with app_context.db_session_factory() as session:
    #         if sub_compliance_id:
    #             sub_compliance_old: SubComplianceCheckTask = session.get(SubComplianceCheckTask, sub_compliance_id)
    #             sub_compliance_old.process_status = "failed"
    #             session.add(sub_compliance_old)
    #             session.commit()


def query_tender_compliance_list(task_id, page_dto: BasePageDto):
    page = page_dto.page_offset  # 当前页码（从 1 开始）
    per_page = page_dto.page_size  # 每页记录数
    # 计算偏移量
    offset = (page - 1) * per_page
    with app_context.db_session_factory() as session:
        tasks = session.query(SubComplianceCheckTask).filter(
            SubComplianceCheckTask.bid_plagiarism_check_task_id == task_id).offset(offset).limit(per_page).all()
        count = session.query(SubComplianceCheckTask).filter(
            SubComplianceCheckTask.bid_plagiarism_check_task_id == task_id).count()
        task_data = [{
            "id": task.id,
            "file_id": task.tender_file_id,
            "file_name": task.tender_file_name,
            "risk_number": task.risk_number,
            "process_status": task.process_status} for task in tasks]
    tender_task_page = TenderTaskPage(
        page_offset=page,
        page_size=len(task_data),
        page_num=calculate_pages_int(count, per_page),
        total=count,
        data=task_data
    )
    return tender_task_page


def query_tender_compliance_info(compliance_info_condition: ComplianceInfoConditionDto):
    page = compliance_info_condition.page_offset  # 当前页码（从 1 开始）
    per_page = compliance_info_condition.page_size  # 每页记录数
    # 计算偏移量
    offset = (page - 1) * per_page
    compliance_info_data = []
    with app_context.db_session_factory() as session:
        record_list = session.query(TenderComplianceRiskRecord).filter(
            TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id).offset(offset).limit(per_page).all()
        count = session.query(TenderComplianceRiskRecord).filter(
            TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id).count()
        risk_number = session.query(TenderComplianceRiskRecord)\
            .filter(and_(TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id, TenderComplianceRiskRecord.is_risk == 1))\
            .count()
        passed_number = session.query(TenderComplianceRiskRecord)\
            .filter(and_(TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id, TenderComplianceRiskRecord.is_risk == 0))\
            .count()
        sub_task_list = session.query(SubComplianceCheckTask).filter(
            SubComplianceCheckTask.tender_file_id == compliance_info_condition.tender_id).all()
        file_record_top: FileRecordEntity = session.get(FileRecordEntity, compliance_info_condition.tender_id)
        file_record_list = []
        for sub_task in sub_task_list:
            file_record_entity: FileRecordEntity = session.get(FileRecordEntity, sub_task.tender_file_id)
            file_record = FileRecordVO(id=file_record_entity.id, file_name=file_record_entity.file_name,
                                       file_url=get_file_url(file_record_entity.file_path))
            file_record_list.append(file_record)
        for record in record_list:
            compliance_info = ComplianceInfoVO(info_id=record.id,
                                            info_description=record.risk_description,
                                            file_page_number=record.tender_page,
                                            info_type=1-record.is_risk)
            compliance_info_data.append(compliance_info)
    com_page = ComplianceInfoPage(data=compliance_info_data, page_size=len(record_list), page_num=calculate_pages_int(count, per_page),
                                  page_offset=compliance_info_condition.page_offset, total=count)
    page = TenderComplianceInfoVO(data=com_page,
                                  tender_id=file_record_top.id,
                                  tender_name=file_record_top.file_name,
                                  tender_url=get_file_url(file_record_top.file_path),
                                  risk_number=risk_number,
                                  passed_number=passed_number,
                                  tender_list=file_record_list)
    return page


async def compliance_validation(tender_file_id):
    # 标书处理分析，将标书每一页转化为相应的图片
    md_parser = MarkDownParser()
    with app_context.db_session_factory() as session:
        images = session.query(TenderPDFImageEntity).filter(TenderPDFImageEntity.tender_file_id == tender_file_id).all()
    if not images or len(images) < 1:
        await md_parser.to_images(tender_file_id=tender_file_id)
    # 根据获取标书中的一级目录
    with app_context.db_session_factory() as session:
        tender_topic_list = session.query(TenderTopic).filter(TenderTopic.tender_file_id == tender_file_id).all()
    if not tender_topic_list or len(tender_topic_list) < 1:
        result = await parser_tender_topic(tender_file_id)
        documents = parser_document(tender_file_id)
        topic_list = insert_into_milvus(tender_file_id, result, documents)
    else:
        topic_list = [{"topic_content": topic_info.topic_name, "start_page": topic_info.start_page,
                       "end_page": topic_info.end_page, "tender_file_id": tender_file_id} for topic_info in tender_topic_list]
    # 获取所有已启动的合规规则库
    with app_context.db_session_factory() as session:
        rule_list = session.query(TenderRuleConfiguration).filter(TenderRuleConfiguration.status == 1).all()
    # 根据规则库匹配到对应的一级目录，以及对应的那几页（也就是对应的图片）
    topic_list_d = []
    for topic in topic_list:
        topic_list_d.append(json.loads(TenderTopicInfo(
            tender_file_id=tender_file_id,
            tender_topic_name=topic['topic_content'],
            start_page=topic['start_page'],
            end_page=topic['end_page']
        ).to_json()))
    asyncio_task = []
    if rule_list:
        for rule in rule_list:
            asyncio_task.append(handle_rule(rule, topic_list_d))
    await asyncio.gather(*asyncio_task)


async def parser_tender_topic(tender_file_id):
    with app_context.db_session_factory() as session:
        # 获取标书前五页图片数据
        tender_pdf_image_list = session.query(TenderPDFImageEntity)\
            .filter(and_(TenderPDFImageEntity.tender_file_id == tender_file_id, and_(TenderPDFImageEntity.page_number > 1, TenderPDFImageEntity.page_number < 8)))\
            .order_by(TenderPDFImageEntity.page_number.asc()).all()
        image_file_list = [image.file_id for image in tender_pdf_image_list]
        url_list = []
        for image_id in image_file_list:
            file_item: FileRecordEntity = session.get(FileRecordEntity, image_id)
            image_url = get_file_url_http(file_item.file_path)
            url_list.append({'url': image_url})
        return await handel_topic(url_list)


def parser_document(tender_file_id):
    logger.info(f"解析标书-{tender_file_id}开始")
    with app_context.db_session_factory() as session:
        file_record = session.get(FileRecordEntity, tender_file_id)
        file_path = file_record.file_path
        business_id = file_record.business_id
        minio_client = app_context.minio_client
        with minio_client.get_object(business_id, file_path) as response:
            file_data = response.read()  # 自动 close + release_conn
        pdf_stream = BytesIO(file_data)
        md_parser = MarkDownParser()
        documents = md_parser.parse(stream=pdf_stream, file_id=tender_file_id)
    logger.info(f"解析标书-{tender_file_id}结束")
    return documents


def insert_into_milvus(tender_file_id, topics, documents: HFiledocument):
    md_parser = MarkDownParser()
    logger.info(f"标书-{tender_file_id}切片开始")
    chunk_list: List[HDocument] = md_parser.overlapping_splitting(documents)
    logger.info(f"标书-{tender_file_id}切片结束")
    topics_com = list(zip(topics, topics[1:]))
    data_list = []
    prefix_pattern = r'(?:[（(]?[一二三四五六七八九十百千万]+[）)]?、?|[0-9]+[.)、]|[（(][0-9]+[）)]?)'
    for topic_com in topics_com:
        topic_start, topic_end = topic_com

        # 1. 安全转义关键词
        safe_keyword_start = re.escape(topic_start)
        safe_keyword_end = re.escape(topic_end)

        pattern = rf'^(({prefix_pattern}\s*{safe_keyword_start})(?!.*\d$).*)$'
        pattern2 = rf'^(({prefix_pattern}\s*{safe_keyword_end})(?!.*\d$).*)$'
        start_page = None
        end_page = None
        for document in documents:
            if document.page_content:
                result_list = document.page_content.split('\n')
                if re.match(pattern, result_list[0]):
                    start_page = document.page
                if re.match(pattern2, result_list[0]):
                    end_page = document.page
                if start_page and end_page and end_page > start_page:
                    break
        data_list.append({"topic_content": topic_start, "start_page": start_page, "end_page": end_page,
                          "tender_file_id": tender_file_id})
    end_topic = topics[-1]
    end_topic_document = documents[-1]
    end_topic_page = end_topic_document.page
    start_topic_page = data_list[-1]["end_page"]
    data_list.append({"topic_content": end_topic, "start_page": start_topic_page, "end_page": end_topic_page,
                      "tender_file_id": tender_file_id})
    data_topic_list = []
    data_topic_content_list = []
    data_topic_start_page_list = []
    data_topic_end_page_list = []
    data_topic_tender_file_id_list = []
    # 遍历每个主题数据
    for data in data_list:
        start_page = data.get("start_page", 0)
        if start_page is None:
            start_page = 0
        end_page = data.get("end_page", 0)
        if end_page is None:
            end_page = 0
        topic_content = data["topic_content"]
        data_topic_content_list.append(topic_content)
        data_topic_start_page_list.append(start_page)
        data_topic_end_page_list.append(end_page)
        data_topic_tender_file_id_list.append(data["tender_file_id"])
        for chunk in chunk_list:
            if chunk.page:
                if start_page <= chunk.page <= end_page:
                    chunk.topic = topic_content
        data_topic_list.append(
            TenderTopic(
                    topic_name=topic_content,
                    start_page=start_page,
                    end_page=end_page,
                    tender_file_id=data["tender_file_id"]))

    logger.info(f"标书-{tender_file_id}一级目录入数据库")
    embedding = QwenEmbeddingVectorizer()
    # 目录入数据库
    if len(data_topic_list) > 0:
        with app_context.db_session_factory() as session:
            session.add_all(data_topic_list)
            session.commit()
        # 目录入向量库
        logger.info(f"标书-{tender_file_id}一级目录入向量库库")
        topic_ems = embedding.encode_group(data_topic_content_list)
        topic_vector_milvus_db = create_tender_topic_vector_milvus_db(embedding.get_vector_dim())
        topic_vector_milvus_db.insert_info([data_topic_content_list, data_topic_start_page_list,
                                            data_topic_end_page_list, data_topic_tender_file_id_list,
                                            topic_ems])
    logger.info(f"标书-{tender_file_id}向量化入库开始")
    file_ids = []
    pages = []
    start_index_list = []
    texts = []
    topics = []
    for chunk in chunk_list:
        if chunk.topic:
            file_ids.append(chunk.file_id)
            pages.append(chunk.page)
            start_index_list.append(chunk.start_index)
            texts.append(chunk.text)
            topics.append(chunk.topic)
    all_ems = embedding.encode_group(texts)
    milvus_vector_db = create_tender_vector_milvus_db(embedding.get_vector_dim())
    vec_lis = all_ems
    milvus_vector_db.insert_info([file_ids, pages, start_index_list, texts, vec_lis, topics])
    logger.info(f"标书-{tender_file_id}向量化入库结束")
    return data_list
