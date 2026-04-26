from sqlalchemy import Column, Integer, String, BigInteger

from apps.repository.entity import Base


class FileRecordEntity(Base):
    __tablename__ = "file_record"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)  # 原始文件名
    file_path = Column(String(512), nullable=False, unique=True)  # 存储路径（唯一）
    file_size = Column(BigInteger, nullable=False)  # 文件大小（字节）
    mime_type = Column(String(100), nullable=False)  # MIME 类型
    business_id = Column(String(100), nullable=True, index=True)  # 业务ID（字符串兼容多种类型）

    def __repr__(self):
        return f"<FileRecord(id={self.id}, name='{self.file_name}')>"
