from typing import List

from fastapi import APIRouter, UploadFile, Form, File

from apps.service.file_service import upload_file
from apps.web.vo.similarity_respose import BaseResponse

file_router = APIRouter(prefix="/api/file", tags=["文件"])


@file_router.post("/upload-multiple", response_model=BaseResponse)
async def tender_file_upload(
        files: List[UploadFile],
        business_id: str = Form(default="tender")
    ):
    """
    标书文件上传接口
    :param files: 接收上传文件
    :param business_id: 业务id根据实际的功能指定，标书指定tender
    """
    file_ids = upload_file(files, business_id)
    return BaseResponse.success(message="文件上传成功", data=file_ids)
