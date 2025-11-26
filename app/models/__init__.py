from app.database import Base

# Import all models here for Alembic to detect them
from app.models.user import User
from app.models.transaction import Transaction

__all__ = ["User", "Transaction"]
