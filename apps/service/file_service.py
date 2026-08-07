import asyncio
import base64
import datetime
import os
import re
import tempfile
import uuid
import zipfile
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from apps import AppContext
from apps.repository.entity.file_entity import FileRecordEntity
from apps.repository.entity.tender_entity import TenderPDFImageEntity
from apps.repository.minio_repository import get_file_url
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__package__)

app_context = AppContext()
minio_client = app_context.minio_client
_executor = ThreadPoolExecutor(max_workers=20)


class TenderInfo(BaseModel):
    """投标信息数据模型"""
    project_name: Optional[str] = Field(None, description="项目名称")
    bid_date: Optional[str] = Field(None, description="投标时间/开标时间")
    bidder: Optional[str] = Field(None, description="投标人/投标单位")
    tenderer: Optional[str] = Field(None, description="招标人/招标单位")
    legal_representative: Optional[str] = Field(None, description="法定代表人或委托代理人")


def extract_tender_info_from_first_page(file_path: str, mime_type: str) -> Optional[TenderInfo]:
    """
    从文件第一页提取完整的投标信息
    :param file_path: 文件路径
    :param mime_type: 文件类型 (pdf, docx, doc等)
    :return: TenderInfo对象，包含项目名称、投标时间、投标人、招标人、法定代表人等信息，失败返回None
    """
    try:
        if mime_type.lower() in ['pdf']:
            return _extract_tender_info_from_pdf(file_path)
        elif mime_type.lower() in ['docx', 'doc']:
            return _extract_tender_info_from_docx(file_path)
        else:
            logger.warning(f"不支持的文件类型: {mime_type}")
            return None
    except Exception as e:
        logger.error(f"提取投标信息失败: {str(e)}", exc_info=True)
        return None


def _extract_tender_info_from_pdf(file_path: str) -> Optional[TenderInfo]:
    """
    从PDF文件第一页提取投标信息（统一使用OCR直接提取结构化信息）
    策略：
    1. 将PDF第一页转换为图片
    2. 使用OCR模型直接识别并提取结构化投标信息
    """
    try:
        logger.info("开始将PDF第一页转换为图片进行OCR识别")
        image_bytes = pdf_page_to_image(file_path, page_number=0, dpi=300)
        
        logger.info("开始OCR识别并提取投标信息")
        tender_info = ocr_extract_tender_info(image_bytes)

        if not tender_info or (not any([tender_info.project_name, tender_info.bidder, tender_info.tenderer])):
            logger.warning("OCR未能提取到有效的投标信息")
            return None
        
        return tender_info

    except Exception as e:
        logger.error(f"PDF投标信息提取失败: {str(e)}", exc_info=True)
        return None


def _extract_tender_info_from_docx(file_path: str) -> Optional[TenderInfo]:
    """
    从Word文档第一页提取投标信息
    策略：提取文本后使用LLM解析
    """
    try:
        from docx import Document

        doc = Document(file_path)
        
        first_page_text = ""
        char_count = 0
        
        for paragraph in doc.paragraphs:
            if paragraph.text and paragraph.text.strip():
                text = paragraph.text.strip()
                first_page_text += text + "\n"
                char_count += len(text)
                
                if char_count > 2000:
                    break

        if not first_page_text or len(first_page_text.strip()) < 10:
            logger.warning("Word文档第一页文本内容为空或过短")
            return None

        logger.info(f"从Word文档提取了 {len(first_page_text)} 字符，开始LLM解析")
        return _parse_tender_info_with_llm(first_page_text)

    except ImportError:
        logger.error("未安装python-docx库，无法解析Word文档")
        return None
    except Exception as e:
        logger.error(f"Word投标信息提取失败: {str(e)}", exc_info=True)
        return None


def _parse_tender_info_with_llm(text: str) -> Optional[TenderInfo]:
    """
    使用LLM从文本中解析投标信息
    :param text: 待解析的文本内容
    :return: TenderInfo对象，失败返回None
    """
    try:
        from apps.model_action.llm import LLMModel
        from apps.model_action.vllm_service import PromptTemplate, HumanMessage
        import json

        prompt = f"""你是一个专业的投标文件信息提取助手。请从以下OCR识别的投标文件首页内容中提取关键信息。

需要提取的字段说明：
1. project_name: 项目名称/标段名称（通常是页面中最醒目的标题，可能包含"项目"、"工程"、"采购"等关键词）
2. bid_date: 投标截止时间或开标时间（查找"投标截止时间"、"开标时间"、"截止日期"等附近的日期，格式如：2024年1月15日 或 2024-01-15）
3. bidder: 投标人/投标单位全称（查找"投标人"、"投标单位"、"供应商"等字段后的公司名称）
4. tenderer: 招标人/采购单位全称（查找"招标人"、"采购人"、"建设单位"、"业主"等字段后的单位名称）
5. legal_representative: 法定代表人或授权委托人姓名（查找"法定代表人"、"法人代表"、"授权代表"、"委托代理人"等字段后的姓名）

重要提示：
- 如果某个字段在文本中找不到明确对应的信息，请将该字段设为 null
- 不要编造或推测不存在的信息
- 保持原文的准确性，特别是公司名称和人名
- 日期尽量转换为标准格式 YYYY-MM-DD

OCR识别的文本内容：
{text}

请严格按照以下JSON格式返回（只返回JSON对象，不要添加任何其他说明、注释或代码标记）：
{{
  "project_name": "项目名称或null",
  "bid_date": "YYYY-MM-DD格式的日期或null",
  "bidder": "投标人全称或null",
  "tenderer": "招标人全称或null",
  "legal_representative": "法定代表人姓名或null"
}}
"""

        llm_model = LLMModel(
            model_name=app_context.llm_config.get("model_name", "Qwen/Qwen2.5-72B-Instruct"),
            url=app_context.llm_config.get("url", "https://api.siliconflow.cn/v1/chat/completions"),
            api_key=app_context.llm_config.get("api_key", "")
        )

        message = PromptTemplate([HumanMessage(prompt)])
        result = asyncio.run(llm_model.invoke(message))

        if result and "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            
            # 尝试提取JSON
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    info_dict = json.loads(json_str)
                    
                    tender_info = TenderInfo(
                        project_name=info_dict.get("project_name"),
                        bid_date=info_dict.get("bid_date"),
                        bidder=info_dict.get("bidder"),
                        tenderer=info_dict.get("tenderer"),
                        legal_representative=info_dict.get("legal_representative")
                    )
                    
                    logger.info(f"成功提取投标信息: 项目={tender_info.project_name}, 投标人={tender_info.bidder}, 招标人={tender_info.tenderer}")
                    return tender_info
                except json.JSONDecodeError as je:
                    logger.error(f"JSON解析失败: {str(je)}, 原始内容: {json_str[:200]}")
                    return None
            else:
                logger.warning(f"未找到JSON格式的内容，LLM返回: {content[:200]}")
                return None

        logger.warning("LLM返回结果格式不正确或为空")
        return None

    except Exception as e:
        logger.error(f"LLM解析投标信息失败: {str(e)}", exc_info=True)
        return None


def task_upload(file_bytes, file_type, business_id, page_number, tender_file_id):
    logger.info(f"task_upload 开始时间- {datetime.datetime.now()}")
    file_id, url = _blocking_upload_logic(file_bytes, file_type, business_id)
    logger.info(f"task_upload 结束时间- {datetime.datetime.now()}")
    with app_context.db_session_factory() as session:
        tender_pdf_image_entity = TenderPDFImageEntity(
            file_id=file_id,
            page_number=page_number,
            tender_file_id=tender_file_id
        )
        session.add(tender_pdf_image_entity)
        session.commit()
    return file_id, page_number


def _blocking_upload_logic(file_bytes, file_type, business_id):
    """
    ⭐ 纯同步逻辑函数
    所有耗时操作都在这里，不阻塞事件循环
    """
    # 1. UUID 生成
    uuid_str = uuid.uuid4().hex

    # 2. 临时文件处理 (可选优化：直接使用 put_object 传 bytes 可跳过此步，见下方说明)
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = os.path.join(tmp_dir, f"{uuid_str}.{file_type}")

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        p = Path(file_path)
        ext = p.suffix[1:] if p.suffix else ""

        # 3. MinIO 上传 (阻塞操作)
        minio_client.fput_object(
            bucket_name=app_context.minio_config["bucket_name"],
            object_name=f"files/{business_id}/{uuid_str}.{ext}",
            file_path=file_path,
            content_type=ext  # 建议指定正确 Content-Type，如 image/png
        )

        # 4. 数据库记录 (假设 db_session 也是同步的)
        file_record = FileRecordEntity(
            file_size=p.stat().st_size,
            mime_type=ext,
            file_name=f"{uuid_str}.{ext}",
            file_path=f"files/{business_id}/{uuid_str}.{ext}",
            business_id=business_id,
        )

        # 注意：多线程下的数据库 Session 需要小心，确保线程安全或使用独立连接
        with app_context.db_session_factory() as session:
            session.add(file_record)
            session.commit()
            file_id = file_record.id
    url = get_file_url(f"files/{business_id}/{uuid_str}.{ext}")
    return file_id, url


async def upload_file_bytes(file_bytes, file_type, business_id):
    """
    上传文件二进制到minio
    :param file_bytes:
    :param file_type:
    :param business_id:
    :return:
    """
    """
    异步入口，将阻塞任务卸载到线程池
    """
    loop = asyncio.get_running_loop()

    # ⭐ 关键步骤：在线程池中运行阻塞逻辑
    file_id, url = await loop.run_in_executor(_executor, _blocking_upload_logic, file_bytes, file_type, business_id)
    logger.info(f"✅ Task Finished: {file_id}, {url}")
    return file_id, url


def upload_file(files, business_id)->List[int]:
    """
    上传文件
    :param files: 文件集合
    :param business_id 业务id，根据实际功能指定业务模块的标识符，目前标书使用tender
    """
    file_record_list = []
    for file in files:
        # 如果 business_id 为 skill，则只允许 zip 压缩包，并解压上传
        if business_id == "skills":
            if not file.filename.endswith(".zip"):
                # 可选：抛出异常或记录日志，这里选择跳过非 zip 文件
                continue
            # 调用 zip_unzip 处理解压和上传，注意 zip_unzip 返回的是 list，需要 extend
            extracted_records = zip_unzip(file, business_id)
            file_record_list.extend(extracted_records)
        else:
            # 原有逻辑：如果是 tender 且为 zip，也进行解压处理
            if business_id == "tender" and file.filename.endswith(".zip"):
                extracted_records = zip_unzip(file, business_id)
                file_record_list.extend(extracted_records)
            else:
                # 普通文件上传逻辑
                with tempfile.TemporaryDirectory() as tmp_dir:
                    file_path = os.path.join(tmp_dir, file.filename)
                    with open(file_path, "wb") as f:
                        f.write(file.file.read())
                    p = Path(file_path)
                    # 上传到 MinIO / 保存到数据库 / OCR 扫描等
                    uuid_str = uuid.uuid4().hex
                    file_type = p.suffix[1:] if p.suffix else ""
                    minio_client.fput_object(
                        bucket_name=app_context.minio_config["bucket_name"],
                        object_name=f"files/{business_id}/{uuid_str}.{file_type}",
                        file_path=file_path,
                        content_type=file.content_type
                    )
                    file_record_list.append(FileRecordEntity(
                        file_size=p.stat().st_size,
                        mime_type=file_type,
                        file_name=file.filename,
                        file_path=f"files/{business_id}/{uuid_str}.{file_type}",
                        business_id=business_id,
                    ))
    
    # 批量保存数据库记录
    if file_record_list:
        with app_context.db_session_factory() as session:
            session.add_all(file_record_list)
            session.commit()
            file_ids = [record.id for record in file_record_list]
    else:
        file_ids = []
        
    return file_ids


def zip_unzip(file, business_id):
    """
    解压ZIP文件并上传到MinIO
    :param file: 上传的ZIP文件
    :param business_id: 业务ID
    :return: 文件记录列表
    """
    file_record_list = []
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, file.filename)

        # 写入临时 ZIP 文件
        with open(zip_path, "wb") as f:
            f.write(file.file.read())
        
        # 安全解压
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # 检查文件数量，防止 zip 炸弹
                if len(zip_ref.namelist()) > MAX_FILES:
                    logger.warning(f"ZIP文件包含过多文件 ({len(zip_ref.namelist())})，超过限制 {MAX_FILES}")
                    return file_record_list

                for member in zip_ref.namelist():
                    # 跳过目录
                    if member.endswith("/"):
                        continue

                    # 安全路径检查（防止 Zip Slip 漏洞）
                    target_path = os.path.join(tmp_dir, member)
                    if not is_safe_path(tmp_dir, target_path):
                        logger.warning(f"检测到不安全的路径: {member}")
                        continue

                    # 检查文件扩展名
                    p = Path(member)
                    file_ext = p.suffix.lower()
                    if file_ext and file_ext[1:] not in [ext.lstrip('.') for ext in ALLOWED_EXTENSIONS]:
                        logger.warning(f"跳过不支持的文件类型: {member}")
                        continue

                    # 解压文件
                    zip_ref.extract(member, tmp_dir)

                    # 检查文件大小
                    extracted_size = os.path.getsize(target_path)
                    if extracted_size > MAX_FILE_SIZE:
                        logger.warning(f"文件过大 ({extracted_size} bytes): {member}")
                        continue

                    # 生成唯一的文件名（使用UUID），但保留原始扩展名
                    uuid_str = uuid.uuid4().hex
                    unique_filename = f"{uuid_str}{p.suffix}"
                    
                    # 构建 MinIO 对象路径（扁平化存储，避免层级过深）
                    object_name = f"files/{business_id}/{unique_filename}"

                    # 上传到 MinIO
                    minio_client.fput_object(
                        bucket_name=app_context.minio_config["bucket_name"],
                        object_name=object_name,
                        file_path=target_path,
                        content_type=file.content_type if hasattr(file, 'content_type') else 'application/octet-stream'
                    )

                    # 创建文件记录（使用原始文件名便于识别）
                    file_record_list.append(FileRecordEntity(
                        file_size=extracted_size,
                        mime_type=file_ext[1:] if file_ext else "",
                        file_name=p.name,  # 保留原始文件名
                        file_path=object_name,
                        business_id=business_id,
                    ))
                    
                    logger.info(f"成功解压并上传文件: {p.name} -> {object_name}")

        except zipfile.BadZipFile:
            logger.error(f"无效的ZIP文件: {file.filename}")
        except Exception as e:
            logger.error(f"解压ZIP文件时出错: {file.filename}, 错误: {str(e)}")
    
    return file_record_list


# 允许的文件扩展名（可选）
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md"}
MAX_FILES = 100  # 防止 zip 炸弹
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def is_safe_path(basedir: str, path: str) -> bool:
    """防止路径遍历攻击（Zip Slip 漏洞）"""
    return os.path.realpath(path).startswith(basedir)


def upload_skill_zip(file) -> dict:
    """
    上传skill压缩包并解压到skills目录
    :param file: 上传的ZIP文件
    :return: 包含skill名称列表和错误信息的字典
    """
    import re
    
    result = {
        "success": True,
        "skill_names": [],
        "error_message": None,
        "duplicate_skills": []
    }
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, file.filename)

        # 写入临时 ZIP 文件
        with open(zip_path, "wb") as f:
            f.write(file.file.read())
        
        # 安全解压
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # 检查文件数量
                if len(zip_ref.namelist()) > MAX_FILES:
                    result["success"] = False
                    result["error_message"] = f"ZIP文件包含过多文件 ({len(zip_ref.namelist())})，超过限制 {MAX_FILES}"
                    return result

                # 获取所有现有的 skill 名称
                skills_base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills')
                existing_skills = set()
                if os.path.exists(skills_base_dir):
                    for item in os.listdir(skills_base_dir):
                        skill_path = os.path.join(skills_base_dir, item)
                        if os.path.isdir(skill_path):
                            skill_md_path = os.path.join(skill_path, 'SKILL.md')
                            if os.path.exists(skill_md_path):
                                try:
                                    with open(skill_md_path, 'r', encoding='utf-8') as f:
                                        content = f.read()
                                        name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
                                        if name_match:
                                            existing_skills.add(name_match.group(1).strip())
                                except Exception as e:
                                    logger.warning(f"读取现有skill失败: {item}, 错误: {str(e)}")
                
                logger.info(f"现有skill名称: {existing_skills}")

                # 收集待上传的 skill 信息
                skills_to_upload = []
                
                for member in zip_ref.namelist():
                    # 跳过目录
                    if member.endswith("/"):
                        continue

                    # 安全路径检查
                    target_path = os.path.join(tmp_dir, member)
                    if not is_safe_path(tmp_dir, target_path):
                        logger.warning(f"检测到不安全的路径: {member}")
                        continue

                    # 只处理 SKILL.md 文件
                    if not member.endswith("SKILL.md"):
                        continue

                    # 解压文件
                    zip_ref.extract(member, tmp_dir)

                    # 读取 SKILL.md 内容，提取 name
                    try:
                        with open(target_path, 'r', encoding='utf-8') as skill_file:
                            content = skill_file.read()
                            
                            # 使用正则表达式提取 name 字段
                            name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
                            if name_match:
                                skill_name = name_match.group(1).strip()
                                
                                # 检查是否与现有 skill 重名
                                if skill_name in existing_skills:
                                    result["duplicate_skills"].append(skill_name)
                                    logger.warning(f"发现重名skill: {skill_name}")
                                    continue
                                
                                # 获取 skill 目录名（SKILL.md 的父目录）
                                skill_dir = os.path.dirname(target_path)
                                skill_folder_name = os.path.basename(skill_dir)
                                
                                skills_to_upload.append({
                                    "name": skill_name,
                                    "folder_name": skill_folder_name,
                                    "temp_path": target_path
                                })
                            else:
                                logger.warning(f"SKILL.md 中未找到 name 字段: {member}")
                                continue
                            
                    except Exception as e:
                        logger.error(f"处理 SKILL.md 文件时出错: {member}, 错误: {str(e)}")
                        continue
                
                # 如果有重名的 skill，返回错误
                if result["duplicate_skills"]:
                    result["success"] = False
                    result["error_message"] = f"以下skill名称已存在: {', '.join(result['duplicate_skills'])}"
                    return result
                
                # 如果没有有效的 skill 可上传
                if not skills_to_upload:
                    result["success"] = False
                    result["error_message"] = "未在压缩包中找到有效的SKILL.md文件"
                    return result
                
                # 执行上传操作
                for skill_info in skills_to_upload:
                    try:
                        skill_name = skill_info["name"]
                        skill_folder_name = skill_info["folder_name"]
                        temp_path = skill_info["temp_path"]
                        
                        # 构建目标路径：skills/{skill_folder_name}/SKILL.md
                        target_skill_dir = os.path.join(skills_base_dir, skill_folder_name)
                        
                        # 创建目录（如果不存在）
                        os.makedirs(target_skill_dir, exist_ok=True)
                        
                        # 复制 SKILL.md 到目标位置
                        import shutil
                        target_skill_path = os.path.join(target_skill_dir, 'SKILL.md')
                        shutil.copy2(temp_path, target_skill_path)
                        
                        # 复制同一目录下的其他文件（如图片等资源）
                        skill_source_dir = os.path.dirname(temp_path)
                        for item in os.listdir(skill_source_dir):
                            if item != 'SKILL.md':
                                source_item = os.path.join(skill_source_dir, item)
                                target_item = os.path.join(target_skill_dir, item)
                                if os.path.isfile(source_item):
                                    shutil.copy2(source_item, target_item)
                                elif os.path.isdir(source_item):
                                    if os.path.exists(target_item):
                                        shutil.rmtree(target_item)
                                    shutil.copytree(source_item, target_item)
                        
                        result["skill_names"].append(skill_name)
                        logger.info(f"成功上传 skill: {skill_name} (目录: {skill_folder_name})")
                        
                    except Exception as e:
                        logger.error(f"上传 skill 失败: {skill_info.get('name', 'unknown')}, 错误: {str(e)}")
                        result["success"] = False
                        result["error_message"] = f"上传 skill '{skill_info.get('name', 'unknown')}' 失败: {str(e)}"
                        return result

        except zipfile.BadZipFile:
            result["success"] = False
            result["error_message"] = f"无效的ZIP文件: {file.filename}"
            logger.error(result["error_message"])
        except Exception as e:
            result["success"] = False
            result["error_message"] = f"解压ZIP文件时出错: {file.filename}, 错误: {str(e)}"
            logger.error(result["error_message"])
    
    return result


def is_scanned_pdf(file_path: str) -> bool:
    """
    判断PDF是否为扫描件
    :param file_path: PDF文件路径
    :return: True表示是扫描件，False表示是文本PDF
    """
    try:
        import fitz

        doc = fitz.open(file_path)
        if doc.is_encrypted:
            logger.warning("PDF文件被加密")
            return False

        total_chars = 0
        sample_pages = min(3, len(doc))

        for page_num in range(sample_pages):
            page = doc[page_num]
            text = page.get_text()
            total_chars += len(text.strip())

            if len(text.strip()) > 200:
                doc.close()
                return False

        doc.close()
        threshold = 50
        return total_chars < threshold

    except Exception as e:
        logger.error(f"判断PDF类型失败: {str(e)}", exc_info=True)
        return False


def pdf_page_to_image(file_path: str, page_number: int = 0, dpi: int = 200) -> bytes:
    """
    将PDF指定页转换为图片
    :param file_path: PDF文件路径
    :param page_number: 页码（从0开始）
    :param dpi: 分辨率
    :return: PNG图片的字节数据
    """
    try:
        import fitz

        doc = fitz.open(file_path)
        if page_number >= len(doc):
            raise ValueError(f"页码 {page_number} 超出范围，文档共 {len(doc)} 页")

        page = doc[page_number]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")
        doc.close()

        return img_bytes

    except Exception as e:
        logger.error(f"PDF转图片失败: {str(e)}", exc_info=True)
        raise


def ocr_extract_tender_info(image_bytes: bytes) -> Optional[TenderInfo]:
    """
    使用OCR Agent直接从图片中提取投标信息（结构化返回）
    :param image_bytes: 图片字节数据
    :return: TenderInfo对象，包含项目名称、投标时间、投标人、招标人、法定代表人等信息，失败返回None
    """
    try:
        from agent.model.orc import scan_orc_content_with_prompt

        # 将图片转换为base64
        base64_str = base64.b64encode(image_bytes).decode("utf-8")
        
        prompt_text = "请从这张投标文件首页图片中提取关键投标信息"
        
        # 调用OCR Agent，直接返回结构化的TenderInfo
        result = scan_orc_content_with_prompt(
            image_base64=base64_str,
            prompt_text=prompt_text,
            response_format=TenderInfo
        )
        logger.info(f"OCR Agent返回结构化结果: {result}")
        # 从结果中提取TenderInfo
        if result and "structured_response" in result:
            tender_info = result["structured_response"]
            if tender_info and any([tender_info.project_name, tender_info.bidder, tender_info.tenderer]):
                logger.info(f"OCR Agent成功提取投标信息: 项目={tender_info.project_name}, 投标人={tender_info.bidder}")
                return tender_info
            else:
                logger.warning("OCR Agent返回的TenderInfo中所有字段都为空")
                return None
        
        logger.warning("OCR Agent未返回结构化结果")
        return None

    except Exception as e:
        logger.error(f"OCR Agent提取投标信息失败: {str(e)}", exc_info=True)
        return None


def ocr_extract_text_from_image(image_bytes: bytes) -> str:
    """
    使用OCR从图片中提取纯文本（保留原有功能供其他地方使用）
    :param image_bytes: 图片字节数据
    :return: 识别出的文本
    """
    try:
        from agent.model.orc import scan_orc_content

        base64_str = base64.b64encode(image_bytes).decode("utf-8")
        prompt_text = """请识别图片中的所有文字内容，保持原有格式和布局。
        特别注意：
        1. 准确识别标题、大字号文字
        2. 保留表格结构
        3. 识别日期、公司名称、人名等关键信息
        4. 如果文字模糊不清，尽量根据上下文推断"""

        result = scan_orc_content(base64_str, prompt_text)

        if result and isinstance(result, str):
            return result.strip()

        return ""

    except Exception as e:
        logger.error(f"OCR识别失败: {str(e)}", exc_info=True)
        return ""


def extract_project_name_from_first_page(file_path: str, mime_type: str) -> str:
    """
    从文件第一页提取项目名称（大标题）
    :param file_path: 文件路径
    :param mime_type: 文件类型 (pdf, docx, doc等)
    :return: 项目名称字符串
    """
    try:
        if mime_type.lower() in ['pdf']:
            return _extract_project_name_from_pdf(file_path)
        elif mime_type.lower() in ['docx', 'doc']:
            return _extract_project_name_from_docx(file_path)
        else:
            logger.warning(f"不支持的文件类型: {mime_type}")
            return ""
    except Exception as e:
        logger.error(f"提取项目名称失败: {str(e)}", exc_info=True)
        return ""


def _extract_project_name_from_pdf(file_path: str) -> str:
    """
    从PDF文件第一页提取项目名称
    策略：
    1. 先判断是否为扫描件
    2. 如果是文本PDF，查找字体最大的文本作为标题
    3. 如果是扫描件，使用OCR识别后提取最大字号的文本
    """
    try:
        import fitz

        is_scanned = is_scanned_pdf(file_path)
        logger.info(f"PDF文件类型判断: {'扫描件' if is_scanned else '文本PDF'}")

        if is_scanned:
            logger.info("检测到扫描件PDF，使用OCR识别第一页")
            return _extract_project_name_from_scanned_pdf(file_path)

        doc = fitz.open(file_path)
        if len(doc) == 0:
            return ""

        first_page = doc[0]
        blocks = first_page.get_text("dict")["blocks"]

        max_font_size = 0
        title_text = ""

        for block in blocks:
            if "lines" not in block:
                continue

            for line in block["lines"]:
                for span in line["spans"]:
                    font_size = span.get("size", 0)
                    text = span.get("text", "").strip()

                    if text and font_size > max_font_size and len(text) > 2:
                        max_font_size = font_size
                        title_text = text

        doc.close()

        if title_text:
            title_text = re.sub(r'\s+', ' ', title_text).strip()
            logger.info(f"从PDF提取的项目名称: {title_text}")
            return title_text

        return ""

    except Exception as e:
        logger.error(f"PDF项目名称提取失败: {str(e)}", exc_info=True)
        return ""


def _extract_project_name_from_scanned_pdf(file_path: str) -> str:
    """
    从扫描版PDF第一页提取项目名称（使用OCR）
    :param file_path: PDF文件路径
    :return: 项目名称
    """
    try:
        logger.info("开始将PDF第一页转换为图片")
        image_bytes = pdf_page_to_image(file_path, page_number=0, dpi=300)

        logger.info("开始OCR识别")
        ocr_text = ocr_extract_text_from_image(image_bytes)

        if not ocr_text:
            logger.warning("OCR识别结果为空")
            return ""

        logger.info(f"OCR识别结果长度: {len(ocr_text)} 字符")

        lines = ocr_text.split('\n')

        max_length = 0
        title_text = ""

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            if len(line) > max_length and len(line) < 100:
                max_length = len(line)
                title_text = line

        if title_text:
            title_text = re.sub(r'\s+', ' ', title_text).strip()
            logger.info(f"从扫描PDF提取的项目名称: {title_text}")
            return title_text

        return ""

    except Exception as e:
        logger.error(f"扫描PDF项目名称提取失败: {str(e)}", exc_info=True)
        return ""


def _extract_project_name_from_docx(file_path: str) -> str:
    """
    从Word文档第一页提取项目名称
    策略：查找第一个大字号或加粗的段落作为标题
    """
    try:
        from docx import Document

        doc = Document(file_path)

        max_font_size = 0
        title_text = ""

        for paragraph in doc.paragraphs:
            if not paragraph.text or not paragraph.text.strip():
                continue

            text = paragraph.text.strip()

            if len(text) < 3:
                continue

            font_size = 0
            is_bold = False

            if paragraph.runs:
                for run in paragraph.runs:
                    if run.font.size and run.font.size.pt:
                        font_size = max(font_size, run.font.size.pt)
                    if run.bold:
                        is_bold = True

            if (font_size > max_font_size and len(text) > 5) or \
                    (is_bold and font_size > 14 and len(text) > 5):
                max_font_size = font_size
                title_text = text

                if font_size >= 16:
                    break

        if title_text:
            title_text = re.sub(r'\s+', ' ', title_text).strip()
            logger.info(f"从Word提取的项目名称: {title_text}")
            return title_text

        return ""

    except ImportError:
        logger.error("未安装python-docx库，无法解析Word文档")
        return ""
    except Exception as e:
        logger.error(f"Word项目名称提取失败: {str(e)}", exc_info=True)
        return ""


def upload_file_with_project_name(files, business_id) -> List[dict]:
    """
    上传文件并提取投标信息（项目名称、投标时间、投标人、招标人、法定代表人等）
    :param files: 文件集合
    :param business_id: 业务id
    :return: 包含文件ID和投标信息的列表
    """
    result_list = []

    for file in files:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, file.filename)
            with open(file_path, "wb") as f:
                f.write(file.file.read())

            p = Path(file_path)
            uuid_str = uuid.uuid4().hex
            file_type = p.suffix[1:] if p.suffix else ""

            minio_client.fput_object(
                bucket_name=app_context.minio_config["bucket_name"],
                object_name=f"files/{business_id}/{uuid_str}.{file_type}",
                file_path=file_path,
                content_type=file.content_type
            )

            file_record = FileRecordEntity(
                file_size=p.stat().st_size,
                mime_type=file_type,
                file_name=file.filename,
                file_path=f"files/{business_id}/{uuid_str}.{file_type}",
                business_id=business_id,
            )

            with app_context.db_session_factory() as session:
                session.add(file_record)
                session.commit()
                file_id = file_record.id

            tender_info = extract_tender_info_from_first_page(file_path, file_type)
            if tender_info:
                result_list.append({
                    "file_id": file_id,
                    "project_name": tender_info.project_name if tender_info else None,
                    "bid_date": tender_info.bid_date if tender_info else None,
                    "bidder": tender_info.bidder if tender_info else None,
                    "tenderer": tender_info.tenderer if tender_info else None,
                    "legal_representative": tender_info.legal_representative if tender_info else None
                })

    return result_list


def delete_file_by_id(file_id: int) -> bool:
    """
    根据file_id删除文件及其关联的所有数据
    
    :param file_id: 文件ID
    :return: 删除成功返回True，失败返回False
    """
    try:
        logger.info(f"开始删除文件 ID: {file_id}")
        
        with app_context.db_session_factory() as session:
            # 1. 查询文件记录
            file_record = session.get(FileRecordEntity, file_id)
            if not file_record:
                logger.warning(f"文件记录不存在: file_id={file_id}")
                return False
            
            file_path = file_record.file_path
            business_id = file_record.business_id
            
            logger.info(f"找到文件记录: {file_record.file_name}, 路径: {file_path}")
            
            # 2. 删除 TenderPDFImageEntity 关联记录（如果存在）
            tender_pdf_images = session.query(TenderPDFImageEntity).filter(
                TenderPDFImageEntity.tender_file_id == file_id
            ).all()
            
            if tender_pdf_images:
                for image_entity in tender_pdf_images:
                    session.delete(image_entity)
                logger.info(f"删除了 {len(tender_pdf_images)} 条 TenderPDFImageEntity 记录")
            
            # 3. 检查是否有其他表引用此文件（如 SubBidPlagiarismCheckTask 等）
            # 这里可以根据需要添加更多的检查
            
            # 4. 删除文件记录
            session.delete(file_record)
            logger.info(f"删除文件记录: file_id={file_id}")
            
            # 5. 提交数据库事务
            session.commit()
            logger.info("数据库记录删除完成")
        
        # 6. 删除 MinIO 中的文件
        try:
            minio_client.remove_object(
                bucket_name=app_context.minio_config["bucket_name"],
                object_name=file_path
            )
            logger.info(f"MinIO文件删除成功: {file_path}")
        except Exception as e:
            logger.error(f"MinIO文件删除失败: {file_path}, 错误: {str(e)}")
            # MinIO删除失败不影响整体结果，因为数据库已删除
        
        logger.info(f"文件删除完成: file_id={file_id}")
        return True
        
    except Exception as e:
        logger.error(f"删除文件失败: file_id={file_id}, 错误: {str(e)}", exc_info=True)
        return False


def batch_delete_files(file_ids: List[int]) -> dict:
    """
    批量删除文件及其关联的所有数据
    
    :param file_ids: 文件ID列表
    :return: 包含删除结果的字典
    """
    if not file_ids:
        logger.warning("批量删除文件列表为空")
        return {
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "success_ids": [],
            "failed_details": []
        }
    
    logger.info(f"开始批量删除 {len(file_ids)} 个文件")
    
    success_count = 0
    failed_count = 0
    success_ids = []
    failed_details = []
    
    for file_id in file_ids:
        try:
            success = delete_file_by_id(file_id)
            if success:
                success_count += 1
                success_ids.append(file_id)
                logger.info(f"文件 {file_id} 删除成功")
            else:
                failed_count += 1
                failed_details.append({
                    "file_id": file_id,
                    "error": "文件不存在或删除失败"
                })
                logger.warning(f"文件 {file_id} 删除失败")
        except Exception as e:
            failed_count += 1
            failed_details.append({
                "file_id": file_id,
                "error": str(e)
            })
            logger.error(f"文件 {file_id} 删除异常: {str(e)}")
    
    result = {
        "total": len(file_ids),
        "success_count": success_count,
        "failed_count": failed_count,
        "success_ids": success_ids,
        "failed_details": failed_details
    }
    
    logger.info(f"批量删除完成: 总数={len(file_ids)}, 成功={success_count}, 失败={failed_count}")
    return result

