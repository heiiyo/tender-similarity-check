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
