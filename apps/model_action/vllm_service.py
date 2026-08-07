import asyncio
import json
import random
import re
from abc import ABC
from typing import Union, List, Dict, Any

from sqlalchemy import and_

from agent.format.out_format import SkillComplianceListFormat
from agent.skill.skill_runner import run_skill_by_name
from apps import AppContext
from apps.repository.entity.file_entity import FileRecordEntity
from apps.repository.entity.tender_entity import TenderPDFImageEntity, TenderComplianceRiskRecord, \
    SubComplianceCheckTask, TenderRuleConfiguration
from apps.tools.file_tool import read_md_file

from pathlib import Path

from logger_config import get_logger

logger = get_logger(name=__package__)

# 获取当前文件的绝对路径
current_file = Path(__file__)

# 获取当前文件所在目录
current_dir = current_file.parent

# 获取上一级目录
parent_dir = current_dir.parent

app_context = AppContext()


class BaseMessage(ABC):
    def __init__(self, content, message_list=None):
        self.type: str = "text"
        self.role: str = "user"
        self.content: Union[str, Dict[str, Any], List[Dict[str, Any]]] = content
        self.message_list = []
        if message_list:
            if isinstance(message_list, BaseMessage):
                self.message_list.append(message_list)
            else:
                self.message_list.extend(message_list)

    def to_dict(self) -> dict:
        """
        将消息序列化为 API 可消费的 JSON 字典
        """
        if isinstance(self.content, str):
            content_message = [{
                "type": self.type,
                self.type: self.content
            }]
        elif isinstance(self.content, Dict):
            content_message = [{
                "type": self.type,
                self.type: self.content
            }]
        else:
            content_message = [{
                "type": self.type,
                self.type: item
            } for item in self.content]
        data = {
            "role": self.role,  # ⭐ 固定映射为 OpenAI 的角色
            "content": content_message
        }

        if self.message_list and len(self.message_list) > 0:
            for message in self.message_list:
                data["content"].extend(message.to_dict()["content"])
        return data


class AIMessage(BaseMessage):
    pass


class StringAIMessage(BaseMessage):
    pass


class HumanMessage(BaseMessage):

    def __init__(self, content: Union[str, List[Dict[str, Any]]], message_list=None):
        super().__init__(content, message_list)


class ImageMessage(BaseMessage):
    # 角色标识（固定值）
    def __init__(self, file_url: str, message=None):
        super().__init__(file_url, message)
        self.type = "image_url"


class SystemMessage(BaseMessage):
    # 角色标识（固定值）
    def __init__(self, content: str, message=None):
        super().__init__(content, message)
        self.type: str = "text"
        self.role: str = "system"


class PromptTemplate:
    def __init__(self, messages: List[BaseMessage]):
        self.messages = messages

    def to_dict(self):
        template_mes = []
        for message in self.messages:
            template_mes.append(message.to_dict())
        return template_mes


def handle_rule(rule: TenderRuleConfiguration,
                      tender_file_id,
                      sub_compliance_check_task_id: int,
                      bid_plagiarism_check_task_id: int):
    # 使用skill检查规则
    result = run_skill_by_name(
        app_context.agent_model,
        rule.skill_name,
        instruction_params={"bid_id": tender_file_id, "rule_id": rule.id},
    )
    logger.info(f"标书 {tender_file_id} 规则 {rule.id} 结果：{result}")
    result_list: SkillComplianceListFormat = result["structured_response"]
    print(f"handle_rule: result-{result}")
    if result_list.result_type == 1:
        # 将结果写入数据库
        with app_context.db_session_factory() as session:
            risk_records = []
            for item in result_list.items:

                is_compliant_value = 1 if item.is_compliant else 0

                risk_record = TenderComplianceRiskRecord(
                    sub_compliance_check_task_id=sub_compliance_check_task_id,
                    tender_file_id=tender_file_id,
                    bid_plagiarism_check_task_id=bid_plagiarism_check_task_id,
                    check_basis=item.check_basis,
                    page_number=item.page_number if hasattr(item, 'page_number') else None,
                    is_compliant=is_compliant_value,
                    rule_id=rule.id
                )
                risk_records.append(risk_record)

            if risk_records:
                session.add_all(risk_records)
                session.commit()
    return result


async def handel_topic(image_url_list):
    # 使用大模型解析文本标题
    llm_model = app_context.llm_model
    sys_str = read_md_file(f"{parent_dir}/model_action/action/topic.md")
    sys_message = SystemMessage(sys_str)
    i_message = ImageMessage(image_url_list, BaseMessage("帮我分析出这些图片中目录的一级标题"))
    prompt_template = PromptTemplate([sys_message, i_message])
    result = await llm_model.invoke(prompt_template)
    return extract_inner_json(result["choices"][0]["message"]["content"])["topic"]


async def handel_compliance_check(image_url_list, remake):
    # 使用大模型解析文本标题
    llm_model = app_context.llm_model
    sys_message = SystemMessage(read_md_file(f"{parent_dir}/model_action/action/rules_check.md"))
    iMessage = ImageMessage(image_url_list,
                            BaseMessage(remake))
    prompt_template = PromptTemplate([sys_message, iMessage])
    result = await llm_model.invoke(prompt_template)
    logger.info(f"handel_compliance_check: {image_url_list[0]}；结果：{result}")
    return extract_inner_json(result["choices"][0]["message"]["content"])


async def summarize_answer():
    # 使用大模型解析文本标题
    llm_model = app_context.llm_model
    sys_str = read_md_file(f"{parent_dir}/model_action/action/summarize_answer.md")
    # sys_str = sys_str.replace("{{topic_list}}", json.dumps(topics, ensure_ascii=False))
    sys_message = SystemMessage(sys_str)
    i_message = BaseMessage("帮我分析出这些图片中目录的一级标题")
    prompt_template = PromptTemplate([sys_message, i_message])
    result = await llm_model.invoke(prompt_template)
    return extract_inner_json(result["choices"][0]["message"]["content"])


def extract_inner_json(response_text):
    """
    防御性解析：从含有推理过程或杂质的混合文本中提取标准 JSON
    修复版：修正 rfind 定位错误，增加 XML/HTML 标签清理
    """
    if not response_text or not response_text.strip():
        raise ValueError("响应内容为空")

    # 策略 1: 尝试直接解析整个清洗后的文本
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass
    # 0. 预处理：清洗常见的模型残留标签 (如 , , 等)
    # 保留纯 JSON 结构前的可能内容，防止干扰

    # 策略 2: 优先寻找 Markdown 代码块中的 JSON (```json 或 ```)
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"Markdown 代码块内 JSON 解析失败: {e}")
            # 即使失败也继续尝试后续策略

    start_idx = response_text.find('</think>')
    candidate = response_text[start_idx:]
    candidate = candidate.replace('</think>', '')
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        logger.warning(f"</think>代码块内 JSON 解析失败: {e}")

    # 策略 3: 兜底 - 查找第一个 { 到最后一个 } (修正了 rfind -> find)
    # 注意：如果是数组开始 [], 也可以用类似的逻辑，这里主要针对对象 {}
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}') + 1

    if start_idx != -1 and end_idx > start_idx + 1:
        candidate = response_text[start_idx:end_idx]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # 如果还是失败，可能是括号不匹配严重，打印日志辅助调试
            logger.error(f"无法提取有效 JSON 数据，候选片段前 100 字:\n{candidate[:100]}")

    raise ValueError(f"解析失败，已尝试多种策略")





