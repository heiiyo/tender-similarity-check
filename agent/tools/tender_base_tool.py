from typing import List

import fitz
import numpy as np
from langchain_core.tools import tool

from agent.skill.skill import SkillContent, SkillDetail
from apps import AppContext


@tool
def query_tender_keyword(bid_id, keyword):
    """
    在指定的标书中搜索特定关键词，并返回所有包含该关键词的页码列表。

    :param bid_id: 要查询的标书的唯一数字ID，例如 1。
    :param keyword: 需要在标书文本中搜索的关键词或短语，例如 "法人代表"。
    :return: 一个整数列表，包含所有找到关键词的页码，例如 [1, 5, 12]。如果未找到，则返回空列表。
    """
    return {"page_number": [1, 2, 3]}

def check_official_seal(bid_id):
    """
    检测标书是否该盖有公章
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
        mat = fitz.Matrix(zoom, zoom)
        pix: fitz.Pixmap = page.get_pixmap(matrix=mat)
        # 预测
        img_bytes = pix.samples  # 或者 pix.tobytes()
        # 2. 将 bytes 转换为 NumPy 数组，并重塑为 (height, width, channels) 的图像格式
        # 注意：OpenCV/NumPy 默认使用 BGR，但 tobytes() 是 RGB，YOLO 内部会自动处理转换
        img = np.frombuffer(img_bytes, dtype=np.uint8).reshape((pix.h, pix.w, 3))
        results = model.predict(source=img, conf=0.6)
        num = 0
        item_result = {"page_number": page_num, "is_sign": False}
        for result in results:
            boxes = result.boxes  # 获取边界框
            if len(boxes) > 0:
                for box in boxes:
                    num += 1
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist() # 坐标
                    # # --- 核心修改部分 ---
                    # # 方案 A：直接用 Pixmap 裁剪 (最快，推荐)
                    # # fitz.Rect 需要浮点数坐标
                    # rect = fitz.Rect(x1, y1, x2, y2)
                    # # 从原始 pix 中裁剪出印章区域
                    # seal_pixmap = fitz.Pixmap(pix, rect)
                    # conf = box.conf  # 置信度
                    # print(f"检测到印章，位置: {x1, y1, x2, y2}, 置信度: {conf}")
                    # seal_bytes = seal_pixmap.tobytes("png")
        if num > 0:
            item_result['is_sign'] = True
        else:
            item_result['is_sign'] = False
        out_results.append(item_result)
    return out_results


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
