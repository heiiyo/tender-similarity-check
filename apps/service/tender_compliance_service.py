import asyncio
import json
import re
import shutil
import time
from io import BytesIO
from typing import List

from anyio import Path
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from sqlalchemy.sql.operators import and_

from agent.format.out_format import TopicListFormat
from apps import AppContext
from apps.algorithms.embedding import QwenEmbeddingVectorizer
from apps.document_parser.base import HFiledocument, HDocument
from apps.document_parser.markdown_parser import MarkDownParser
from apps.model_action.vllm_service import handle_rule, handel_topic
from apps.repository.entity.file_entity import FileRecordEntity
from apps.repository.entity.tender_entity import TenderPDFImageEntity, TenderTopic, TenderRuleConfiguration, \
    SubComplianceCheckTask, BidPlagiarismCheckTask, TenderComplianceRiskRecord
from apps.repository.minio_repository import get_file_url_http, get_file_url
from apps.service.milnus_service import create_tender_topic_vector_milvus_db, create_tender_vector_milvus_db
from apps.web.dto.compliance_dto import TenderComplianceDTO, ComplianceRulesConditionDTO, ComplianceInfoConditionDto
from apps.web.dto.tender_task import BasePageDto, TenderTaskDto
from apps.web.vo.compliance_respose import ComplianceRulesPage, ComplianceRulesVO, \
    TenderComplianceInfoVO, ComplianceInfoVO, SkillComplianceFormat
from apps.web.vo.similarity_respose import TenderTaskPage, FileRecordVO

from logger_config import get_logger

logger = get_logger(name=__name__)
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


def get_compliance_rule_by_id(rule_id: int):
    """
    根据规则ID查询单个规则详情
    :param rule_id: 规则ID
    :return: 规则详情VO，如果不存在则返回None
    """
    with app_context.db_session_factory() as session:
        rule = session.get(TenderRuleConfiguration, rule_id)
        if not rule:
            return None

        return ComplianceRulesVO(
            id=rule.id,
            rule_name=rule.rule_name,
            rule_description=rule.rule_description,
            skill_name=rule.skill_name,
            status=rule.status,
            rule_type=rule.rule_type,
            sort_order=rule.sort_order
        )


def query_all_compliance_rules():
    """
    获取所有合规规则列表（不分页，按sort_order倒序）
    :return: 规则列表
    """
    result_data = []
    with app_context.db_session_factory() as session:
        # 查询所有规则，按sort_order倒序排列
        rules = session.query(TenderRuleConfiguration).filter(TenderRuleConfiguration.is_deleted == 0).order_by(
            TenderRuleConfiguration.sort_order.desc()
        ).all()
        
        for rule in rules:
            result_data.append(
                ComplianceRulesVO(
                    id=rule.id,
                    rule_name=rule.rule_name,
                    rule_description=rule.rule_description,
                    skill_name=rule.skill_name,
                    status=rule.status,
                    rule_type=rule.rule_type,
                    sort_order=rule.sort_order
                )
            )
    
    return result_data


def add_compliance_rule(tender_compliance: TenderComplianceDTO):
    """
    添加合规规则
    :param tender_compliance: 规则信息
    """
    sort_order_value = tender_compliance.sort_order if tender_compliance.sort_order is not None else int(time.time())
    # 获取所有已启动的合规规则库
    with app_context.db_session_factory() as session:
        session.add(TenderRuleConfiguration(
            rule_name=tender_compliance.rule_name,
            rule_description=tender_compliance.rule_description,
            skill_name=tender_compliance.skill_name,
            status=tender_compliance.status,
            rule_type=tender_compliance.rule_type,
            sort_order=sort_order_value
        ))
        session.commit()


def update_compliance_rule_info(tender_compliance: TenderComplianceDTO):
    rule_id = None
    with app_context.db_session_factory() as session:
        rule: TenderRuleConfiguration = session.get(TenderRuleConfiguration, tender_compliance.id)
        if not rule:
            return None

        if tender_compliance.rule_name:
            rule.rule_name = tender_compliance.rule_name
        if tender_compliance.rule_description:
            rule.rule_description = tender_compliance.rule_description
        if tender_compliance.skill_name is not None:
            rule.skill_name = tender_compliance.skill_name
        if tender_compliance.status is not None:
            rule.status = tender_compliance.status
        if tender_compliance.rule_type is not None:
            rule.rule_type = tender_compliance.rule_type
        if tender_compliance.sort_order is not None:
            rule.sort_order = tender_compliance.sort_order

        session.add(rule)
        session.commit()
        rule_id = rule.id
    return rule_id

def delete_compliance_rule_by_id(rule_id: int):
    """
    删除合规规则（逻辑删除，设置 is_deleted 为 True）
    :param rule_id: 合规规则ID
    """
    with app_context.db_session_factory() as session:
        rule = session.get(TenderRuleConfiguration, rule_id)
        if not rule:
            return False
        
        # 假设 TenderRuleConfiguration 实体中有 is_deleted 字段
        # 如果实体中没有该字段，请确保在数据库模型中添加 is_deleted 列
        if hasattr(rule, 'is_deleted'):
            rule.is_deleted = True
        else:
            # 如果没有 is_deleted 字段，这里可能需要根据实际模型调整
            # 通常逻辑删除会修改状态或删除记录，这里按照指令使用 is_deleted
            logger.warning(f"TenderRuleConfiguration 实体中未找到 is_deleted 字段，无法执行逻辑删除")
            return False
            
        session.add(rule)
        session.commit()
        return True


def delete_skill_by_name(skill_name: str):
    """
    根据 skill_name 删除 skills 目录下对应的 skill 文件夹
    :param skill_name: 技能名称
    :return: 删除结果字典
    """
    if not skill_name:
        return {"success": False, "message": "技能名称不能为空"}

    # 假设 skills 目录位于项目根目录或特定配置路径下
    # 这里使用相对路径 'skills'，实际项目中可能需要根据配置调整
    skills_dir = Path("skills")
    skill_path = skills_dir / skill_name

    try:
        # 检查路径是否存在且是一个目录
        if not (skill_path.exists() and skill_path.is_dir()):
            logger.warning(f"技能文件夹不存在或不是目录: {skill_path}")
            return {"success": False, "message": f"技能文件夹 '{skill_name}' 不存在"}

        # 删除文件夹及其内容
        shutil.rmtree(skill_path)
        logger.info(f"成功删除技能文件夹: {skill_path}")
        return {"success": True, "message": f"技能文件夹 '{skill_name}' 已删除"}

    except Exception as e:
        logger.error(f"删除技能文件夹 '{skill_name}' 时发生错误: {str(e)}", exc_info=True)
        return {"success": False, "message": f"删除失败: {str(e)}"}


def query_compliance_rules_list(rules_condition_dto: ComplianceRulesConditionDTO):
    page = rules_condition_dto.page_offset  # 当前页码（从 1 开始）
    per_page = rules_condition_dto.page_size  # 每页记录数
    # 计算偏移量
    offset = (page - 1) * per_page
    condition_array = []
    result_data = []
    condition_array.append(TenderRuleConfiguration.is_deleted == 0)
    # 筛选任务类型
    if rules_condition_dto.rule_name:
        condition_array.append(TenderRuleConfiguration.rule_name == rules_condition_dto.rule_name)
    if rules_condition_dto.status:
        condition_array.append(TenderRuleConfiguration.status == rules_condition_dto.status)
    if rules_condition_dto.rule_type:
        condition_array.append(TenderRuleConfiguration.rule_type == rules_condition_dto.rule_type)
    with app_context.db_session_factory() as session:
        if condition_array and len(condition_array) >= 1:
            rules = session.query(TenderRuleConfiguration).filter(*condition_array).order_by(TenderRuleConfiguration.sort_order.desc()).offset(offset).limit(
                per_page).all()
            count = session.query(TenderRuleConfiguration).filter(*condition_array).count()
        else:
            rules = session.query(TenderRuleConfiguration).order_by(TenderRuleConfiguration.sort_order.desc()).offset(offset).limit(
                per_page).all()
            count = session.query(TenderRuleConfiguration).count()
        for rule in rules:
            result_data.append(
                ComplianceRulesVO(id=rule.id,
                                  rule_name=rule.rule_name,
                                  rule_description=rule.rule_description,
                                  skill_name=rule.skill_name,
                                  status=rule.status,
                                  rule_type=rule.rule_type,
                                  sort_order=rule.sort_order))
    page = ComplianceRulesPage(
        page_offset=rules_condition_dto.page_offset,
        page_size=len(result_data),
        page_num=calculate_pages_int(count, per_page),
        total=count,
        data=result_data
    )
    return page


def create_compliance_check_task_record(tender_task_dto: TenderTaskDto):
    """创建合规任务记录（同步，供接口立即返回任务信息）。"""
    if not tender_task_dto.file_ids:
        return None
    with app_context.db_session_factory() as session:
        file_record_list = session.query(FileRecordEntity).filter(
            FileRecordEntity.id.in_(tender_task_dto.file_ids)).all()
        file_name_list = [file_record.file_name for file_record in file_record_list]
        file_id_list = [file_record.id for file_record in file_record_list]
        task = BidPlagiarismCheckTask(
            check_type=tender_task_dto.check_type,
            task_name=tender_task_dto.task_name,
            file_name_list=",".join(file_name_list),
            file_id_list=','.join(map(str, file_id_list)),
            task_type=tender_task_dto.task_type,
            tender_reference_file_id=tender_task_dto.tender_reference_id
        )
        session.add(task)
        session.commit()
        return task.id


async def run_compliance_checks_task(file_ids: List[int], task_id: int):
    """合规检测步骤：步骤内并发，步骤间由流水线顺序保证。"""
    max_concurrency = 3
    semaphore = asyncio.Semaphore(max_concurrency)

    async def process_one(tender_file_id: int):
        async with semaphore:
            await asyncio.to_thread(compliance_background_task, tender_file_id, task_id)

    await asyncio.gather(*(process_one(fid) for fid in file_ids))


def compliance_background_task(tender_file_id, task_id):
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
    from collections import defaultdict
    compliance_info_data = []
    with app_context.db_session_factory() as session:
        # 获取所有风险记录
        record_list = session.query(TenderComplianceRiskRecord).filter(
            TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id).all()
        risk_number = session.query(TenderComplianceRiskRecord) \
            .filter(and_(TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id,
                         TenderComplianceRiskRecord.is_compliant == 1)) \
            .count()
        passed_number = session.query(TenderComplianceRiskRecord) \
            .filter(and_(TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id,
                         TenderComplianceRiskRecord.is_compliant == 0)) \
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

        # 按 rule_id 分组
        records_by_rule = defaultdict(list)
        for record in record_list:
            if record.rule_id is not None:
                records_by_rule[record.rule_id].append(record)

        # 获取所有涉及的 rule_id
        rule_ids = list(records_by_rule.keys())

        # 批量查询规则信息
        rules_dict = {}
        if rule_ids:
            rules = session.query(TenderRuleConfiguration).filter(
                TenderRuleConfiguration.id.in_(rule_ids)
            ).all()
            for rule in rules:
                rules_dict[rule.id] = rule

        # 组装数据
        for rule_id, records in records_by_rule.items():
            rule = rules_dict.get(rule_id)
            if not rule:
                logger.warning(f"未找到规则 ID: {rule_id}")
                continue

            # 构建该规则下的所有检测结果
            compliance_list = []
            for record in records:
                compliance_item = SkillComplianceFormat(
                    is_compliant=(record.is_compliant == 0),  # is_compliant=0 表示合规
                    page_number=record.page_number if record.page_number else 0,
                    check_basis=record.check_basis if record.check_basis else ""
                )
                compliance_list.append(compliance_item)

            # 统计异常和正常条目数量
            abnormal_count = sum(1 for item in compliance_list if not item.is_compliant)
            normal_count = sum(1 for item in compliance_list if item.is_compliant)

            # 构建规则维度的合规信息
            compliance_info = ComplianceInfoVO(
                rule_id=rule_id,
                rule_name=rule.rule_name if rule else "",
                rule_description=rule.rule_description if rule else "",
                abnormal_count=abnormal_count,
                normal_count=normal_count,
                compliance_list=compliance_list
            )
            compliance_info_data.append(compliance_info)

    # 注意：这里不再使用分页，因为已经按规则分组
    page = TenderComplianceInfoVO(
        data=compliance_info_data,
        tender_id=file_record_top.id,
        tender_name=file_record_top.file_name,
        tender_url=get_file_url(file_record_top.file_path),
        risk_number=risk_number,
        passed_number=passed_number,
        tender_list=file_record_list
    )
    return page


def get_compliance_info(compliance_info_condition: ComplianceInfoConditionDto) -> List[ComplianceInfoVO]:
    """
    根据标书tender_id获取合规检测信息
    :param tender_id: 标书ID
    :return: 合规检测信息列表
    """
    compliance_info_data = []

    with app_context.db_session_factory() as session:
        # 1. 查询该标书的所有合规风险记录
        records = session.query(TenderComplianceRiskRecord).filter(
            TenderComplianceRiskRecord.tender_file_id == compliance_info_condition.tender_id
        ).all()

        if not records:
            logger.info(f"标书 {compliance_info_condition.tender_id} 没有合规检测记录")
            return []

        # 2. 按 rule_id 分组统计
        rule_ids = set(record.rule_id for record in records if record.rule_id)

        # 3. 为每个规则构建合规信息
        for rule_id in rule_ids:
            # 获取规则信息
            rule = session.get(TenderRuleConfiguration, rule_id)

            # 筛选条件
            rule_records_all = [record for record in records if record.rule_id == rule_id]
            if compliance_info_condition.check_type == 2:
                rule_records = rule_records_all
            else:
                rule_records = [record for record in records
                            if record.rule_id == rule_id and record.is_compliant==compliance_info_condition.check_type]

            # 构建该规则下的所有检测结果
            compliance_list = []
            for record in rule_records:
                compliance_item = SkillComplianceFormat(
                    is_compliant=(record.is_compliant == 1),  # is_compliant=1 表示合规
                    page_number=record.page_number if record.page_number else 0,
                    check_basis=record.check_basis if record.check_basis else ""
                )
                compliance_list.append(compliance_item)

            # 统计异常和正常条目数量（基于该规则的所有记录）
            abnormal_count = sum(1 for record in rule_records_all if record.is_compliant == 0)
            normal_count = sum(1 for record in rule_records_all if record.is_compliant == 1)

            # 构建规则维度的合规信息
            compliance_info = ComplianceInfoVO(
                rule_id=rule_id,
                rule_name=rule.rule_name if rule else "",
                rule_description=rule.rule_description if rule else "",
                abnormal_count=abnormal_count,
                normal_count=normal_count,
                compliance_list=compliance_list
            )
            compliance_info_data.append(compliance_info)

    return compliance_info_data

def update_compliance_rule_sort_order(sort_list: List[dict]):
    """
    批量更新规则排序
    :param sort_list: 排序列表，每个元素包含 id 和 sort_order
    """
    with app_context.db_session_factory() as session:
        for item in sort_list:
            rule_id = item.get('id')
            sort_order = item.get('sort_order')
            
            if rule_id is not None and sort_order is not None:
                rule = session.get(TenderRuleConfiguration, rule_id)
                if rule:
                    rule.sort_order = sort_order
        
        session.commit()


async def compliance_validation(tender_file_id):
    """
    合规性验证主流程
    """
    try:
        # 1. 获取子任务和主任务信息（前置校验，失败则快速返回）
        with app_context.db_session_factory() as session:
            sub_compliance_task = session.query(SubComplianceCheckTask).filter(
                SubComplianceCheckTask.tender_file_id == tender_file_id
            ).order_by(SubComplianceCheckTask.id.desc()).first()
            
            if not sub_compliance_task:
                logger.error(f"未找到标书 {tender_file_id} 的合规子任务")
                return
            
            sub_compliance_check_task_id = sub_compliance_task.id
            bid_plagiarism_check_task_id = sub_compliance_task.bid_plagiarism_check_task_id
            
            # 获取主任务信息以获取 task_type
            main_task = session.query(BidPlagiarismCheckTask).filter(
                BidPlagiarismCheckTask.id == bid_plagiarism_check_task_id
            ).first()
            
            if not main_task:
                logger.error(f"未找到主任务 {bid_plagiarism_check_task_id}")
                return
            
            task_type = main_task.task_type
        
        # 2. 并行检查并处理图片和目录
        md_parser = MarkDownParser()
        
        # 检查是否需要生成图片
        with app_context.db_session_factory() as session:
            has_images = session.query(TenderPDFImageEntity).filter(
                TenderPDFImageEntity.tender_file_id == tender_file_id
            ).first() is not None
        
        # 检查是否需要解析目录
        with app_context.db_session_factory() as session:
            has_topics = session.query(TenderTopic).filter(
                TenderTopic.tender_file_id == tender_file_id
            ).first() is not None
        
        # 构建并行任务列表
        parallel_tasks = []
        
        # 任务1：生成图片（如果需要）
        if not has_images:
            parallel_tasks.append(md_parser.to_images(tender_file_id=tender_file_id))
            logger.info(f"标书 {tender_file_id} 开始生成图片")
        
        # 任务2：解析目录并入库（如果需要）
        if not has_topics:
            async def parse_and_index():
                """解析目录并建立向量索引"""
                result = await parser_tender_topic(tender_file_id)
                documents = parser_document(tender_file_id)
                insert_into_milvus(tender_file_id, result, documents)
            
            parallel_tasks.append(parse_and_index())
            logger.info(f"标书 {tender_file_id} 开始解析目录")
        
        # 并行执行独立任务
        if parallel_tasks:
            await asyncio.gather(*parallel_tasks, return_exceptions=True)
        
        # 3. 根据任务类型获取匹配的合规规则库
        with app_context.db_session_factory() as session:
            # 根据 task_type 匹配 rule_type
            query = session.query(TenderRuleConfiguration).filter(
                TenderRuleConfiguration.status == 1
            )
            
            # 如果 task_type 有值，则添加 rule_type 过滤条件
            if task_type is not None:
                query = query.filter(and_(TenderRuleConfiguration.rule_type == task_type, TenderRuleConfiguration.rule_type ==1))
                logger.info(f"标书 {tender_file_id} 使用任务类型 {task_type} 匹配规则")
            else:
                logger.warning(f"标书 {tender_file_id} 的任务类型为 None，将获取所有启用的规则")
            
            rule_list = query.all()
        
        if not rule_list:
            logger.warning(f"标书 {tender_file_id} 没有可用的合规规则（任务类型: {task_type}）")
            return
        
        # 4. 并行执行所有规则检查
        logger.info(f"标书 {tender_file_id} 开始执行 {len(rule_list)} 个合规规则检查")
        asyncio_task = [
            handle_rule(rule, tender_file_id,
                        sub_compliance_check_task_id,
                        bid_plagiarism_check_task_id)
            for rule in rule_list
        ]
        
        # 使用 gather 并行执行，并捕获异常避免单个规则失败影响整体
        await asyncio.gather(*asyncio_task, return_exceptions=True)
        
        logger.info(f"标书 {tender_file_id} 合规验证完成")
    
    except Exception as e:
        logger.error(f"标书 {tender_file_id} 合规验证异常: {str(e)}", exc_info=True)
        raise


async def parser_tender_topic(tender_file_id):
    logger.info(f"parser_tender_topic-{tender_file_id}开始")
    with app_context.db_session_factory() as session:
        tender_pdf_image_list = session.query(TenderPDFImageEntity)\
            .filter(and_(TenderPDFImageEntity.tender_file_id == tender_file_id, and_(TenderPDFImageEntity.page_number > 1, TenderPDFImageEntity.page_number < 10)))\
            .order_by(TenderPDFImageEntity.page_number.asc()).all()
        context = ""
        for image in tender_pdf_image_list:
            context += image.page_context
        agent_model = AppContext().agent_model
        agent = create_agent(
            agent_model,
            system_prompt='''
            # Role
            你是一名文档目录审核专家，用于提取文档目录内容
            
            # Context
            根据输入内容分析出文档的一级目录
            
            # Few-Shot Examples
            ## Example 1 (符合要求)
            Input: 帮我分析出内容中的一级目录。
            Output: {'topics': [{'topic_name':'投标函'},{'topic_name':'投标保证金'}]}    
            ''',
            response_format=TopicListFormat,
        )

        response = await agent.ainvoke({"messages": [HumanMessage(context)]})
        topic_formatted: TopicListFormat = response['structured_response']
        topic_list = [topic.topic_name for topic in topic_formatted.topics]
        logger.info(f"parser_tender_topic-{tender_file_id}结束")
        return topic_list


def parser_document(tender_file_id):
    logger.info(f"解析标书-{tender_file_id}开始")
    print(f"解析标书-{tender_file_id}开始")
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
    embedding = AppContext().embedding_vectorizer
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
