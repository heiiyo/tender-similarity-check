from typing import List

from fastapi import APIRouter

from apps.service.tender_compliance_service import add_compliance_rule, update_compliance_rule_info, \
    query_compliance_rules_list, query_tender_compliance_list, query_tender_compliance_info
from apps.web.dto.compliance_dto import TenderComplianceDTO, ComplianceRulesConditionDTO, ComplianceInfoConditionDto
from apps.web.dto.tender_task import BasePageDto
from apps.web.vo.compliance_respose import ComplianceRulesPage, ComplianceRulesVO, TenderComplianceInfoVO, \
    ComplianceInfoVO, ComplianceInfoPage
from apps.web.vo.similarity_respose import BaseResponse, TenderTaskPage, FileRecordVO

tender_compliance_router = APIRouter(prefix="/api/tender/compliance", tags=["标书合规 "])


@tender_compliance_router.post("/compliance_rules", response_model=BaseResponse)
def create_compliance_rules(tender_compliance: TenderComplianceDTO):
    """
    创建合规规则接口
    """
    add_compliance_rule(tender_compliance)
    return BaseResponse.success()


@tender_compliance_router.post("/update_compliance_rules", response_model=BaseResponse)
def update_compliance_rules(tender_compliance: TenderComplianceDTO):
    """
    更新规则库（包括状态）
    """
    return BaseResponse.success(update_compliance_rule_info(tender_compliance))


@tender_compliance_router.post("/compliance_rules_list", response_model=BaseResponse, description="获取合规规则库列表")
def compliance_rules_list(rules_condition_dto: ComplianceRulesConditionDTO):
    page = query_compliance_rules_list(rules_condition_dto)
    return BaseResponse.success(page)


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
