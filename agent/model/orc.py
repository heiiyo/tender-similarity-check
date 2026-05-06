from langchain_core.messages import HumanMessage
from langchain_siliconflow import ChatSiliconFlow


orc_model = ChatSiliconFlow(
            base_url="https://api.siliconflow.cn/v1",
            api_key="sk-sdbwgllpqhbnijbotgyqsikuhowhmmuzpowxraulvasfexsv",
            model="PaddlePaddle/PaddleOCR-VL-1.5",
            temperature=0,
            max_tokens=1000,
            timeout=30
        )

def get_orc_model():
    return orc_model


def scan_orc_content(image_base64, prompt_text):
    message = HumanMessage(content=[
        {"type": "text", "text": prompt_text},
        {"type": "image", "source_type": "base64", "mime_type": "image/png", "data": image_base64}
    ])
    result = orc_model.invoke([message])
    return result.content