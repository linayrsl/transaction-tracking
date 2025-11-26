from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(BigInteger, nullable=False)  # Stored as cents (big integer for large amounts)
    currency = Column(String(3), nullable=False)  # 3-letter uppercase code
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to User
    user = relationship("User", back_populates="transactions")
