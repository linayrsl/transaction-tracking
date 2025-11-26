from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    CurrencySummary,
)

router = APIRouter()


@router.post(
    "/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    transaction_data: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new transaction for the authenticated user.

    - **amount**: Transaction amount (float with 2 decimal places)
    - **currency**: 3-letter currency code (e.g., USD, EUR, GBP)
    """
    # Convert amount from float to cents (integer)
    amount_cents = int(transaction_data.amount * 100)

    # Create transaction
    new_transaction = Transaction(
        user_id=current_user.id,
        amount=amount_cents,
        currency=transaction_data.currency,
    )

    db.add(new_transaction)
    await db.commit()
    await db.refresh(new_transaction)

    return new_transaction


@router.get("/", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List transactions for the authenticated user with pagination.

    Returns transactions ordered by created_at descending (newest first).

    - **page**: Page number (starts at 1)
    - **per_page**: Items per page (default 10, max 50)
    """
    # Calculate offset
    offset = (page - 1) * per_page

    # Query total count
    count_query = select(func.count()).select_from(Transaction).where(
        Transaction.user_id == current_user.id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Query transactions with pagination
    query = (
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(per_page)
        .offset(offset)
    )
    result = await db.execute(query)
    transactions = result.scalars().all()

    # Calculate total pages
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return TransactionListResponse(
        items=transactions,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/summary/", response_model=list[CurrencySummary])
async def get_transaction_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated transaction totals by currency for authenticated user.

    Returns a list of currency summaries ordered alphabetically by currency code.
    Returns empty array if user has no transactions.
    """
    # Query: GROUP BY currency, SUM amounts, ORDER BY currency
    query = (
        select(
            Transaction.currency,
            func.sum(Transaction.amount).label("total_amount"),
        )
        .where(Transaction.user_id == current_user.id)
        .group_by(Transaction.currency)
        .order_by(Transaction.currency)
    )

    result = await db.execute(query)
    rows = result.all()

    # Convert from cents to dollars and build response
    summary = [
        CurrencySummary(
            currency=row.currency,
            total=float(row.total_amount) / 100.0
        )
        for row in rows
    ]

    return summary
