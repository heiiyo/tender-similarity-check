from typing import Optional, Any, List

from pydantic import BaseModel, Field

from apps.web.vo.similarity_respose import BasePage


class ComplianceRulesVO(BaseModel):
    id: Optional[int]
    rule_name: Optional[str]
    rule_description: Optional[str]
    rule_topic: Optional[str] = Field(default="", description="对应主题")
    md: Optional[int] = Field(default=None, description="对应的提示词文件id")
    status: Optional[int] = Field(default=1, description="合规规则库状态：1-启用，2-禁用")


class ComplianceRulesPage(BasePage):
    data: Optional[List[ComplianceRulesVO]] = None


class ComplianceInfoVO(BaseModel):
    info_id: Optional[int]
    info_description: Optional[str]
    file_page_number: Optional[int]
    info_type: Optional[int]


class ComplianceInfoPage(BasePage):
    data: Optional[List[ComplianceInfoVO]]


class TenderComplianceInfoVO(BaseModel):
    tender_id: Optional[int]
    tender_url: Optional[str]
    tender_name: Optional[str]
    risk_number: Optional[int]
    passed_number: Optional[int]
    tender_list: Optional[List[Any]]
    data:Optional[ComplianceInfoPage]
