from sqlalchemy import Column, DateTime, func, Integer
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):

    created_at = Column(DateTime, default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False, comment="修改时间")
    create_by = Column(Integer, nullable=True, comment="创建人")
    status = Column(Integer, default=1, comment="状态：1-使用证, -1-已废弃")  # 状态：1-使用证, -1-已废弃

