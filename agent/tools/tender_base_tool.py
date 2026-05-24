import asyncio
import base64
import io
from typing import List

import numpy as np
from PIL import Image
from langchain_core.tools import tool

from agent.skill.skill import SkillContent, SkillDetail
from apps import AppContext
from apps.repository.entity.tender_entity import TenderTopic, TenderPDFImageEntity, SubBidPlagiarismCheckTask, \
    SubComplianceCheckTask, TenderComplianceRiskRecord
from apps.repository.entity.file_entity import FileRecordEntity
from apps.repository.minio_repository import get_object_bytes

from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__package__)

@tool
def query_tender_base_info(bid_id):
    """
    查询标书的基本信息，如投标人信息，招标人信息， 招标日期
    :param bid_id: 要查询的标书的唯一数字ID（tender_file_id）。
    """
    pass


@tool
def analyze_tender_page_with_ocr(bid_id: int, page_numbers: List[int], user_intent: str):
    """
    使用OCR视觉模型分析标书指定页面的内容，判断是否符合用户意图

    :param bid_id: 要分析的标书的唯一数字ID（tender_file_id）。
    :param page_numbers: 需要分析的页码列表，例如 [1, 5, 10]。
    :param user_intent: 用户意图描述，例如"分析是否有有效的证书信息"、"检查是否存在资质证书"等。
    :return: 一个字典列表，每个元素代表一页的分析结果，包含：
             - is_compliant (bool): 是否符合用户意图
             - page_number (int): 页码
             - check_basis (str): 检查依据和详细说明

             例如：[
               {"is_compliant": True, "page_number": 1, "check_basis": "检测到有效的ISO9001认证证书"},
               {"is_compliant": False, "page_number": 2, "check_basis": "未检测到相关证书信息"},
               ...
             ]
    """
    from agent.model.orc import scan_orc_content

    results = []

    try:
        app_context = AppContext()

        # 1. 从数据库获取指定页码的图片记录
        with app_context.db_session_factory() as session:
            image_records = session.query(TenderPDFImageEntity).filter(
                TenderPDFImageEntity.tender_file_id == bid_id,
                TenderPDFImageEntity.page_number.in_(page_numbers)
            ).order_by(TenderPDFImageEntity.page_number.asc()).all()

            if not image_records:
                logger.warning(f"标书 {bid_id} 在页码 {page_numbers} 中未找到对应的图片记录")
                return [{
                    "is_compliant": False,
                    "page_number": page,
                    "check_basis": f"第{page}页：未找到对应的图片记录"
                } for page in page_numbers]

            # 2. 遍历每一页进行OCR分析
            for record in image_records:
                try:
                    page_num = record.page_number
                    file_id = record.file_id

                    # 3. 根据file_id获取文件记录
                    file_record = session.get(FileRecordEntity, file_id)
                    if not file_record:
                        logger.warning(f"文件记录 {file_id} 不存在")
                        results.append({
                            "is_compliant": False,
                            "page_number": page_num,
                            "check_basis": f"第{page_num}页：文件记录不存在"
                        })
                        continue

                    # 4. 从MinIO获取图片数据
                    img_bytes = get_object_bytes(file_record.file_path)

                    # 5. 转换为base64用于OCR识别
                    base64_str = base64.b64encode(img_bytes).decode("utf-8")

                    # 6. 构建OCR提示词，结合用户意图
                    ocr_prompt = f"""请仔细分析这张图片，判断以下内容：
                    {user_intent}
                    
                    请提供详细的分析结果，包括：
                    1. 是否检测到相关内容
                    2. 检测到的具体内容是什么
                    3. 内容的有效性评估"""

                    # 7. 调用OCR模型进行识别
                    ocr_result = scan_orc_content(base64_str, prompt_text=ocr_prompt)

                    # 8. 解析OCR结果，判断是否符合用户意图
                    # 这里可以根据具体的用户意图做更精细的判断逻辑
                    # 目前采用简单的关键词匹配方式
                    ocr_text_lower = ocr_result.lower() if isinstance(ocr_result, str) else ""

                    # 判断是否合规（可以根据实际需求调整判断逻辑）
                    is_compliant = any(keyword in ocr_text_lower for keyword in ["证书", "资质", "有效", "认证"])

                    results.append({
                        "is_compliant": is_compliant,
                        "page_number": page_num,
                        "check_basis": f"第{page_num}页：{ocr_result}"
                    })

                    logger.info(f"标书 {bid_id} 第 {page_num} 页OCR分析完成")

                except Exception as page_error:
                    logger.error(f"标书 {bid_id} 第 {record.page_number} 页OCR分析失败: {str(page_error)}",
                                 exc_info=True)
                    results.append({
                        "is_compliant": False,
                        "page_number": record.page_number,
                        "check_basis": f"第{record.page_number}页：OCR分析失败 - {str(page_error)}"
                    })

        # 按页码排序
        results.sort(key=lambda x: x["page_number"])
        logger.info(f"标书 {bid_id} OCR分析完成，共分析 {len(results)} 页")
        return results

    except Exception as e:
        logger.error(f"标书 {bid_id} OCR分析整体失败: {str(e)}", exc_info=True)
        return [{
            "is_compliant": False,
            "page_number": page,
            "check_basis": f"OCR分析整体失败: {str(e)}"
        } for page in page_numbers]


@tool
def query_tender_topic(bid_id, keyword):
    """
    查询关键字是否在目录中存在
    :param bid_id: 要查询的标书的唯一数字ID（tender_file_id）。
    :param keyword: 要搜索的关键词。
    :return: 一个字典，包含以下键值对：
             - page_number (List[int]): 匹配关键词的页码列表
    """
    logger.info(f"query_tender_topic: {bid_id}, {keyword}")
    try:
        import re
        app_context = AppContext()
        with app_context.db_session_factory() as session:
            # 根据 tender_file_id 查询所有目录项
            topics = session.query(TenderTopic).filter(
                TenderTopic.tender_file_id == bid_id
            ).order_by(TenderTopic.start_page.asc()).all()
            
            if not topics:
                return {"page_number": []}
            
            # 遍历每一个目录项，搜索关键词
            matched_pages = []
            for topic in topics:
                if not topic.topic_name:
                    continue
                
                # 清理文本：去除多余空白字符
                clean_topic_name = re.sub(r'\s+', ' ', topic.topic_name.strip())
                clean_keyword = re.sub(r'\s+', ' ', keyword.strip())
                
                # 方法1：直接匹配（清理空白后）
                if clean_keyword.lower() in clean_topic_name.lower():
                    # 如果找到匹配，添加起始页码
                    if topic.start_page:
                        try:
                            start_page = int(topic.start_page)
                            matched_pages.append(start_page)
                        except ValueError:
                            pass
                    continue
                
                # 方法2：使用正则表达式模糊匹配（处理可能的分隔符）
                pattern_parts = [re.escape(char) for char in clean_keyword]
                flexible_pattern = r'\s*'.join(pattern_parts)
                
                if re.search(flexible_pattern, topic.topic_name, re.IGNORECASE):
                    if topic.start_page:
                        try:
                            start_page = int(topic.start_page)
                            matched_pages.append(start_page)
                        except ValueError:
                            pass
                    continue
            
            # 去重并排序
            matched_pages = sorted(list(set(matched_pages)))
            return {"page_number": matched_pages}
    
    except Exception as e:
        print(f"查询标书 {bid_id} 目录关键词 '{keyword}' 失败: {str(e)}")
        return {"page_number": []}


@tool
def query_tender_keyword(bid_id: int, keyword: str, page_number_list: List[int] = None):
    """
    用于查询标书内容中指定的关键词出现的页码。

    :param bid_id: 要查询的标书的唯一数字ID（tender_file_id）。
    :param keyword: 要搜索的关键词。
    :param page_number_list: 需要在哪些中查找关键字keyword。 如果全文搜索，默认为None,空
    :return: 一个字典，包含以下键值对：
             - page_number (List[int]): 匹配关键词的页码列表
    """
    try:
        import re
        app_context = AppContext()
        with app_context.db_session_factory() as session:
            # 根据 tender_file_id 查询所有页面的内容
            pages = None
            if page_number_list:
                pages = session.query(TenderPDFImageEntity).filter(
                    TenderPDFImageEntity.tender_file_id == bid_id,
                    TenderPDFImageEntity.page_number.in_(page_number_list)
                )
            else:
                pages = session.query(TenderPDFImageEntity).filter(
                    TenderPDFImageEntity.tender_file_id == bid_id
                ).order_by(TenderPDFImageEntity.page_number.asc()).all()
            if not pages:
                return {"page_number": []}
            
            # 遍历每一页，搜索关键词
            matched_pages = []
            for page in pages:
                if not page.page_context:
                    continue
                
                # 清理文本：去除多余空白字符，统一换行符
                clean_text = re.sub(r'\s+', ' ', page.page_context.strip())
                clean_keyword = re.sub(r'\s+', ' ', keyword.strip())
                print(f"clean_text-{clean_text}, clean_keyword-{clean_keyword}")
                # 方法1：直接匹配（清理空白后）
                if clean_keyword in clean_text:
                    matched_pages.append(page.page_number)
                    continue
                
                # 方法2：使用正则表达式模糊匹配（处理可能的分隔符）
                # 将关键词中的每个字符之间允许有任意空白字符
                pattern_parts = [re.escape(char) for char in clean_keyword]
                flexible_pattern = r'\s*'.join(pattern_parts)
                
                if re.search(flexible_pattern, page.page_context):
                    matched_pages.append(page.page_number)
                    continue
                
                # 方法3：分词匹配（适用于长关键词）
                # 如果关键词包含多个词，检查是否所有词都出现在文本中
                if len(clean_keyword) > 4:
                    # 按常见分隔符分割关键词
                    keyword_parts = re.split(r'[，,、\s]+', clean_keyword)
                    if all(part in clean_text for part in keyword_parts if len(part) > 1):
                        matched_pages.append(page.page_number)
            
            return {"page_number": matched_pages}
    
    except Exception as e:
        print(f"查询标书 {bid_id} 关键词 '{keyword}' 失败: {str(e)}")
        return {"page_number": []}


def is_red_color(image: Image.Image, threshold: float = 0.1) -> bool:
    """
    判断图片是否主要为红色（适合检测公章）

    :param image: PIL Image 对象
    :param threshold: 红色像素占比阈值，默认0.5（50%）
    :return: True 如果图片主要为红色，否则 False
    """
    try:
        # 转换为 RGB
        image = image.convert('RGB')
        pixels = np.array(image)

        # 提取 RGB 通道
        r, g, b = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]

        # 定义红色条件：R > G 且 R > B，且 R 值较高
        red_mask = (r > 100) & (r > g * 1.5) & (r > b * 1.5)

        # 计算红色像素占比
        red_ratio = np.sum(red_mask) / (pixels.shape[0] * pixels.shape[1])
        logger.info(f'is Red: {red_ratio > threshold}')
        return red_ratio > threshold
    except Exception as e:
        logger.error(f"判断颜色失败: {str(e)}")
        return False


def is_circular_shape(image: Image.Image, tolerance: float = 0.3) -> bool:
    """
    判断图片中的主要形状是否为圆形（适合检测公章）

    :param image: PIL Image 对象
    :param tolerance: 圆形容忍度，越小要求越严格，默认0.3
    :return: True 如果形状接近圆形，否则 False
    """
    try:
        import cv2

        # PIL 转 OpenCV
        img_array = np.array(image.convert('RGB'))
        img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # 转为灰度图
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        # 二值化
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

        # 查找轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return False

        # 找到最大的轮廓
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)

        # 过滤太小的轮廓
        if area < 100:
            return False

        # 计算周长
        perimeter = cv2.arcLength(largest_contour, True)

        if perimeter == 0:
            return False

        # 计算圆度（circularity）
        # 圆度公式：4 * π * area / perimeter^2
        # 完美圆形的圆度为 1，其他形状小于 1
        circularity = 4 * np.pi * area / (perimeter * perimeter)

        # 判断是否接近圆形（圆度 > 1 - tolerance）
        logger.info(f"圆度: {circularity > (1 - tolerance)}")
        return circularity > (1 - tolerance)

    except ImportError:
        # 如果没有安装 opencv，使用简化方法
        logger.warning("OpenCV 未安装，使用简化方法判断圆形")
        return _is_circular_simple(image)

    except Exception as e:
        logger.error(f"判断形状失败: {str(e)}")
        return False


def _is_circular_simple(image: Image.Image, tolerance: float = 0.3) -> bool:
    """
    简化版圆形判断方法（不依赖 OpenCV）

    :param image: PIL Image 对象
    :param tolerance: 宽高比容忍度
    :return: True 如果形状接近圆形，否则 False
    """
    try:
        # 转为灰度图
        image = image.convert('L')
        pixels = np.array(image)

        # 二值化
        binary = (pixels < 128).astype(int)

        # 找到非零像素的边界
        rows = np.any(binary, axis=1)
        cols = np.any(binary, axis=0)

        if not (np.any(rows) and np.any(cols)):
            return False

        ymin, ymax = np.where(rows)[0][[0, -1]]
        xmin, xmax = np.where(cols)[0][[0, -1]]

        bbox_height = ymax - ymin
        bbox_width = xmax - xmin

        if bbox_height == 0 or bbox_width == 0:
            return False

        # 计算宽高比，接近 1 表示接近正方形/圆形
        aspect_ratio = min(bbox_width, bbox_height) / max(bbox_width, bbox_height)

        # 计算填充率
        foreground_pixels = np.sum(binary > 0)
        bbox_area = bbox_height * bbox_width
        fill_ratio = foreground_pixels / bbox_area if bbox_area > 0 else 0

        # 圆形应该宽高比接近1，且填充率较高（约78.5%是完美圆形在正方形中的占比）
        return aspect_ratio > (1 - tolerance) and fill_ratio > 0.6

    except Exception as e:
        logger.error(f"简化版圆形判断失败: {str(e)}")
        return False


async def detect_seal_for_page(page_number, file_id, model, bid_id):
    """
    异步检测单页图片中的公章
    
    :param page_number: 页码
    :param file_id: 文件ID
    :param model: YOLO模型实例
    :param bid_id: 标书ID
    :return: 检测结果字典
    """
    try:
        app_context = AppContext()
        
        # 为每个页面创建独立的数据库会话，用完即关闭
        with app_context.db_session_factory() as session:
            # 根据file_id获取文件记录
            file_record = session.get(FileRecordEntity, file_id)
            if not file_record:
                logger.warning(f"文件记录 {file_id} 不存在")
                return {
                    "page_number": page_number,
                    "is_sign": False,
                    "seal_count": 0,
                    "text": f"第{page_number}页：文件记录不存在"
                }

            from apps.repository.minio_repository import get_object_bytes
            
            loop = asyncio.get_event_loop()
            
            # 从 MinIO 获取字节流（同步操作，放入线程池）
            img_bytes = await loop.run_in_executor(
                None, 
                lambda: get_object_bytes(file_record.file_path)
            )

            # 用 PIL 打开图片并转换为 RGB
            image = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            # 转换为 NumPy 数组
            img_array = np.array(image)
            
            # 使用YOLO模型检测公章（同步操作，放入线程池）
            results = await loop.run_in_executor(
                None,
                lambda: model.predict(source=img_array, conf=0.6, verbose=False)
            )

            seal_count = 0
            confidence = 0
            detected_text = ""
            logger.info(f"第{page_number}页，检测结果：{results}")
            # 处理检测结果
            for result in results:
                boxes = result.boxes
                if len(boxes) > 0:
                    for box in boxes:
                        # 获取置信度

                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()

                        # 使用PIL截图印章部分用于OCR识别
                        crop_box = (
                            max(0, int(x1)),
                            max(0, int(y1)),
                            min(image.width, int(x2)),
                            min(image.height, int(y2))
                        )

                        # 裁剪印章区域
                        seal_img = image.crop(crop_box)
                        if is_red_color(seal_img) and is_circular_shape(seal_img):
                            confidence = float(box.conf[0])
                            seal_count += 1
                        #
                        # # 转换为字节流用于OCR
                        # seal_img_buffer = io.BytesIO()
                        # seal_img.save(seal_img_buffer, format='PNG')
                        # seal_img_bytes = seal_img_buffer.getvalue()
                        #
                        # # OCR识别（同步操作，放入线程池）
                        # base64_str = base64.b64encode(seal_img_bytes).decode("utf-8")
                        # from agent.model.orc import scan_orc_content
                        # detected_text = await loop.run_in_executor(
                        #     None,
                        #     lambda: scan_orc_content(base64_str, prompt_text="识别公章内容")
                        # )
                        
            # 构建结果
            item_result = {
                "page_number": page_number,
                "is_sign": seal_count > 0,
                "seal_count": seal_count,
                "confidence": confidence,
                "text": detected_text if detected_text else f"第{page_number}页：检测到 {seal_count} 个公章"
            }
            
            logger.info(f"标书 {bid_id} 第 {page_number} 页检测结果: {item_result}")
            return item_result
        
    except Exception as page_error:
        logger.error(f"标书 {bid_id} 第 {page_number} 页检测失败: {str(page_error)}", exc_info=True)
        return {
            "page_number": page_number,
            "is_sign": False,
            "seal_count": 0,
            "confidence": 0,
            "text": f"第{page_number}页：检测失败 - {str(page_error)}"
        }


def save_compliance_risk_records(
        tender_file_id: int,
        rule_id: int,
        result_list
):
    """
    保存合规检测风险记录到数据库

    :param tender_file_id: 标书文件ID
    :param rule_id: 规则ID
    :param result_list: 检测结果列表，包含items属性，每个item包含check_basis、page_number、is_compliant等字段
    """
    try:
        app_context = AppContext()

        with app_context.db_session_factory() as session:
            sub_task: SubComplianceCheckTask = session.query(SubComplianceCheckTask).filter(
                SubComplianceCheckTask.tender_file_id == tender_file_id
            ).first()
            risk_records = []

            # 遍历检测结果，创建风险记录
            for item in result_list:
                # is_compliant为False表示有风险（不合规），为True表示无风险（合规）
                # 数据库中：1-合规；0-不合规
                is_compliant_value = 1 if item.get("is_sign", 0) else 0
                risk_record = TenderComplianceRiskRecord(
                    sub_compliance_check_task_id=1,
                    tender_file_id=tender_file_id,
                    bid_plagiarism_check_task_id=1,
                    check_basis=item.get("text", ""),
                    page_number=item.get("page_number", 0),
                    is_compliant=is_compliant_value,
                    confidence=item.get("confidence", 1.0),
                    rule_id=rule_id
                )
                risk_records.append(risk_record)

            # 批量插入数据库
            if risk_records:
                session.add_all(risk_records)
                session.commit()
                logger.info(f"成功保存 {len(risk_records)} 条合规风险记录")
    except Exception as e:
        logger.error(f"保存合规风险记录失败: {str(e)}", exc_info=True)
        raise

@tool
def check_official_seal(bid_id: int, rule_id: int):
    """
    用于检测标书是否盖有公章，根据标书id检测标书每一页的盖章情况
    
    :param bid_id: 要检测的标书的唯一数字ID（tender_file_id）。
    :param rule_id: 对应的规则id。
    :return: 一个字典列表，每个元素代表一页的检测结果，包含：
             - page_number (int): 页码
             - is_sign (bool): 是否检测到公章
             - seal_count (int): 检测到的公章数量
             - text (str): 检测详情描述
             
             例如：[
               {"page_number": 1, "is_sign": True, "seal_count": 2, "text": "第1页：检测到2个公章"},
               {"page_number": 2, "is_sign": False, "seal_count": 0, "text": "第2页：未检测到公章"},
               ...
             ]
    """
    from ultralytics import YOLO
    
    # try:
    app_context = AppContext()

    # 1. 加载YOLO模型（只需加载一次）
    model_path = AppContext.project_root / 'models/Seal_inspection/best.pt'
    model = YOLO(str(model_path))

    # 2. 从数据库获取标书的所有图片记录（一次性查询，提取必要字段）
    with app_context.db_session_factory() as session:
        image_records = session.query(TenderPDFImageEntity).filter(
            TenderPDFImageEntity.tender_file_id == bid_id
        ).order_by(TenderPDFImageEntity.page_number.asc()).all()

        if not image_records:
            logger.warning(f"标书 {bid_id} 没有找到对应的图片记录")
            return []

        # 提前提取需要的字段，避免传递整个ORM对象
        page_tasks_data = [
            {"page_number": record.page_number, "file_id": record.file_id}
            for record in image_records[0: 4]
        ]

        logger.info(f"标书 {bid_id} 共有 {len(page_tasks_data)} 页需要检测")

    # 3. 使用协程并发检测所有页面
    async def run_concurrent_detection():
        # 创建信号量限制并发数，避免过多并发导致内存溢出
        semaphore = asyncio.Semaphore(5)

        async def detect_with_semaphore(task_data):
            async with semaphore:
                # 直接调用async函数，不需要额外的session管理
                return await detect_seal_for_page(
                    task_data["page_number"],
                    task_data["file_id"],
                    model,
                    bid_id
                )

        # 并发执行所有页面的检测任务
        tasks = [detect_with_semaphore(task_data) for task_data in page_tasks_data]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果和异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"第 {i+1} 页检测异常: {str(result)}")
                processed_results.append({
                    "page_number": page_tasks_data[i]["page_number"] if i < len(page_tasks_data) else 0,
                    "is_sign": False,
                    "seal_count": 0,
                    "text": f"检测异常: {str(result)}"
                })
            else:
                processed_results.append(result)

        # 按页码排序
        processed_results.sort(key=lambda x: x["page_number"])
        return processed_results

    # 运行异步任务
    out_results = asyncio.run(run_concurrent_detection())

    logger.info(f"标书 {bid_id} 公章检测完成，共检测 {out_results} ")
    save_compliance_risk_records(bid_id, rule_id, out_results)
    return {
            "is_sign": True,
            "text": f"检测完毕"
        }
    
    # except Exception as e:
    #     logger.error(f"标书 {bid_id} 公章检测整体失败: {str(e)}", exc_info=True)
    #     return [{"page_number": 0, "is_sign": False, "seal_count": 0, "text": f"检测失败: {str(e)}"}]


@tool
def check_tender_signature(bid_id, page_number: List[int]):
    """
    检测标书指定页面上是否存在签字。
    :param bid_id: 要检测的标书的唯一数字ID。
    :param page_number: 一个整数列表，指定需要检测签名的页码，例如 [1, 5]。
    :return: 一个字典列表，每个字典代表一页的检测结果，包含页码(page_number)、是否存在签名(is_sign)和详细内容(content)。
    """
    # return [{"page_number": page,
    #     "is_sign": True,
    #     "content": "该页有签名"
    #     } for page in page_number]
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
    
    :param bid_id: 要检测的标书的唯一数字ID（tender_file_id）。
    :return: 返回标书目录的列表，每个元素包含目录名称、起始页码和结束页码。
             例如：[{"topic_name": "第一章", "start_page": 1, "end_page": 10}, ...]
             如果未找到目录，则返回空列表。
    """
    try:
        app_context = AppContext()
        with app_context.db_session_factory() as session:
            # 根据 tender_file_id 查询目录信息，按起始页码排序
            topics = session.query(TenderTopic).filter(
                TenderTopic.tender_file_id == bid_id
            ).order_by(TenderTopic.start_page.asc()).all()
            
            if not topics:
                return []
            
            # 构建返回目录列表
            topic_list = []
            for topic in topics:
                topic_list.append({
                    "topic_name": topic.topic_name,
                    "start_page": int(topic.start_page) if topic.start_page else None,
                    "end_page": int(topic.end_page) if topic.end_page else None
                })
            
            return topic_list
    
    except Exception as e:
        # 记录错误但不中断流程
        print(f"获取标书 {bid_id} 目录失败: {str(e)}")
        return []



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
    from agent.tools.system_tool import get_registered_system_tools
    tools.extend(get_registered_system_tools())
    # 加载手册
    instructions = skill.load_instructions()
    return tools, instructions
