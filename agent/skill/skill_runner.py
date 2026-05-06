"""
用户请求编排：路由模型在「标书技能 / 系统工具 / 纯模型」间选择；
命中技能则 load_skill；命中系统工具则挂载对应工具与用户原问题交互。
"""
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool

from agent.format.out_format import SkillInfoFormat
from agent.skill.skill import SkillRegistry
from agent.tools.system_tool import format_system_tools_catalog, system_tools_by_name, get_registered_system_tools
from agent.tools.tender_base_tool import load_skill

SKILL_EXECUTOR_SYSTEM_PROMPT = """
你是一个执行引擎，不是聊天机器人。
你的任务是分析用户请求并立即调用工具。

【重要禁令】
1. 禁止在回复中描述你的思考过程（例如：不要说“让我来调用工具”、“我正在查找”）。
2. 禁止在回复中模拟工具调用的结果。
3. 如果你需要调用工具，必须直接输出工具调用指令，不要有任何前置文本。

【执行规则】
- 如果用户的问题需要查询数据，必须直接调用工具。
- 不要告诉我你要做什么，直接做！"""

SYSTEM_TOOLS_EXECUTOR_SYSTEM_PROMPT = """
你是系统任务执行引擎。用户问题已路由到「系统工具」能力。
根据用户需求正确调用可用工具（执行脚本、安装依赖等），不要做无关闲聊。
调用工具时禁止编造工具返回结果；必须先调用工具再总结。
注意脚本执行与环境安全，路径须明确。"""

GENERAL_AGENT_SYSTEM_PROMPT = """你是招投标与标书领域的智能助手。
当前请求未匹配标书技能或系统工具链路，请直接基于你的知识回答用户。
若问题依赖具体标书文件、扫描件或内部数据库而你无法访问，请如实说明。"""


def build_router_system_prompt(skill_registry: SkillRegistry) -> str:
    """完整路由提示：标书技能清单 + 系统工具清单 + 输出字段说明。"""
    return f"""你是任务路由器。根据用户问题选择一种执行方式（execution_mode）：

1) skill — 需要「标书技能」中的业务能力（查标书、公章、签字、关键词等）。
2) system_tools — 需要「系统工具」（运行脚本、pip 安装依赖等），与标书 SKILL 无关。
3) general — 闲聊、常识、或不需要任何工具。

三者互斥；同一请求优先判断是否为标书业务(skill)，否则再判断是否需要系统工具(system_tools)。

{skill_registry.get_skills_catalog_section()}

{format_system_tools_catalog()}

你必须输出结构化字段：
- execution_mode: skill | system_tools | general
- skill_name: 仅 skill 时填写
- system_tool_names: 仅 system_tools 时填写（工具名列表；可留空表示启用全部系统工具供你选择）
- skill_description: 简述路由理由
"""


def route_user_request(
    skill_registry: SkillRegistry, model: Any, user_message: str
) -> SkillInfoFormat:
    """使用技能目录 + 系统工具目录做结构化路由。"""
    main_agent = create_agent(
        model,
        system_prompt=build_router_system_prompt(skill_registry),
        response_format=SkillInfoFormat,
        tools=get_registered_system_tools()
    )
    result = main_agent.invoke({"messages": [HumanMessage(user_message)]})
    print("route_user_request:", result)
    structured = result["structured_response"]
    if not isinstance(structured, SkillInfoFormat):
        raise TypeError("路由模型未返回 SkillInfoFormat")
    return structured


def resolve_system_tools_from_router(router: SkillInfoFormat) -> list[BaseTool]:
    """根据路由结果解析要挂载的系统工具；名称无效则跳过；空列表表示使用全部已注册系统工具。"""
    registry = system_tools_by_name()
    names = [n.strip() for n in (router.system_tool_names or []) if n and str(n).strip()]
    if not names:
        return list(registry.values())
    out: list[BaseTool] = []
    for n in names:
        t = registry.get(n)
        if t is not None:
            out.append(t)
    return out


def run_skill_by_name(model: Any, skill_name: str) -> dict:
    """按技能名加载 tools 与 SKILL 指令并执行一轮。"""
    tools, instructions = load_skill(skill_name)
    print(f"run_skill_by_name: {tools}, {instructions}")
    skill_agent = create_agent(
        model, tools=tools, system_prompt=SKILL_EXECUTOR_SYSTEM_PROMPT
    )
    return skill_agent.invoke({"messages": [HumanMessage(instructions)]})


def run_system_tools_agent(model: Any, user_message: str, tools: list[BaseTool]) -> dict:
    """挂载系统工具，基于用户原问题让模型自行决定调用（调用前须保证 tools 非空）。"""
    agent = create_agent(
        model, tools=tools, system_prompt=SYSTEM_TOOLS_EXECUTOR_SYSTEM_PROMPT
    )
    return agent.invoke({"messages": [HumanMessage(user_message)]})


def invoke_with_skill_or_llm(
    skill_registry: SkillRegistry,
    model: Any,
    user_message: str,
) -> dict:
    """
    自动路由：标书技能 → 系统工具 → 纯模型。

    返回:
        mode: 'skill' | 'system_tools' | 'general'
        router: 路由结构化结果
        invoke_result: create_agent(...).invoke 的完整返回值（含 messages）
    """
    router = route_user_request(skill_registry, model, user_message)

    if router.execution_mode == "skill":
        name = (router.skill_name or "").strip()
        if name and skill_registry.get_skill(name) is not None:
            return {
                "mode": "skill",
                "router": router,
                "invoke_result": run_skill_by_name(model, name),
            }
        return _invoke_general_only(model, user_message, router)

    if router.execution_mode == "system_tools":
        tools = resolve_system_tools_from_router(router)
        if not tools:
            return _invoke_general_only(model, user_message, router)
        return {
            "mode": "system_tools",
            "router": router,
            "invoke_result": run_system_tools_agent(model, user_message, tools),
        }

    return _invoke_general_only(model, user_message, router)


def _invoke_general_only(
    model: Any, user_message: str, router: SkillInfoFormat
) -> dict:
    agent = create_agent(model, system_prompt=GENERAL_AGENT_SYSTEM_PROMPT)
    return {
        "mode": "general",
        "router": router,
        "invoke_result": agent.invoke({"messages": [HumanMessage(user_message)]}),
    }
