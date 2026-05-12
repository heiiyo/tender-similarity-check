"""
用户请求编排：路由模型在「标书技能 / 系统工具 / 纯模型」间选择；
命中技能则 load_skill；命中系统工具则挂载对应工具与用户原问题交互。
"""
import re
from typing import Any, Mapping

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool

from agent.format.out_format import (
    SkillComplianceFormat,
    SkillComplianceListFormat,
    SkillInfoFormat,
)
from agent.skill.skill import SkillRegistry
from agent.tools.system_tool import format_system_tools_catalog, system_tools_by_name, get_registered_system_tools
from agent.tools.tender_base_tool import load_skill

SKILL_EXECUTOR_SYSTEM_PROMPT = """
你是一个执行引擎，不是聊天机器人。
你的任务是按 SKILL 手册完成必要步骤，需要事实时必须调用工具。

【重要禁令】
1. 禁止在回复中描述你的思考过程（例如：不要说“让我来调用工具”、“我正在查找”）。
2. 禁止在未调用工具的情况下，臆造工具才会给出的检测结果。
3. 需要查询或检测时，必须实际调用工具并取得返回后再下结论。

【执行规则】
- 凡依赖标书数据、公章/签字/关键词等检测的，必须先调用相应工具。
- 流程结束后，你必须产出结构化字段 `items`：数组，每项含 is_compliant、check_basis。
- 单项结论时 `items` 仅含一条即可；多页/多项须分项列出多条。
- 每条 check_basis 须紧扣工具返回（页码、字段、是否命中等），不得臆造。
"""

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


def apply_instruction_params(
    instructions: str, params: Mapping[str, Any] | None
) -> str:
    """
    用 params 补全 SKILL 手册中的占位符。占位符与 skills 中常见写法一致：`{{key}}`（如 {{query}}、{{file_id}}）。
    未出现在 params 中的占位符保持原样，便于发现缺参。
    """

    if not params:
        return instructions

    def _replace(m: re.Match) -> str:
        key = m.group(1).strip()
        if key in params:
            return str(params[key])
        return m.group(0)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", _replace, instructions)


def extract_skill_compliance_items(invoke_result: dict) -> list[SkillComplianceFormat]:
    """从 ``run_skill_by_name`` 的 invoke 结果中取出合规条目列表。"""
    sr = invoke_result.get("structured_response")
    if isinstance(sr, SkillComplianceListFormat):
        return list(sr.items)
    if isinstance(sr, SkillComplianceFormat):
        return [sr]
    raise TypeError(
        "structured_response 应为 SkillComplianceListFormat 或 SkillComplianceFormat，"
        f"实际为 {type(sr).__name__}"
    )


def run_skill_by_name(
    model: Any,
    skill_name: str,
    instruction_params: Mapping[str, Any] | None = None
):
    """按技能名加载 tools 与 SKILL 指令执行一轮；结构化结果为 ``SkillComplianceListFormat``（items 数组）。

    instruction_params: 用于替换手册正文中的 `{{key}}` 占位符，例如
    ``{"query": "审计报表", "file_id": 1}`` 对应 ``{{query}}``、``{{file_id}}``。
    """
    print(f"run_skill_by_name: model-{model}")
    print(f"run_skill_by_name: skill_name-{skill_name}")
    tools, instructions = load_skill(skill_name)
    final_instructions = apply_instruction_params(instructions, instruction_params)
    print(f"run_skill_by_name: final_instructions-{final_instructions}")
    skill_agent = create_agent(
        model,
        tools=tools,
        system_prompt=SKILL_EXECUTOR_SYSTEM_PROMPT,
        response_format=SkillComplianceListFormat,
    )
    result = skill_agent.invoke({"messages": [HumanMessage(content=final_instructions)]})
    print(f"run_skill_by_name: result-{result}")
    return result


def run_system_tools_agent(model: Any, user_message: str, tools: list[BaseTool]) -> dict:
    """挂载系统工具，基于用户原问题让模型自行决定调用（调用前须保证 tools 非空）。"""
    agent = create_agent(
        model, tools=tools, system_prompt=SYSTEM_TOOLS_EXECUTOR_SYSTEM_PROMPT,
        response_format = SkillComplianceListFormat
    )
    return agent.invoke({"messages": [HumanMessage(user_message)]})


def invoke_with_skill_or_llm(
    skill_registry: SkillRegistry,
    model: Any,
    user_message: str,
    *,
    instruction_params: Mapping[str, Any] | None = None,
) -> dict:
    """
    自动路由：标书技能 → 系统工具 → 纯模型。

    instruction_params: 当路由为 skill 时，传入 ``run_skill_by_name`` 用于补全 SKILL 中 ``{{key}}`` 占位符。

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
                "invoke_result": run_skill_by_name(
                    model, name, instruction_params=instruction_params
                ),
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
