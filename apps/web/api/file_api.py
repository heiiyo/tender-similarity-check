import asyncio
from typing import List

from fastapi import APIRouter, UploadFile, Form, File, Query
from pydantic import BaseModel, Field

from apps.service.file_service import upload_file, upload_skill_zip, upload_file_with_project_name, delete_file_by_id, batch_delete_files
from apps.web.vo.similarity_respose import BaseResponse
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__name__)
file_router = APIRouter(prefix="/api/file", tags=["文件"])


class BatchDeleteRequest(BaseModel):
    """批量删除请求模型"""
    file_ids: List[int] = Field(..., description="要删除的文件ID列表", min_items=1)


@file_router.post("/upload-multiple", response_model=BaseResponse, summary="批量上传标书文件")
async def tender_file_upload(
        files: List[UploadFile] = File(..., description="请上传标书文件（支持多选）"),
        business_id: str = Form(default="tender", description="业务ID，默认为tender")
    ):
    """
    标书文件上传接口
    
    **功能说明：**
    - 支持同时上传多个标书文件
    - 支持格式：PDF、Word(.doc/.docx)等
    - 返回上传成功的文件ID列表
    
    **参数说明：**
    - files: 要上传的文件列表（可在Swagger中选择多个文件）
    - business_id: 业务标识，默认为"tender"
    
    **Swagger使用提示：**
    1. 点击 "Choose File" 按钮
    2. 按住 Ctrl (Windows) 或 Cmd (Mac) 键选择多个文件
    3. 或者多次点击添加多个文件
    
    **返回示例：**
    
    """
    file_ids = upload_file(files, business_id)
    return BaseResponse.success(message="文件上传成功", data=file_ids)


@file_router.post("/upload-with-project-name", response_model=BaseResponse)
async def upload_file_with_name(
        files: List[UploadFile] = File(..., description="请上传文件（支持PDF、Word等格式）"),
        business_id: str = Form(default="tender")
):
    """
    文件上传接口，自动解析文件第一页提取项目名称（大标题）
    :param files: 接收上传文件
    :param business_id: 业务id，默认为tender
    :return: 返回文件ID列表及对应的项目名称
    """
    supported_types = ['.pdf', '.docx', '.doc']

    for file in files:
        file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''
        if f'.{file_ext}' not in supported_types:
            return BaseResponse.error(
                message=f"不支持的文件格式: .{file_ext}，仅支持 {', '.join(supported_types)}"
            )

    try:
        result_list = upload_file_with_project_name(files, business_id)

        return BaseResponse.success(
            message="文件上传成功",
            data=result_list
        )
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}", exc_info=True)
        return BaseResponse.error(message=f"文件上传失败: {str(e)}")


@file_router.delete("/delete/{file_id}", response_model=BaseResponse)
async def delete_file(file_id: int):
    """
    删除文件接口，根据file_id删除文件及其关联的所有数据
    
    :param file_id: 要删除的文件ID
    :return: 删除结果
    """
    try:
        success = await asyncio.to_thread(delete_file_by_id, file_id)
        
        if success:
            return BaseResponse.success(
                message=f"文件删除成功: file_id={file_id}",
                data={"file_id": file_id}
            )
        else:
            return BaseResponse.error(
                message=f"文件删除失败，文件可能不存在: file_id={file_id}"
            )
    except Exception as e:
        logger.error(f"删除文件接口异常: file_id={file_id}, 错误: {str(e)}", exc_info=True)
        return BaseResponse.error(message=f"删除文件失败: {str(e)}")


@file_router.post("/batch_delete", response_model=BaseResponse)
async def batch_delete_file(request: BatchDeleteRequest):
    """
    批量删除文件接口，根据file_ids批量删除文件及其关联的所有数据
    
    :param request: 批量删除请求，包含文件ID列表
    :return: 批量删除结果
    """
    try:
        file_ids = request.file_ids
        
        if not file_ids:
            return BaseResponse.error(message="文件ID列表不能为空")
        
        logger.info(f"收到批量删除请求，文件数量: {len(file_ids)}")
        
        # 在线程池中执行批量删除，避免阻塞事件循环
        result = await asyncio.to_thread(batch_delete_files, file_ids)
        
        if result["failed_count"] == 0:
            # 全部成功
            return BaseResponse.success(
                message=f"批量删除成功，共删除 {result['success_count']} 个文件",
                data=result
            )
        elif result["success_count"] > 0:
            # 部分成功
            return BaseResponse.success(
                message=f"批量删除完成，成功 {result['success_count']} 个，失败 {result['failed_count']} 个",
                data=result
            )
        else:
            # 全部失败
            return BaseResponse.error(
                message=f"批量删除失败，所有文件删除均失败",
                data=result
            )
            
    except Exception as e:
        logger.error(f"批量删除文件接口异常: {str(e)}", exc_info=True)
        return BaseResponse.error(message=f"批量删除文件失败: {str(e)}")
