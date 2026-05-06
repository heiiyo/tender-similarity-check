import pytest
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_siliconflow import ChatSiliconFlow

from agent.format.out_format import SkillInfoFormat
from agent.skill.skill import SkillRegistry
from agent.skill.skill_runner import (
    build_router_system_prompt,
    invoke_with_skill_or_llm,
    route_user_request,
    run_skill_by_name,
)
from agent.tools.tender_base_tool import check_official_seal, check_tender_signature


@pytest.fixture
def skill_registry():
    return SkillRegistry()


@pytest.fixture
def model():
    return ChatSiliconFlow(
        base_url="https://api.siliconflow.cn/v1",
        api_key="sk-sdbwgllpqhbnijbotgyqsikuhowhmmuzpowxraulvasfexsv",
        model="Qwen/Qwen3.6-35B-A3B",
        temperature=0,
        max_tokens=1000,
        timeout=30,
        extra_body={"enable_thinking": False},
    )


def test_check_official_seal_tool():
    """检测盖章单元测试"""
    tool: BaseTool = check_official_seal
    result = tool.invoke({"bid_id": 1})
    print(result)
    assert len(result) == 4


def test_read_skills(skill_registry: SkillRegistry):
    assert len(skill_registry.skills) >= 1
    names = {s.name for s in skill_registry.skills}
    assert "query_keyword" in names


def test_agent_skill(skill_registry: SkillRegistry, model):
    """路由模型：标书技能匹配"""
    agent = create_agent(
        model,
        system_prompt=build_router_system_prompt(skill_registry),
        response_format=SkillInfoFormat,
    )
    result = agent.invoke(
        {"messages": [HumanMessage("帮我查询标书bid_id=1是否有法人代表或委托人签字")]}
    )
    assert isinstance(result["structured_response"], SkillInfoFormat)
    sig = result["structured_response"]
    print(sig)
    assert sig.execution_mode == "skill"
    assert sig.skill_name == "check_bid_signature"
    result = agent.invoke(
        {"messages": [HumanMessage("帮我查询标书bid_id=1是否存在'审计报表'")]}
    )
    assert isinstance(result["structured_response"], SkillInfoFormat)
    kw = result["structured_response"]
    print(kw)
    assert kw.execution_mode == "skill"
    assert kw.skill_name == "query_keyword"


def test_check_tender_signature_tool():
    """检测签字单元测试"""
    tool: BaseTool = check_tender_signature
    result = tool.invoke({"bid_id": 1, "page_number": [1]})
    print(result)
    assert len(result) == 1


def test_check_signature(skill_registry: SkillRegistry, model):
    skill_info = route_user_request(
        skill_registry,
        model,
        "帮我查询标书bid_id=1是否有法人代表或委托人签字",
    )
    assert skill_info.execution_mode == "skill"
    task_result = run_skill_by_name(model, skill_info.skill_name)
    print(task_result["messages"][-1].content)


def test_check_official_seal(skill_registry: SkillRegistry, model):
    skill_info = route_user_request(
        skill_registry, model, "检测标书bid_id=1是否盖有公章"
    )
    assert skill_info.execution_mode == "skill"
    task_result = run_skill_by_name(model, skill_info.skill_name)
    print(task_result["messages"][-1].content)


def test_invoke_routes_general_without_skill(skill_registry: SkillRegistry, model):
    out = invoke_with_skill_or_llm(
        skill_registry, model, "你好，请用一句话介绍你自己。"
    )
    assert out["mode"] == "general"
    assert out["router"].execution_mode == "general"
    assert out["invoke_result"]["messages"]


def test_invoke_routes_skill_when_matched(skill_registry: SkillRegistry, model):
    out = invoke_with_skill_or_llm(
        skill_registry, model, "检测标书bid_id=1是否盖有公章"
    )
    assert out["mode"] == "skill"
    assert out["router"].execution_mode == "skill"
    assert out["invoke_result"]["messages"]
