from typing import Optional

from pydantic import BaseModel, Field

from apps.web.dto.tender_task import BasePageDto


class TenderComplianceDTO(BaseModel):
    id: Optional[int] = Field(default=None, description="规则id")
    rule_name: Optional[str] = Field(description="规则名称")
    rule_description: Optional[str] = Field(description="规则描述")
    skill_name: Optional[str] = Field(description="对应的提示词文件名称")
    status: Optional[int] = Field(description="合规规则库状态：1-启用，2-禁用")
    rule_type: Optional[int] = Field(description="规则类型：1-通用，2-民用，3-军用")
    sort_order: Optional[int] = Field(default=None, description="排序字段，默认为当前时间戳")


class ComplianceRulesConditionDTO(BasePageDto):
    rule_name: Optional[str] = Field(default=None, description="规则名称")
    status: Optional[int] = Field(default=None, description="合规规则库状态：1-启用，2-禁用")
    rule_type: Optional[int] =  Field(default=None, description="规则类型：1-通用，2-民用，3-军用")


class ComplianceInfoConditionDto(BaseModel):
    tender_id: Optional[int] = None
