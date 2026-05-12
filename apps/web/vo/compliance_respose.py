from typing import Optional, Any, List

from pydantic import BaseModel, Field

from apps.web.vo.similarity_respose import BasePage


class ComplianceRulesVO(BaseModel):
    id: Optional[int] = Field(description="规则id")
    rule_name: Optional[str] = Field(description="规则名称")
    rule_description: Optional[str] = Field(default="", description="规则描述")
    skill_name: Optional[str] = Field(default=None, description="技能名称")
    status: Optional[int] = Field(default=1, description="合规规则库状态：1-启用，2-禁用")
    rule_type: Optional[int] = Field(description="规则类型：1-民用，2-军用")
    sort_order: Optional[int] = Field(default=None, description="排序字段")


class ComplianceRulesPage(BasePage):
    data: Optional[List[ComplianceRulesVO]] = None


class SkillComplianceFormat(BaseModel):
    """技能执行完成后的合规判定（结构化输出）。"""

    is_compliant: bool = Field(
        description="综合 SKILL 要求与工具返回事实，结论是否合规：true=合规，false=不合规或存在缺陷。",
    )
    page_number: int = Field(description="标书对应的页码")
    check_basis: str = Field(
        description=(
            "检查依据：说明依据哪些工具结果、数据字段、页码或规则作出上述判定；"
            "须与工具返回一致，不得臆造。"
        ),
    )


class ComplianceInfoVO(BaseModel):
    rule_id: Optional[int] = Field(description="规则id")
    rule_name: Optional[str] = Field(description="规则名称")
    rule_description: Optional[str] = Field(description="规则描述")
    compliance_list: Optional[List[SkillComplianceFormat]] = Field(description="规则检测结果")


class TenderComplianceInfoVO(BaseModel):
    tender_id: Optional[int]
    tender_url: Optional[str]
    tender_name: Optional[str]
    risk_number: Optional[int]
    passed_number: Optional[int]
    tender_list: Optional[List[Any]]
    data:Optional[List[ComplianceInfoVO]]
