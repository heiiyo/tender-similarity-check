"""sys_load_references_tool 单元测试。"""
from pathlib import Path

import pytest

from agent.skill.skill import SkillDetail
from agent.tools import system_tool as st


class TestSysLoadReferencesTool:
    """根据 skill_name 解析 skills 目录下参考文件并读取内容。"""

    @staticmethod
    def _fake_skill(skill_dir: Path, skill_name: str = "demo_skill") -> SkillDetail:
        return SkillDetail(skill_name, skill_dir, "test", [])

    def test_empty_skill_name(self):
        out = st.sys_load_references_tool.invoke(
            {"skill_name": "", "reference_path": "x.txt"}
        )
        assert "skill_name 不能为空" in out

    def test_empty_reference_path(self):
        out = st.sys_load_references_tool.invoke(
            {"skill_name": "demo_skill", "reference_path": ""}
        )
        assert "reference_path 不能为空" in out

    def test_unknown_skill(self):
        out = st.sys_load_references_tool.invoke(
            {"skill_name": "nonexistent_skill___xyz", "reference_path": "a.txt"}
        )
        assert "未知技能" in out

    def test_reads_file_at_skill_root(self, tmp_path: Path, monkeypatch):
        skill_dir = tmp_path / "demo_skill"
        skill_dir.mkdir()
        (skill_dir / "readme.txt").write_text("root-body", encoding="utf-8")

        def fake_get(name: str):
            return self._fake_skill(skill_dir, name) if name == "demo_skill" else None

        monkeypatch.setattr(st.SkillContent, "get_skill", fake_get)

        out = st.sys_load_references_tool.invoke(
            {"skill_name": "demo_skill", "reference_path": "readme.txt"}
        )
        assert "文件内容:" in out
        assert "root-body" in out
        assert "readme.txt" in out

    def test_reads_file_under_references(self, tmp_path: Path, monkeypatch):
        skill_dir = tmp_path / "demo_skill"
        skill_dir.mkdir()
        ref = skill_dir / "references"
        ref.mkdir()
        (ref / "note.md").write_text("in-ref", encoding="utf-8")

        monkeypatch.setattr(
            st.SkillContent,
            "get_skill",
            lambda name: self._fake_skill(skill_dir, name)
            if name == "demo_skill"
            else None,
        )

        out = st.sys_load_references_tool.invoke(
            {"skill_name": "demo_skill", "reference_path": "note.md"}
        )
        assert "in-ref" in out

    def test_absolute_path_reads_without_skill_lookup(self, tmp_path: Path):
        f = tmp_path / "abs_only.txt"
        f.write_text("abs-content", encoding="utf-8")

        out = st.sys_load_references_tool.invoke(
            {
                "skill_name": "ignored_when_absolute",
                "reference_path": str(f.resolve()),
            }
        )
        assert "abs-content" in out

    def test_path_traversal_rejected(self, tmp_path: Path, monkeypatch):
        skill_dir = tmp_path / "demo_skill"
        skill_dir.mkdir()
        (skill_dir / "safe.txt").write_text("ok", encoding="utf-8")

        monkeypatch.setattr(
            st.SkillContent,
            "get_skill",
            lambda name: self._fake_skill(skill_dir, name)
            if name == "demo_skill"
            else None,
        )

        out = st.sys_load_references_tool.invoke(
            {
                "skill_name": "demo_skill",
                "reference_path": "../outside.txt",
            }
        )
        assert "未找到参考文件" in out or "错误" in out
