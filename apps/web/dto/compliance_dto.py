from typing import Optional

from pydantic import BaseModel, Field

from apps.web.dto.tender_task import BasePageDto


class TenderComplianceDTO(BaseModel):
    id: Optional[int] = Field(default=None, description="规则id")
    rule_name: Optional[str] = None
    rule_description: Optional[str] = None
    rule_topic: Optional[str] = Field(default="", description="对应主题")
    md: Optional[str] = Field(default=None, description="对应的提示词文件id")
    status: Optional[int] = Field(default=1, description="合规规则库状态：1-启用，2-禁用")


class ComplianceRulesConditionDTO(BasePageDto):
    rule_name: Optional[str] = None


class ComplianceInfoConditionDto(BasePageDto):
    tender_id: Optional[int] = None
