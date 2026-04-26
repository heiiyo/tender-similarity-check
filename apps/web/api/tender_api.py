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
    batch_update_tender_similarity_info
from apps.web.dto.tender_task import TenderTaskDto, TenderConditionDto, BasePageDto, TenderSimilarityDto, BatchIds
from apps.web.vo.similarity_respose import BaseResponse

tender_router = APIRouter(prefix="/api/tender", tags=["标书"])


@tender_router.post("/tender_check", response_model=BaseResponse)
async def tender_check(tender_task_dto: TenderTaskDto, background_tasks: BackgroundTasks):
    """
    标书检测
    """
    bid_plagiarism_check(tender_task_dto, background_tasks)
    return BaseResponse.success()


@tender_router.post("/tender_task_list", response_model=BaseResponse)
async def tender_task_list(condition: TenderConditionDto):
    page = get_tender_task_list(condition)
    return BaseResponse.success(page)


@tender_router.post("/tender_info_list/{task_id}", response_model=BaseResponse)
async def tender_sub_task_list(task_id, base_page: BasePageDto):
    """
    获取任务详情列表
    :param task_id: 标书检测任务id
    :return:
    """
    page = get_tender_sub_task_list(task_id, base_page)
    return BaseResponse.success([page])


@tender_router.post("/tender_similarity_info/{sub_task_id}", response_model=BaseResponse)
async def tender_similarity_info(sub_task_id):
    data = get_tender_similarity_info(sub_task_id)
    if not data:
        return BaseResponse.error(message="查询任务失败，或不存在")
    return BaseResponse.success([data])


@tender_router.post("/tender_similarity_info_by_file_id", response_model=BaseResponse)
async def tender_similarity_info_by_file_id(tender_similarity_dto: TenderSimilarityDto):
    data = get_tender_similarity_info_by_file_id(tender_similarity_dto)
    if not data:
        return BaseResponse.error(message="查询任务失败，或不存在")
    return BaseResponse.success([data])


@tender_router.post("/update_tender_similarity_info_id/{info_id}", response_model=BaseResponse)
async def update_tender_similarity_info_id(info_id):
    update_tender_similarity_info(info_id)
    return BaseResponse.success(info_id)


@tender_router.post("/batch_update_tender_similarity_info_id", response_model=BaseResponse)
async def batch_update_tender_similarity_info_id(ids: BatchIds):
    batch_update_tender_similarity_info(ids.ids)
    return BaseResponse.success(ids.ids)


@tender_router.get("/export_similarity_report_by_task_id/{task_id}")
async def export_similarity_report_by_task_id(task_id):
    buffer = export_similarity_report_task_id(task_id)
    # file_id, url = await upload_file_bytes(buffer.read(), "xlsx", "report")
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
    # return BaseResponse.success(url)


@tender_router.get("/export_similarity_report_by_sub_task_id/{sub_task_id}")
async def export_similarity_report_by_sub_task_id(sub_task_id):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "相似性对比"
    export_similarity_report(sub_task_id, wb)
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

