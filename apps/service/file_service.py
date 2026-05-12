import asyncio
import datetime
import os
import tempfile
import uuid
import zipfile
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path
from typing import List

from apps import AppContext
from apps.repository.entity.file_entity import FileRecordEntity
from apps.repository.entity.tender_entity import TenderPDFImageEntity
from apps.repository.minio_repository import get_file_url
from logger_config import get_logger

logger = get_logger(name=__package__)

app_context = AppContext()
minio_client = app_context.minio_client
# 创建一个全局线程池（避免每次调用都创建新线程）
_executor = ThreadPoolExecutor(max_workers=20)


async def task_upload(file_bytes, file_type, business_id, page_number, tender_file_id):
    print(f"task_upload 开始时间- {datetime.datetime.now()}")
    file_id, url = await upload_file_bytes(file_bytes, file_type, business_id)
    print(f"task_upload 结束时间- {datetime.datetime.now()}")
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
    print(f"✅ Task Finished: {file_id}, {url}")
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

