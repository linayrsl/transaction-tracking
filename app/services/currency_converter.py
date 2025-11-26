"""Currency conversion service using Exchange Rate API."""
import httpx
from typing import Tuple

from app.config import settings


class CurrencyConverter:
    """Service for converting amounts between currencies using Exchange Rate API."""

    BASE_URL = "https://v6.exchangerate-api.com/v6"

    def __init__(
        self,
        api_key: str = settings.EXCHANGE_RATE_API_KEY,
        timeout_seconds: int = settings.EXCHANGE_RATE_API_TIMEOUT_SECONDS,
    ):
        """
        Initialize the currency converter.

        Args:
            api_key: Exchange Rate API key
            timeout_seconds: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def convert(
        self,
        amount_micro_cents: int,
        from_currency: str,
        to_currency: str,
    ) -> Tuple[int | None, str | None]:
        """
        Convert amount from one currency to another.

        Args:
            amount_micro_cents: Amount in micro cents (1/10,000 of currency unit)
            from_currency: Source currency code (e.g., "USD")
            to_currency: Target currency code (e.g., "EUR")

        Returns:
            Tuple of (converted_amount_micro_cents, error_message)
            - On success: (converted_amount, None)
            - On failure: (None, error_message)
        """
        # Convert micro cents to currency units for API call
        amount_currency_units = amount_micro_cents / 10000.0

        # Build API URL
        url = f"{self.BASE_URL}/{self.api_key}/pair/{from_currency}/{to_currency}/{amount_currency_units}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                # Check for API-level errors
                if data.get("result") == "error":
                    error_type = data.get("error-type", "unknown")
                    return None, self._translate_api_error(error_type)

                # Extract conversion result
                conversion_result = data.get("conversion_result")
                if conversion_result is None:
                    return None, "Invalid response from currency API"

                # Convert back to micro cents
                result_micro_cents = int(conversion_result * 10000)
                return result_micro_cents, None

        except httpx.TimeoutException:
            return None, "Currency conversion request timed out"
        except httpx.HTTPStatusError as e:
            return None, f"Currency API returned error: {e.response.status_code}"
        except httpx.RequestError as e:
            return None, f"Failed to connect to currency API: {str(e)}"
        except (ValueError, KeyError) as e:
            return None, f"Failed to parse currency API response: {str(e)}"
        except Exception as e:
            return None, f"Unexpected error during currency conversion: {str(e)}"

    def _translate_api_error(self, error_type: str) -> str:
        """
        Translate Exchange Rate API error types to user-friendly messages.

        Args:
            error_type: Error type from the API response

        Returns:
            User-friendly error message
        """
        error_messages = {
            "unsupported-code": "Currency code not supported",
            "malformed-request": "Invalid currency conversion request",
            "invalid-key": "Invalid API key",
            "inactive-account": "Currency API account is inactive",
            "quota-reached": "Currency API quota exceeded",
        }
        return error_messages.get(error_type, f"Currency API error: {error_type}")
