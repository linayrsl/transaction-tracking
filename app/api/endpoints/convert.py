"""Currency conversion endpoints."""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.logging import app_logger
from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionResponse
from app.services.currency_converter import CurrencyConverter

router = APIRouter()


@router.get("/{transaction_id}/{target_currency}", response_model=TransactionResponse)
async def convert_transaction(
    transaction_id: int,
    target_currency: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Convert a transaction's amount to a different currency.

    - **transaction_id**: ID of the transaction to convert
    - **target_currency**: 3-letter target currency code (e.g., USD, EUR, GBP)

    Returns the original transaction's metadata with amount converted to target currency.
    """
    # Validate target currency format
    target_currency = target_currency.upper()
    if not re.match(r"^[A-Z]{3}$", target_currency):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Currency must be a 3-letter code"
        )

    # Fetch transaction (must belong to current user)
    query = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id
    )
    result = await db.execute(query)
    transaction = result.scalar_one_or_none()

    # Return 404 if not found or doesn't belong to user
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    # Optimization: If same currency, return original (no API call)
    if transaction.currency == target_currency:
        return transaction

    # Initialize currency converter and perform conversion
    converter = CurrencyConverter()
    converted_amount_micro_cents, error = await converter.convert(
        amount_micro_cents=transaction.amount,
        from_currency=transaction.currency,
        to_currency=target_currency
    )

    # Handle conversion failure
    if error is not None:
        # Log internal error details for debugging (to stdout)
        app_logger.error(
            f"Currency conversion failed for transaction {transaction_id} "
            f"({transaction.currency} -> {target_currency}): {error}"
        )
        # Return generic error to client (no internal details)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Currency conversion failed"
        )

    # Build response with original metadata + converted amount
    return TransactionResponse(
        id=transaction.id,
        amount=converted_amount_micro_cents,
        currency=target_currency,
        created_at=transaction.created_at
    )
