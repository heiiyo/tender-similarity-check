from typing import List

from langchain_core.tools import tool

from agent.skill.skill import SkillContent, SkillDetail


@tool
def query_tender_keyword(bid_id, keyword):
    """
    在指定的标书中搜索特定关键词，并返回所有包含该关键词的页码列表。

    :param bid_id: 要查询的标书的唯一数字ID，例如 1。
    :param keyword: 需要在标书文本中搜索的关键词或短语，例如 "法人代表"。
    :return: 一个整数列表，包含所有找到关键词的页码，例如 [1, 5, 12]。如果未找到，则返回空列表。
    """
    return {"page_number": [1, 2, 3]}

@tool
def query_tender_signature(bid_id, page_number:List[int]):
    """
    检测标书指定页面上是否存在签字。

    :param bid_id: 要检测的标书的唯一数字ID。
    :param page_number: 一个整数列表，指定需要检测签名的页码，例如 [1, 5]。
    :return: 一个字典列表，每个字典代表一页的检测结果，包含页码(page_number)、是否存在签名(is_sign)和详细内容(content)。
    """
    return [{
        "page_number": 1,
        "is_sign": True,
        "content": "存在法人代表签字"
    },{
        "page_number": 2,
        "is_sign": True,
        "content": "存在委托人签字"
    },{
        "page_number": 1,
        "is_sign": False,
        "content": "法人代表签字缺失"
    }]

@tool
def get_contents_info(bid_id):
    """
    根据标书bid_id获取标书目录
    :param bid_id: 要检测的标书的唯一数字ID。
    :return: 返回标书目录的列表
    """
    return ""



def load_skill(skill_name):
    """
    加载任务执行手册以及对应的工具
    """
    skill: SkillDetail = SkillContent.get_skill(skill_name)
    # 获取工具
    tools = []
    tool_name_list = skill.get_tools()
    if tool_name_list:
        for tool_name in tool_name_list:
            tools.append(globals()[tool_name])
    # 添加系统工具
    # 加载手册
    instructions = skill.load_instructions()
    return tools, instructions
