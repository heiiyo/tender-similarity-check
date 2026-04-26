import json
from typing import Optional
from pydantic import BaseModel


class TenderTopicInfo(BaseModel):
    tender_file_id: Optional[int] = None
    tender_topic_name: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None

    def to_json(self):
        """利用 Pydantic model_dump_json 自动处理序列化和编码"""
        # 核心修改点在这里
        return json.dumps(
            self.model_dump(exclude_none=True),
            ensure_ascii=False
        )
