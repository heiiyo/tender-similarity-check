from pathlib import Path
from typing import List

import frontmatter

from apps import AppContext

class SkillDetail:

    def __init__(self, name, path, description, tools):
        """
        :param name: skill名称
        :param path: skill路径
        :param description: skill描述
        :param tools: 允许的工具
        """
        self.name = name
        self.path = path
        self.description = description
        self.tools = tools

    def get_tools(self):
        return self.tools

    def load_instructions(self) -> str:
        """
        加载指令，用于执行任务
        """
        # 支持多种可能的文件名，增加灵活性
        for filename in ["instructions.md", "README.md", "prompt.md", "SKILL.md"]:
            instruction_file = self.path / filename
            if instruction_file.exists():
                with open(instruction_file, "r", encoding="utf-8") as f:
                    return f.read()
        return ""

    def _load_script(self):
        """
        加载需要执行的脚本
        """



class SkillRegistry:
    """
    skill registry
    """
    def __init__(self, skills_dir=AppContext.project_root / "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills_metadata = []
        self.skills: List[SkillDetail] = []
        self._scan_skills()

    def _scan_skills(self):
        """第一层：仅扫描元数据，不加载详细内容"""
        for skill_folder in self.skills_dir.iterdir():
            if skill_folder.is_dir():
                meta_file = skill_folder / "SKILL.md"
                if meta_file.exists():
                    # 简单解析 Markdown 头部的 YAML 块
                    meta = frontmatter.load(str(meta_file))
                    self.skills.append(SkillDetail(**meta.metadata, path=skill_folder))

    def get_skill_catalog_prompt(self):
        """生成给 LLM 的初始提示词：仅包含技能列表"""
        catalog = """
        根据用户问题匹配对对应的技能
        Available Skills:
        """
        for skill in self.skills:
            catalog += f"- {skill.name}: {skill.description}\n"
        catalog += """
        输出json案例：
        {"skill_name": query_xxx, "bid_id"=1}
        """
        return catalog


    def get_skill(self, skill_name: str) -> SkillDetail | None:
        for skill in self.skills:
            if skill.name == skill_name:
                return skill
        return None



class SkillContent:
    skill_registry = SkillRegistry()

    @staticmethod
    def get_skill(skill_name: str) -> SkillDetail | None:
        return SkillContent.skill_registry.get_skill(skill_name)
