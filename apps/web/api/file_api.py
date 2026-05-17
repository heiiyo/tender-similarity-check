from typing import List

from fastapi import APIRouter, UploadFile, Form, File

from apps.service.file_service import upload_file, upload_skill_zip
from apps.web.vo.similarity_respose import BaseResponse
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__name__)
file_router = APIRouter(prefix="/api/file", tags=["文件"])


@file_router.post("/upload-multiple", response_model=BaseResponse)
async def tender_file_upload(
        files: List[UploadFile] = File(..., description="请上传标书文件"),
        business_id: str = Form(default="tender")
    ):
    """
    标书文件上传接口
    :param files: 接收上传文件
    :param business_id: 业务id根据实际的功能指定，标书指定tender
    """
    file_ids = upload_file(files, business_id)
    return BaseResponse.success(message="文件上传成功", data=file_ids)


@file_router.post("/upload-skill", response_model=BaseResponse)
async def upload_skill(
        file: UploadFile = File(..., description="请上传skill压缩包文件（.zip格式）")
    ):
    """
    上传skill压缩包文件，自动解压到skills目录
    :param file: 接收上传的ZIP文件，应包含SKILL.md及可能的其他资源文件
    :return: 返回解析出的skill名称列表
    """
    if not file.filename.endswith(".zip"):
        return BaseResponse.error(message="仅支持ZIP格式的压缩文件")
    
    try:
        result = upload_skill_zip(file)
        
        if not result["success"]:
            # 如果是重名错误
            if result.get("duplicate_skills"):
                return BaseResponse.error(
                    message=f"上传失败：以下skill名称已存在: {', '.join(result['duplicate_skills'])}",
                    data={"duplicate_skills": result["duplicate_skills"]}
                )
            # 其他错误
            return BaseResponse.error(message=result.get("error_message", "上传skill失败"))
        
        if not result["skill_names"]:
            return BaseResponse.error(message="未在压缩包中找到有效的SKILL.md文件")
        
        return BaseResponse.success(
            message=f"成功上传 {len(result['skill_names'])} 个skill",
            data={"skill_names": result["skill_names"]}
        )
    except Exception as e:
        return BaseResponse.error(message=f"上传skill失败: {str(e)}")


