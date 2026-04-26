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
        if business_id == "tender" and file.filename.endswith(".zip"):
            file_record_list.append(zip_unzip(file, business_id))

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
                object_name=f"files/{business_id}/{uuid_str+'.'+ file_type}",
                file_path=file_path,  # ✅ 直接传入 file.file
                content_type=file.content_type
            )
            file_record_list.append(FileRecordEntity(
                file_size=p.stat().st_size,
                mime_type=p.suffix[1:] if p.suffix else "",
                file_name=file.filename,
                file_path=f"files/{business_id}/{uuid_str+'.'+ file_type}",
                business_id=business_id,
            ))
    with app_context.db_session_factory() as session:
        session.add_all(file_record_list)
        session.commit()
        file_ids = [file_record.id for file_record in file_record_list]
    return file_ids


def zip_unzip(file, business_id):
    file_record_list = []
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
                    pass

                extracted_files = []
                for member in zip_ref.namelist():
                    # 跳过目录
                    if member.endswith("/"):
                        continue

                    # 安全路径检查（关键！）
                    target_path = os.path.join(tmp_dir, member)
                    if not is_safe_path(tmp_dir, target_path):
                        continue

                    # 可选：检查扩展名
                    if ALLOWED_EXTENSIONS and not any(member.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
                        continue  # 跳过不允许的文件

                    # 解压文件
                    zip_ref.extract(member, tmp_dir)

                    # 👇 在这里处理解压后的文件（示例：打印路径）
                    print(f"Processing: {target_path}")
                    # 上传到 MinIO / 保存到数据库 / OCR 扫描等
                    minio_client.fput_object(
                        bucket_name=app_context.minio_config["bucket_name"],
                        object_name=f"files/{business_id}/{member}",
                        file_path=target_path,  # ✅ 直接传入 file.file
                        content_type=file.content_type
                    )
                    p = Path(target_path)
                    file_record_list.append(FileRecordEntity(
                        file_size = p.stat().st_size,
                        mime_type = p.suffix[1:] if p.suffix else "",
                        file_name = p.name,
                        file_path=f"files/{business_id}/{member}",
                        business_id=business_id,
                    ))

        except zipfile.BadZipFile:
            pass
    return file_record_list


# 允许的文件扩展名（可选）
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
MAX_FILES = 100  # 防止 zip 炸弹
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def is_safe_path(basedir: str, path: str) -> bool:
    """防止路径遍历攻击（Zip Slip 漏洞）"""
    return os.path.realpath(path).startswith(basedir)

