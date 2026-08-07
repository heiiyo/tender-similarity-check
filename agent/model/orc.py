from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_siliconflow import ChatSiliconFlow

from apps import AppContext
from apps.service.file_service import TenderInfo


def get_orc_model():
    """
    获取OCR模型实例（从AppContext中获取）
    """
    app_context = AppContext()
    if not hasattr(app_context, 'ocr_model') or app_context.ocr_model is None:
        # 如果尚未初始化，则创建临时实例（兼容旧代码）
        orc_model = ChatSiliconFlow(
            base_url="https://api.siliconflow.cn/v1",
            api_key="sk-sdbwgllpqhbnijbotgyqsikuhowhmmuzpowxraulvasfexsv",
            model="PaddlePaddle/PaddleOCR-VL-1.5",
            temperature=0,
            max_tokens=1000,
            timeout=300
        )
        return orc_model
    return app_context.ocr_model


def scan_orc_content(image_base64, prompt_text):
    """
    使用OCR模型识别图片内容

    :param image_base64: base64编码的图片数据
    :param prompt_text: 提示词文本
    :return: OCR识别结果
    """
    orc_model = get_orc_model()
    message = HumanMessage(content=[
        {"type": "text", "text": prompt_text},
        {"type": "image", "source_type": "base64", "mime_type": "image/png", "data": image_base64}
    ])
    result = orc_model.invoke([message])
    return result.contentss


def scan_orc_content_with_prompt(image_base64, prompt_text, response_format, tools=None):
    """
    使用OCR Agent识别图片内容并返回结构化结果
    
    :param image_base64: base64编码的图片数据
    :param prompt_text: 提示词文本
    :param response_format: 响应格式（Pydantic模型）
    :param tools: 可选的工具列表
    :return: OCR识别的结构化结果
    """
    # 初始化OCR Agent（用于结构化提取投标信息）
    app_context = AppContext()
    ocr_agent = create_agent(
        model=app_context.ocr_model,
        tools=tools or [],  # OCR Agent不需要额外工具，直接使用视觉能力
        system_prompt="""你是一个专业的投标文件信息提取助手。请从图片中提取关键信息并以JSON格式返回。
                        需要提取的字段说明：
                        1. project_name: 项目名称/标段名称（通常是页面中最醒目的标题）
                        2. bid_date: 投标截止时间或开标时间（格式：YYYY-MM-DD）
                        3. bidder: 投标人/投标单位全称
                        4. tenderer: 招标人/采购单位全称
                        5. legal_representative: 法定代表人或授权委托人姓名
                    
                        重要提示：
                        - 如果某个字段在图片中找不到明确对应的信息，请将该字段设为 null
                        - 不要编造或推测不存在的信息
                        - 保持原文的准确性，特别是公司名称和人名
                        - 只返回JSON对象，不要添加任何其他说明""",
        response_format=response_format)
    result = ocr_agent.invoke({"messages": [HumanMessage(content=[
        {"type": "text", "text": prompt_text},
        {"type": "image", "source_type": "base64", "mime_type": "image/png", "data": image_base64}
    ])]})
    
    # 返回结构化的结果
    return result
