import pytest
import asyncio
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_siliconflow import ChatSiliconFlow

from agent.format.out_format import SkillComplianceListFormat, SkillInfoFormat
from agent.skill.skill import SkillRegistry
from agent.skill.skill_runner import (
    build_router_system_prompt,
    extract_skill_compliance_items,
    invoke_with_skill_or_llm,
    route_user_request,
    run_skill_by_name,
)
from agent.tools.tender_base_tool import check_official_seal, check_tender_signature, query_tender_topic, \
    query_tender_keyword


@pytest.fixture
def context():
    from apps import AppContext
    return AppContext().init_context()

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


def test_check_official_seal_tool(context):
    """检测盖章单元测试"""
    tool: BaseTool = check_official_seal
    result = tool.invoke({"bid_id": 1, "rule_id": 1})
    print(result)
    assert len(result) == 4

def test_query_tender_topic(context):
    tool: BaseTool = query_tender_topic
    result = tool.invoke({"bid_id": 1, "keyword": "技术标"})
    print(result)

def test_query_tender_keyword(context):
    tool: BaseTool = query_tender_keyword
    result = tool.invoke({"bid_id": 1, "keyword": "法定代表人或被授权人"})
    print(result)


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


def test_check_signature(context, skill_registry: SkillRegistry, model):
    skill_info = route_user_request(
        skill_registry,
        model,
        "帮我查询标书bid_id=1是否有盖公司公章",
    )
    assert skill_info.execution_mode == "skill"
    task_result = run_skill_by_name(model, skill_info.skill_name, instruction_params={"bid_id":1})
    batch = task_result["structured_response"]
    assert isinstance(batch, SkillComplianceListFormat)
    items = extract_skill_compliance_items(task_result)
    assert len(items) >= 1
    print(items[0].is_compliant, items[0].check_basis)


def test_check_official_seal(skill_registry: SkillRegistry, model):
    skill_info = route_user_request(
        skill_registry, model, "检测标书bid_id=1是否盖有公章"
    )
    assert skill_info.execution_mode == "skill"
    task_result = run_skill_by_name(model, skill_info.skill_name)
    batch = task_result["structured_response"]
    assert isinstance(batch, SkillComplianceListFormat)
    items = extract_skill_compliance_items(task_result)
    assert len(items) >= 1
    print(items[0].is_compliant, items[0].check_basis)


def test_invoke_routes_general_without_skill(skill_registry: SkillRegistry, model):
    out = invoke_with_skill_or_llm(
        skill_registry, model, "你好，请用一句话介绍你自己。"
    )
    assert out["mode"] == "general"
    assert out["router"].execution_mode == "general"
    assert out["invoke_result"]["messages"]


@pytest.mark.asyncio
async def test_invoke_routes_skill_when_matched(context, skill_registry: SkillRegistry, model):
    """测试技能路由和执行的完整流程，确保协程完全执行"""
    
    # 在当前事件循环中执行同步调用
    # invoke_with_skill_or_llm 内部会调用 asyncio.run()
    # 我们需要确保它完全执行完毕

    loop = asyncio.get_event_loop()
    
    # 在线程池中执行同步函数，避免阻塞事件循环
    out = await loop.run_in_executor(
        None,
        lambda: invoke_with_skill_or_llm(
            skill_registry, model, "检测标书bid_id=1是否盖有公章"
        )
    )
    
    # 验证路由结果
    assert out["mode"] == "skill", f"期望 mode='skill'，实际为 '{out['mode']}'"
    assert out["router"].execution_mode == "skill", \
        f"期望 execution_mode='skill'，实际为 '{out['router'].execution_mode}'"
    print(f"执行结果: {out['invoke_result']}")

    # 验证结构化响应
    structured_response = out["invoke_result"]["structured_response"]
    assert isinstance(structured_response, SkillComplianceListFormat), \
        f"期望 SkillComplianceListFormat，实际为 {type(structured_response).__name__}"

    # 验证items内容
    items = extract_skill_compliance_items(out["invoke_result"])
    assert len(items) >= 1, f"期望至少1个item，实际为 {len(items)}"

    # 打印结果用于调试
    print(f"\n=== 测试结果 ===")
    print(f"Mode: {out['mode']}")
    print(f"Items count: {len(items)}")
    for i, item in enumerate(items):
        print(f"  Item {i}: is_compliant={item.is_compliant}; {item.model_dump_json(indent=4, ensure_ascii=False)}")
