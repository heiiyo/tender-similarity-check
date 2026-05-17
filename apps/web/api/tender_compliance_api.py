from typing import List

from fastapi import APIRouter

from apps.service.tender_compliance_service import add_compliance_rule, update_compliance_rule_info, \
    query_compliance_rules_list, query_tender_compliance_list, query_tender_compliance_info, \
    update_compliance_rule_sort_order, query_all_compliance_rules, get_compliance_rule_by_id, \
    delete_compliance_rule_by_id, delete_skill_by_name, get_compliance_info
from apps.web.dto.compliance_dto import TenderComplianceDTO, ComplianceRulesConditionDTO, ComplianceInfoConditionDto
from apps.web.dto.tender_task import BasePageDto
from apps.web.vo.similarity_respose import BaseResponse
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__name__)

tender_compliance_router = APIRouter(prefix="/api/tender/compliance", tags=["标书合规 "])


@tender_compliance_router.post("/compliance_rules", response_model=BaseResponse)
def create_compliance_rules(tender_compliance: TenderComplianceDTO):
    """
    创建合规规则接口
    """
    add_compliance_rule(tender_compliance)
    return BaseResponse.success()


@tender_compliance_router.get("/compliance_rules/{rule_id}", response_model=BaseResponse,
                              description="获取单个合规规则详情")
def get_compliance_rule(rule_id: int):
    """
    根据规则ID查询单个规则详情
    :param rule_id: 规则ID
    :return: 规则详情
    """
    rule = get_compliance_rule_by_id(rule_id)

    if not rule:
        return BaseResponse.error(message=f"规则 ID {rule_id} 不存在")

    return BaseResponse.success(data=rule)


@tender_compliance_router.post("/update_compliance_rules", response_model=BaseResponse)
def update_compliance_rules(tender_compliance: TenderComplianceDTO):
    """
    更新规则库（包括状态）
    """
    return BaseResponse.success(update_compliance_rule_info(tender_compliance))


@tender_compliance_router.post("/update_sort_order", response_model=BaseResponse)
def update_sort_order(sort_list: List[dict]):
    """
    批量更新规则排序（前端拖拽排序后调用）
    :param sort_list: 排序列表，格式为 [{"id": 1, "sort_order": 1234567890}, {"id": 2, "sort_order": 1234567891}, ...]
    """
    update_compliance_rule_sort_order(sort_list)
    return BaseResponse.success()


@tender_compliance_router.post("/compliance_rules_list", response_model=BaseResponse, description="获取合规规则库列表")
def compliance_rules_list(rules_condition_dto: ComplianceRulesConditionDTO):
    page = query_compliance_rules_list(rules_condition_dto)
    return BaseResponse.success(page)


@tender_compliance_router.get("/all_compliance_rules", response_model=BaseResponse, description="获取所有合规规则列表（不分页）")
def get_all_compliance_rules():
    """
    获取所有合规规则列表，不进行分页和筛选，按sort_order倒序排列
    :return: 规则列表
    """
    rules = query_all_compliance_rules()
    return BaseResponse.success(data=rules)


@tender_compliance_router.delete("/delete_compliance_rule/{rule_id}", response_model=BaseResponse, description="根据rule_id删除规则")
def delete_compliance_rule(rule_id: int):
    """
    删除合规规则
    :param rule_id: 规则ID
    """
    delete_compliance_rule_by_id(rule_id)
    return BaseResponse.success()


@tender_compliance_router.delete("/skills/{skill_name}", response_model=BaseResponse,
                                 description="根据skill_name删除skills目录下对应的skill")
def delete_skill(skill_name: str):
    """
    根据技能名称删除 skills 目录下对应的 skill 文件夹
    :param skill_name: 技能名称
    :return: 删除结果
    """
    result = delete_skill_by_name(skill_name)

    if result.get("success"):
        return BaseResponse.success(data=result, message=result.get("message"))
    else:
        return BaseResponse.error(message=result.get("message"))

@tender_compliance_router.post("/tender_compliance_list/{task_id}", response_model=BaseResponse, description="获取标书合规列表")
def tender_compliance_list(task_id, page_dto: BasePageDto):
    """
    获取标书合规列表
    :param task_id: 任务id
    :param page_dto: 分页字段
    """
    tender_page = query_tender_compliance_list(task_id, page_dto)
    return BaseResponse.success(data=tender_page)


@tender_compliance_router.post("/tender_compliance_info", response_model=BaseResponse, description="获取合规详情")
def tender_compliance_info(compliance_info_condition: ComplianceInfoConditionDto):
    page = query_tender_compliance_info(compliance_info_condition)
    return BaseResponse.success(data=page)


@tender_compliance_router.post("/compliance_info", response_model=BaseResponse, description="根据标书ID获取合规检测信息")
def get_tender_compliance_info(compliance_info_condition: ComplianceInfoConditionDto):
    """
    根据标书tender_id获取合规检测信息
    :param tender_id: 标书ID
    :return: 合规检测信息列表
    """
    compliance_info_list = get_compliance_info(compliance_info_condition)
    return BaseResponse.success(data=compliance_info_list)




