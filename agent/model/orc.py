from langchain_core.messages import HumanMessage
from langchain_siliconflow import ChatSiliconFlow

from apps import AppContext


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