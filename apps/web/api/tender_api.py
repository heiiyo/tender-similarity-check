import asyncio
import urllib
from datetime import datetime
from io import BytesIO

import openpyxl
from fastapi import APIRouter, BackgroundTasks
from starlette.responses import StreamingResponse

from apps.service.file_service import upload_file_bytes
from apps.service.tender_service import bid_plagiarism_check, get_tender_task_list, get_tender_sub_task_list, \
    get_tender_similarity_info, get_tender_similarity_info_by_file_id, delete_tender_task_by_task_id, \
    export_similarity_report, export_similarity_report_task_id, update_tender_similarity_info, \
    batch_update_tender_similarity_info, batch_delete_tender_tasks
from apps.web.dto.tender_task import TenderTaskDto, TenderConditionDto, BasePageDto, TenderSimilarityDto, BatchIds
from apps.web.vo.similarity_respose import BaseResponse
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(name=__name__)
tender_router = APIRouter(prefix="/api/tender", tags=["标书"])


@tender_router.post("/tender_check", response_model=BaseResponse, summary="创建标书检测任务")
async def tender_check(tender_task_dto: TenderTaskDto, background_tasks: BackgroundTasks):
    """
    标书检测接口
    
    **功能说明：**
    - 支持查重检测和合规检测两种模式
    - 后台异步执行，立即返回任务创建结果
    - 检测过程包括：文件解析、向量化、相似度比对/规则检查
    
    **检测类型：**
    - check_type = 1: 查重检测（对比多份标书之间的相似度）
    - check_type = 2: 合规检测（检查标书是否符合规范要求）
    
    **处理流程：**
    1. 注册检测任务到数据库
    2. 后台异步解析标书文件（PDF/Word）
    3. 提取文本并生成向量
    4. 执行相似度比对或合规规则检查
    5. 更新任务状态和检测结果
    
    **请求参数示例：**
    
    ```
    {
      "check_type": 1,
      "files": [
        {
          "file_id": "file1",
          "file_name": "标书1.pdf",
          "file_type": "pdf"
        },
        {
          "file_id": "file2",
          "file_name": "标书2.docx",
          "file_type": "docx"
        }
      ]
    }
    ```
    """
    bid_plagiarism_check(tender_task_dto, background_tasks)
    return BaseResponse.success()


@tender_router.post("/tender_task_list", response_model=BaseResponse)
async def tender_task_list(condition: TenderConditionDto):
    page = await asyncio.to_thread(get_tender_task_list, condition)
    return BaseResponse.success(page)


@tender_router.post("/tender_info_list/{task_id}", response_model=BaseResponse)
async def tender_sub_task_list(task_id, base_page: BasePageDto):
    """
    获取任务详情列表
    :param task_id: 标书检测任务id
    :return:
    """
    page = await asyncio.to_thread(get_tender_sub_task_list, task_id, base_page)
    return BaseResponse.success([page])


@tender_router.post("/tender_similarity_info/{sub_task_id}", response_model=BaseResponse)
async def tender_similarity_info(sub_task_id):
    data = await asyncio.to_thread(get_tender_similarity_info, sub_task_id)
    if not data:
        return BaseResponse.error(message="查询任务失败，或不存在")
    return BaseResponse.success([data])


@tender_router.post("/tender_similarity_info_by_file_id", response_model=BaseResponse)
async def tender_similarity_info_by_file_id(tender_similarity_dto: TenderSimilarityDto):
    data = await asyncio.to_thread(get_tender_similarity_info_by_file_id, tender_similarity_dto)
    if not data:
        return BaseResponse.error(message="查询任务失败，或不存在")
    return BaseResponse.success([data])


@tender_router.post("/update_tender_similarity_info_id/{info_id}", response_model=BaseResponse)
async def update_tender_similarity_info_id(info_id):
    await asyncio.to_thread(update_tender_similarity_info, info_id)
    return BaseResponse.success(info_id)


@tender_router.post("/batch_update_tender_similarity_info_id", response_model=BaseResponse)
async def batch_update_tender_similarity_info_id(ids: BatchIds):
    await asyncio.to_thread(batch_update_tender_similarity_info, ids.ids)
    return BaseResponse.success(ids.ids)


@tender_router.get("/export_similarity_report_by_task_id/{task_id}")
async def export_similarity_report_by_task_id(task_id):
    buffer = await asyncio.to_thread(export_similarity_report_task_id, task_id)
    # file_id, url = await upload_file_bytes(buffer.read(), "xlsx", "report")
    filename = f"报告导出.xlsx"
    from urllib.parse import quote
    encoded_filename = quote(filename.encode('utf-8'))
    from fastapi.responses import StreamingResponse
    # 5. 返回 FileResponse
    return StreamingResponse(
        content=buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{encoded_filename}'
        }
    )
    # return BaseResponse.success(url)


@tender_router.get("/export_similarity_report_by_sub_task_id/{sub_task_id}")
async def export_similarity_report_by_sub_task_id(sub_task_id):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "相似性对比"
    await asyncio.to_thread(export_similarity_report, sub_task_id, wb)
    # 2. 创建内存流
    buffer = BytesIO()
    # 6. 保存 Excel 到内存流
    wb.save(buffer)
    buffer.seek(0)  # 将指针重置到开头
    # file_id, url = await upload_file_bytes(buffer.read(), "xlsx", "report")
    # return BaseResponse.success(url)
    # 处理中文乱码问题
    filename = f"similarity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    from fastapi.responses import StreamingResponse
    # 5. 返回 FileResponse
    return StreamingResponse(
        content=buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{filename}'
        }
    )


@tender_router.delete("/delete_tender_task/{task_id}", response_model=BaseResponse)
def delete_tender_task(task_id):
    delete_tender_task_by_task_id(task_id)
    return BaseResponse.success()


@tender_router.post("/batch_delete_tender_task", response_model=BaseResponse)
async def batch_delete_tender_task(task_ids: BatchIds):
    """
    批量删除标书任务

    :param task_ids: 任务ID列表
    :return: 删除结果统计
    """
    if not task_ids.task_ids:
        return BaseResponse.error(message="任务ID列表不能为空")

    try:
        result = await asyncio.to_thread(batch_delete_tender_tasks, task_ids.task_ids)

        if result["failed_count"] > 0:
            return BaseResponse.success(
                message=f"批量删除完成：成功 {result['success_count']} 个，失败 {result['failed_count']} 个",
                data=result
            )

        return BaseResponse.success(
            message=f"成功删除 {result['success_count']} 个任务",
            data=result
        )
    except Exception as e:
        logger.error(f"批量删除任务失败: {str(e)}", exc_info=True)
        return BaseResponse.error(message=f"批量删除失败: {str(e)}")

