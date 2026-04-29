import pytest
from langchain.agents import create_agent

from langchain_core.messages import HumanMessage
from langchain_siliconflow import ChatSiliconFlow

from agent.skill.skill import SkillRegistry
from agent.tools.tender_base_tool import load_skill, check_official_seal
from agent.format.out_format import SkillInfoFormat


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
        extra_body={"enable_thinking": False}
    )

def test_check_official_seal():
    result = check_official_seal(1)
    print(result)

def test_read_skills(skill_registry: SkillRegistry):
    assert 1 == len(skill_registry.skills)
    skill = skill_registry.skills[0]
    assert skill.name == "query_keyword"

def test_agent_skill(skill_registry: SkillRegistry, model):
    agent = create_agent(
        model,
        system_prompt=skill_registry.get_skill_catalog_prompt(),
        response_format=SkillInfoFormat
    )
    result = agent.invoke({"messages": [HumanMessage("帮我查询标书bid_id=1是否有法人代表或委托人签字")]})
    assert isinstance(result["structured_response"], SkillInfoFormat) == True
    print(result["structured_response"])
    assert result["structured_response"].skill_name == 'check_bid_signature'
    result = agent.invoke({"messages": [HumanMessage("帮我查询标书bid_id=1是否存在'审计报表'")]})
    assert isinstance(result["structured_response"], SkillInfoFormat) == True
    print(result["structured_response"])
    assert result["structured_response"].skill_name == 'query_keyword'


def test_agent_query_skill(skill_registry: SkillRegistry, model):
    main_agent = create_agent(
        model,
        system_prompt=skill_registry.get_skill_catalog_prompt(),
        response_format=SkillInfoFormat
    )
    result = main_agent.invoke({"messages": [HumanMessage("帮我查询标书bid_id=1是否有法人代表或委托人签字")]})
    assert isinstance(result["structured_response"], SkillInfoFormat) == True
    skill_info_format: SkillInfoFormat = result["structured_response"]
    tools, instructions= load_skill(skill_info_format.skill_name)
    skill_agent = create_agent(model, tools=tools, system_prompt="""
    你是一个执行引擎，不是聊天机器人。
    你的任务是分析用户请求并立即调用工具。
    
    【重要禁令】
    1. 禁止在回复中描述你的思考过程（例如：不要说“让我来调用工具”、“我正在查找”）。
    2. 禁止在回复中模拟工具调用的结果。
    3. 如果你需要调用工具，必须直接输出工具调用指令，不要有任何前置文本。
    
    【执行规则】
    - 如果用户的问题需要查询数据，必须直接调用工具。
    - 不要告诉我你要做什么，直接做！""")
    task_result = skill_agent.invoke({"messages": [HumanMessage(instructions)]})
    messages = task_result["messages"]
    print(messages[-1].content)

