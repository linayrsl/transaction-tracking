"""Tests for currency conversion service."""
import pytest
import httpx
import respx
from respx import MockRouter

from app.services.currency_converter import CurrencyConverter


@pytest.fixture
def converter():
    """Create a CurrencyConverter instance with test API key."""
    return CurrencyConverter(api_key="test_api_key", timeout_seconds=10)


@pytest.mark.asyncio
@respx.mock
async def test_successful_conversion(converter: CurrencyConverter):
    """Test successful currency conversion."""
    # Mock API response
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 85.0,
            },
        )
    )

    # Convert 100.0000 USD (1,000,000 micro cents) to EUR
    result, error = await converter.convert(1000000, "USD", "EUR")

    assert error is None
    assert result == 850000  # 85.0000 EUR in micro cents


@pytest.mark.asyncio
@respx.mock
async def test_micro_cents_precision(converter: CurrencyConverter):
    """Test that micro cents precision is preserved."""
    # Mock API response with 4 decimal places
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/GBP/12.3456"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.79,
                "conversion_result": 9.753024,
            },
        )
    )

    # Convert 12.3456 USD (123,456 micro cents)
    result, error = await converter.convert(123456, "USD", "GBP")

    assert error is None
    assert result == 97530  # 9.753024 GBP = 97,530 micro cents (truncated)


@pytest.mark.asyncio
@respx.mock
async def test_different_currency_pairs(converter: CurrencyConverter):
    """Test conversion between different currency pairs."""
    # GBP to JPY
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/GBP/JPY/50.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 165.50,
                "conversion_result": 8275.0,
            },
        )
    )

    result, error = await converter.convert(500000, "GBP", "JPY")

    assert error is None
    assert result == 82750000  # 8275.0000 JPY in micro cents


@pytest.mark.asyncio
@respx.mock
async def test_zero_amount(converter: CurrencyConverter):
    """Test conversion of zero amount."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/0.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 0.0,
            },
        )
    )

    result, error = await converter.convert(0, "USD", "EUR")

    assert error is None
    assert result == 0


@pytest.mark.asyncio
@respx.mock
async def test_large_amount(converter: CurrencyConverter):
    """Test conversion of large amount."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/1000000.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 850000.0,
            },
        )
    )

    # 1,000,000.0000 USD = 10,000,000,000 micro cents
    result, error = await converter.convert(10000000000, "USD", "EUR")

    assert error is None
    assert result == 8500000000  # 850,000.0000 EUR


@pytest.mark.asyncio
@respx.mock
async def test_unsupported_currency_code(converter: CurrencyConverter):
    """Test API error for unsupported currency code."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/XXX/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "error",
                "error-type": "unsupported-code",
            },
        )
    )

    result, error = await converter.convert(1000000, "USD", "XXX")

    assert result is None
    assert error == "Currency code not supported"


@pytest.mark.asyncio
@respx.mock
async def test_invalid_api_key(converter: CurrencyConverter):
    """Test API error for invalid API key."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "error",
                "error-type": "invalid-key",
            },
        )
    )

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert error == "Invalid API key"


@pytest.mark.asyncio
@respx.mock
async def test_quota_exceeded(converter: CurrencyConverter):
    """Test API error for quota exceeded."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "error",
                "error-type": "quota-reached",
            },
        )
    )

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert error == "Currency API quota exceeded"


@pytest.mark.asyncio
@respx.mock
async def test_unknown_api_error(converter: CurrencyConverter):
    """Test handling of unknown API error type."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "error",
                "error-type": "some-unknown-error",
            },
        )
    )

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert error == "Currency API error: some-unknown-error"


@pytest.mark.asyncio
@respx.mock
async def test_http_error(converter: CurrencyConverter):
    """Test handling of HTTP error responses."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(return_value=httpx.Response(500, json={"error": "Internal Server Error"}))

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert "500" in error


@pytest.mark.asyncio
@respx.mock
async def test_timeout_error(converter: CurrencyConverter):
    """Test handling of timeout errors."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(side_effect=httpx.TimeoutException("Request timed out"))

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert error == "Currency conversion request timed out"


@pytest.mark.asyncio
@respx.mock
async def test_network_error(converter: CurrencyConverter):
    """Test handling of network errors."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(side_effect=httpx.ConnectError("Connection failed"))

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert "Failed to connect to currency API" in error


@pytest.mark.asyncio
@respx.mock
async def test_invalid_json_response(converter: CurrencyConverter):
    """Test handling of invalid JSON response."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(return_value=httpx.Response(200, text="Invalid JSON"))

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert "Failed to parse currency API response" in error


@pytest.mark.asyncio
@respx.mock
async def test_missing_conversion_result(converter: CurrencyConverter):
    """Test handling of response missing conversion_result."""
    respx.get(
        "https://v6.exchangerate-api.com/v6/test_api_key/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                # Missing conversion_result
            },
        )
    )

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert result is None
    assert error == "Invalid response from currency API"


@pytest.mark.asyncio
@respx.mock
async def test_custom_timeout():
    """Test that custom timeout is used."""
    converter = CurrencyConverter(api_key="test_key", timeout_seconds=5)

    assert converter.timeout_seconds == 5


@pytest.mark.asyncio
@respx.mock
async def test_custom_api_key():
    """Test that custom API key is used in request."""
    converter = CurrencyConverter(api_key="custom_key", timeout_seconds=10)

    respx.get(
        "https://v6.exchangerate-api.com/v6/custom_key/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 85.0,
            },
        )
    )

    result, error = await converter.convert(1000000, "USD", "EUR")

    assert error is None
    assert result == 850000
