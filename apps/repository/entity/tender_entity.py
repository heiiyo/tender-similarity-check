from sqlalchemy import Column, Integer, String, Float, Text

from apps.repository.entity import Base


class BidPlagiarismCheckTask(Base):
    """
    标书查重任务
    """
    __tablename__ = "bid_plagiarism_check_task"

    id = Column(Integer, primary_key=True, index=True)
    tender_reference_file_id = Column(Integer, nullable=True)
    check_type = Column(Integer, nullable=False)
    task_name = Column(String(100), nullable=False)
    file_name_list = Column(String(255), nullable=False)
    file_id_list = Column(String(255), nullable=False)
    process_status = Column(String(20), default="processing")  # 进度状态：completed, processing, parsed, failed


class SubBidPlagiarismCheckTask(Base):
    """
    标书查重子任务
    """
    __tablename__ = "sub_bid_plagiarism_check_task"

    id = Column(Integer, primary_key=True, index=True)
    process_status = Column(String(20), default="processing")  # 进度状态：completed, processing, parsed, failed
    bid_plagiarism_check_task_id = Column(Integer, nullable=False)
    left_file_id = Column(Integer, nullable=False)
    left_file_name = Column(String(255), nullable=False)
    right_file_id = Column(Integer, nullable=False)
    right_file_name = Column(String(255), nullable=False)
    similarity_number = Column(Integer, nullable=False)


class SubComplianceCheckTask(Base):
    """
    标书合规子任务
    """
    __tablename__ = "sub_compliance_check_task"
    id = Column(Integer, primary_key=True, index=True)
    process_status = Column(String(20), default="processing", comment="进度状态：completed, processing, parsed, failed")
    bid_plagiarism_check_task_id = Column(Integer, nullable=False)
    tender_file_id = Column(Integer, nullable=False, comment="标书id")
    tender_file_name = Column(String(255), nullable=False, comment="标书名称")
    risk_number = Column(Integer, default=0, comment="风险数量")


class TenderComplianceRiskRecord(Base):
    """
    标书合规检测风险记录表
    """
    __tablename__ = "tender_compliance_risk_record"
    id = Column(Integer, primary_key=True, index=True)
    sub_compliance_check_task_id = Column(Integer, nullable=False, comment="任务合规任务子表id")
    tender_file_id = Column(Integer, nullable=False, comment="标书id")
    bid_plagiarism_check_task_id = Column(Integer, nullable=False, comment="任务id")
    risk_description = Column(Text, nullable=False, comment="风险描述")
    tender_page = Column(Integer, comment="标书不合规所在页")
    is_risk = Column(Integer, default=1, comment="1-风险；0-无风险")
    rule_id = Column(Integer, comment="规则id")


class DocumentSimilarityRecord(Base):
    """
        文档相似度记录
    """
    __tablename__ = "document_similarity_record"
    id = Column(Integer, primary_key=True, index=True)
    bid_plagiarism_check_task_id = Column(Integer, nullable=False)
    sub_bid_plagiarism_check_task_id = Column(Integer, nullable=False)
    left_file_id = Column(Integer, nullable=False)
    left_file_name = Column(String(255), nullable=False)
    left_file_url = Column(Text, nullable=False)
    left_file_page = Column(Integer, nullable=False)
    left_file_page_start_index = Column(Integer, nullable=False)
    left_file_page_chunk = Column(String(255), nullable=False)
    right_file_id = Column(Integer, nullable=False)
    right_file_name = Column(String(255), nullable=False)
    right_file_url = Column(Text, nullable=False)
    right_file_page = Column(Integer, nullable=False)
    right_file_page_start_index = Column(Integer, nullable=False)
    right_file_page_chunk = Column(String(255), nullable=False)
    similarity = Column(Float, nullable=False)


class TenderRuleConfiguration(Base):
    """
        标书合规检测规则库
    """
    __tablename__ = "tender_rule_configuration"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    remake = Column(Text, nullable=False)
    topic = Column(String(255), nullable=False)
    skill = Column(String(255), nullable=False)


class TenderTopic(Base):
    """
        标书合规检测规则库
    """
    __tablename__ = "tender_topic"
    id = Column(Integer, primary_key=True, index=True, comment="主键id")
    topic_name = Column(String(255), nullable=False, comment="一级目录")
    start_page = Column(Text, comment="开始页数")
    end_page = Column(String(255), comment="结束页数")
    tender_file_id = Column(Integer, nullable=False, comment="对应的标书文件id")


class TenderPDFImageEntity(Base):
    """
        标书映射关联的图片表（图片是标书根据每一页转换过来的）
    """
    __tablename__ = "tender_pdf_image_entity"
    id = Column(Integer, primary_key=True, index=True, comment="主键id")
    file_id = Column(Integer, nullable=False, comment="图片在文件记录表的id")
    page_number = Column(Integer, nullable=False, comment="改图片为标书的那些页")
    tender_file_id = Column(Integer, nullable=False, comment="标书文件在文件记录表的id")


