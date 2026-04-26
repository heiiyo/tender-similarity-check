"""
标书查重vo, 用于前端显示结果
"""
from datetime import datetime
from typing import Any, Optional, List

from pydantic import BaseModel


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

