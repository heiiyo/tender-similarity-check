"""
标书查重vo, 用于前端显示结果
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List

from pydantic import BaseModel, Field

# 1. 定义枚举类：继承 str, Enum
class Status(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# 1. 定义枚举类：继承 str, Enum
class CheckType(int, Enum):
    SIMILARITY = 1
    COMPLIANCE = 2
    COMPREHENSIVE = 3

class TaskTypeEnum(int, Enum):
    COMMON = 1
    CIVIL = 2
    MILITARY = 3

def format_datetime(value) -> str:
    """
    日期格式化
    :param value:
    :return:
    """
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


class BaseResponse(BaseModel):
    code: int = 1
    message: str = "success"
    data: Optional[Any] = None

    @classmethod
    def success(cls, data: Any = None, message: str = "success"):
        return cls(code=1, data=data, message=message)

    @classmethod
    def error(cls, code: int = -1, message: str = "error", data: Any = None):
        return cls(code=code, data=data, message=message)

    
class ContrastVO:
    def __init__(self, document, contrast_document_array:list):
        self.document = document
        self.contrast_document_array = contrast_document_array


class BasePage(BaseModel):
    page_size: Optional[int] = None
    page_num: Optional[int] = None
    page_offset: Optional[int] = None
    total: Optional[int] = None


class TenderTaskPage(BasePage):
    data: Optional[Any] = None


class FileRecordVO(BaseModel):
    id: int = None
    file_name: str = None
    file_url: str = None


class TenderSimilarityVO(BasePage):
    data: Optional[Any] = None
    tender_reference: Optional[str] = None
    tender_list: Optional[List[FileRecordVO]] = None

class TaskDataVO(BaseModel):
    id: Optional[int] = Field(description="任务id")
    check_type: CheckType = Field(description="检测类型：1-重复性检测；2-合规性检测；3-综合性检测")
    task_type: TaskTypeEnum = Field(description="项目性质：1-通用，2-民用，3-军用")
    task_name: Optional[str] = Field(description="项目名称")
    file_name_list: Optional[str] = Field(description="文件名称列表，号隔开")
    check_num: Optional[int] = Field(description="检测项")
    risk_num: Optional[int] = Field(description="风险项")
    compliance_num: Optional[int] = Field(description="合规项")
    similarity_num: Optional[int] = Field(description="重复项")
    process_status: Status = Field(description="任务执行状态：processing-进行中，completed-已完成，failed-已完成")
    created_at: Optional[str] = Field(description="创建时间")

