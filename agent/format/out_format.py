from typing import Literal

from pydantic import BaseModel, Field


class SkillInfoFormat(BaseModel):
    """
    路由层结构化输出：标书技能 / 系统工具 / 纯模型 三选一。
    """

    execution_mode: Literal["skill", "system_tools", "general"] = Field(
        description=(
            "skill=走 skills 目录（标书公章/签字/关键词等）；"
            "system_tools=走自定义系统工具（脚本执行、依赖安装等）；"
            "general=不挂载工具，仅用模型回答。"
        )
    )
    skill_name: str = Field(
        default="",
        description="execution_mode 为 skill 时必填，为 SKILL.md 中的 name；其它情况留空。",
    )
    system_tool_names: list[str] = Field(
        default_factory=list,
        description=(
            "execution_mode 为 system_tools 时填写要启用的系统工具名（与清单一致）；"
            "可为空表示启用全部系统工具由模型自选。"
        ),
    )
    skill_description: str = Field(
        default="",
        description="简述为何选择该 execution_mode；general 时说明用户意图类别即可。",
    )


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


class SkillComplianceListFormat(BaseModel):
    """技能执行后的多条合规结论（分页、分项或多检查点时使用）。"""

    items: list[SkillComplianceFormat] = Field(
        description=(
            "合规判定条目列表，每项结构与 SkillComplianceFormat 相同。"
            "单项检测可只含一条；多页/多项须分项列出多条，便于追溯。"
        ),
    )

class TopicFormat(BaseModel):
    """一级目录信息"""
    topic_name:str = Field(
        description="一级目录名称",
    )


class TopicListFormat(BaseModel):
    """一级目录信息"""

    topics: list[TopicFormat] = Field(
        description=(
            "目录集合"
        ),
    )

