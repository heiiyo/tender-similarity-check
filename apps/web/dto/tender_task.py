from datetime import date
from typing import List

from pydantic import BaseModel, Field


class TenderTaskDto(BaseModel):
    task_name: str = Field(..., description="任务名称")
    task_type: int = Field(..., description="任务类型：1-查重，2-合规，3-综合")
    file_ids: List[int] = Field(..., description="标书集合，标书文件id")
    tender_reference_id: int = Field(..., description="招标文件id")


class BasePageDto(BaseModel):
    page_offset: int = 1
    page_size: int = 10


class TenderConditionDto(BasePageDto):
    task_type: int = None
    process_status: str = None
    created_at_start: date = None
    created_at_end: date = None


class TenderSimilarityDto(BasePageDto):
    left_file_id: int = Field(..., description="左侧标书文件id")
    right_file_id: int = Field(..., description="右侧标书文件id")


class BatchIds(BaseModel):
    ids: List[int]



