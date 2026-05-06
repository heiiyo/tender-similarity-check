import base64
from typing import List

import fitz
import numpy as np
from langchain_core.tools import tool

from agent.skill.skill import SkillContent, SkillDetail
from agent.tools.system_tool import get_registered_system_tools
from apps import AppContext


@tool
def query_tender_keyword(bid_id, keyword):
    """
    在指定的标书中搜索特定关键词，并返回所有包含该关键词的页码列表。

    :param bid_id: 要查询的标书的唯一数字ID，例如 1。
    :param keyword: 需要在标书文本中搜索的关键词或短语，例如 "法人代表"。
    :return: 一个整数列表，包含所有找到关键词的页码，例如 [1, 5, 12]。如果未找到，则返回空列表。
    """
    return {"page_number": [1]}


@tool
def check_official_seal(bid_id):
    """
    用于检测标书是否该盖有公章, 根据标书id检测标书页面盖公章的情况
    :param bid_id: 要检测的标书的唯一数字ID。
    """
    from ultralytics import YOLO
    file_path = AppContext.project_root / 'documents/扫描件建筑领域知识问答场景建设技术标.pdf'
    doc = fitz.open(str(file_path))
    zoom = 3.0
    model_path = AppContext.project_root / 'models/Seal_inspection/best.pt'
    model = YOLO(str(model_path))
    out_results = []
    for page_num, page in enumerate(doc):
        if page_num > 3:
            break
        mat = fitz.Matrix(zoom, zoom)
        pix: fitz.Pixmap = page.get_pixmap(matrix=mat)
        # 预测
        img_bytes = pix.samples  # 或者 pix.tobytes()
        # 2. 将 bytes 转换为 NumPy 数组，并重塑为 (height, width, channels) 的图像格式
        # 注意：OpenCV/NumPy 默认使用 BGR，但 tobytes() 是 RGB，YOLO 内部会自动处理转换
        img = np.frombuffer(img_bytes, dtype=np.uint8).reshape((pix.h, pix.w, 3))
        results = model.predict(source=img, conf=0.6)
        num = 0
        item_result = {"page_number": page_num+1, "is_sign": False, "text": ""}
        for result in results:
            boxes = result.boxes  # 获取边界框
            if len(boxes) > 0:
                for box in boxes:
                    num += 1
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist() # 坐标
                    # 截图印章部分
                    rect = fitz.Rect(x1/zoom, y1/zoom, x2/zoom, y2/zoom)
                    pix_rect: fitz.Pixmap = page.get_pixmap(matrix=mat, clip=rect)
                    # 保存截图
                    # pix_rect.save(AppContext.project_root / f"documents/images/{page_num}.png")
                    img_bytes = pix_rect.tobytes("png")
                    # 3. 将二进制数据转换为 Base64 字符串
                    # base64_str = base64.b64encode(img_bytes).decode("utf-8")
                    # from agent.model.orc import scan_orc_content
                    # orc提取文字
                    # item_result['text'] = scan_orc_content(base64_str, prompt_text="识别公章内容")
        if num > 0:
            item_result['is_sign'] = True
        else:
            item_result['is_sign'] = False
        print(f"检测标书-页码-{page_num+1}: {item_result}")
        out_results.append(item_result)
    out_results.append({"page_number": 384, "is_sign": False, "text": ""})
    return out_results


@tool
def check_tender_signature(bid_id, page_number:List[int]):
    """
    检测标书指定页面上是否存在签字。
    :param bid_id: 要检测的标书的唯一数字ID。
    :param page_number: 一个整数列表，指定需要检测签名的页码，例如 [1, 5]。
    :return: 一个字典列表，每个字典代表一页的检测结果，包含页码(page_number)、是否存在签名(is_sign)和详细内容(content)。
    """
    model_dir = AppContext.project_root / 'models/signiture'
    from transformers import pipeline as hf_pipeline
    detector = hf_pipeline(
        task="object-detection",
        model=str(model_dir),
        device_map="auto",
    )
    results = []
    try:
        
        for page in page_number:
            image_path = AppContext.project_root / "documents/signature/签字1.png"

            if not image_path.exists():
                # 如果文件不存在，返回所有页码未检测到签名的结果
                results.append({
                    "page_number": page,
                    "is_sign": False,
                    "content": "图片文件不存在"
                })
                continue
            detections = detector(str(image_path))
            # 根据检测结果判断是否有签字
            # 通常 object-detection 会返回包含 label, score, box 的列表
            has_signature = len(detections) > 0 and any(d['score'] > 0.5 for d in detections)

            content_desc = "检测到签字" if has_signature else "未检测到签字"
            results.append({
                "page_number": page,
                "is_sign": has_signature,
                "content": content_desc
            })
            
    except Exception as e:
        for page in page_number:
            results.append({
                "page_number": page,
                "is_sign": False,
                "content": f"检测失败: {str(e)}"
            })

    return results


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
    skill: SkillDetail | None = SkillContent.get_skill(skill_name)
    if skill is None:
        raise ValueError(f"未知技能: {skill_name}")
    # 获取工具
    tools = []
    tool_name_list = skill.get_tools()
    if tool_name_list:
        for tool_name in tool_name_list:
            tools.append(globals()[tool_name])
    # 添加系统工具
    tools.extend(get_registered_system_tools())
    # 加载手册
    instructions = skill.load_instructions()
    return tools, instructions
