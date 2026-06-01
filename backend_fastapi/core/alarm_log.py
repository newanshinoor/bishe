from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String

from core.database import Base


class AlarmLog(Base):
    """
    LSTM 防作弊报警证据表。

    对应 MySQL 表结构：
    - log_id: int，主键，自增
    - transaction_id: varchar(32)，关联交易/订单编号；没有交易上下文时写入实时流占位编号
    - creat_at: datetime，报警产生时间
    - violation_type: varchar(20)，作弊类型，如 swap、occlusion
    - lstm_score: decimal(4,3)，LSTM 判定置信度
    - shot_path: varchar(255)，异常前 6 秒视频片段保存路径
    """

    __tablename__ = "alarm_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True, comment="报警日志主键")
    transaction_id = Column(String(32), nullable=False, comment="关联交易/订单编号")
    creat_at = Column(DateTime, nullable=False, default=datetime.now, comment="报警产生时间")
    violation_type = Column(String(20), nullable=False, comment="违规类型")
    lstm_score = Column(Numeric(4, 3), nullable=False, comment="LSTM 判定置信度")
    shot_path = Column(String(255), nullable=False, comment="异常证据视频路径")
