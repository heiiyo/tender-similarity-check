from pydantic import BaseModel, Field


class SkillInfoFormat(BaseModel):
    """
    技能信息输出格式
    """
    skill_name: str = Field(description="技能名称")
    skill_description: str = Field(description="技能描述")
