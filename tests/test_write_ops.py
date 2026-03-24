"""Tests for write operation tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from quickbooks_mcp.tools.write_ops import register_write_tools


@pytest.fixture
def write_tools(mock_server: Any, mock_qbo: AsyncMock) -> dict[str, Any]:
    """Register write tools with a valid premium license and return tool functions."""
    with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
        with patch("quickbooks_mcp.tools.write_ops.validate_license") as mock_validate:
            from quickbooks_mcp.utils.license import LicenseStatus

            mock_validate.return_value = LicenseStatus(
                valid=True,
                license_key="test_key",
                customer_name="Test User",
                status="active",
                error="",
            )
            register_write_tools(mock_server, mock_qbo, "test_key")
    return mock_server.tools


@pytest.fixture
def free_write_tools(mock_server: Any, mock_qbo: AsyncMock) -> dict[str, Any]:
    """Register write tools with no license (free tier)."""
    register_write_tools(mock_server, mock_qbo, "")
    return mock_server.tools


class TestPremiumGate:
    """Tests that write tools require premium license."""

    async def test_create_invoice_requires_license(
        self, free_write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_write_tools["create_invoice"](
            customer_id="1", line_items=[{"description": "Test", "amount": 100}]
        )

        assert "premium" in result.lower() or "license" in result.lower()
        mock_qbo.create.assert_not_called()

    async def test_record_payment_requires_license(
        self, free_write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_write_tools["record_payment"](invoice_id="1", amount=100)

        assert "premium" in result.lower() or "license" in result.lower()

    async def test_create_expense_requires_license(
        self, free_write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_write_tools["create_expense"](vendor_name="Test", amount=100)

        assert "premium" in result.lower() or "license" in result.lower()


class TestCreateInvoice:
    """Tests for the create_invoice tool."""

    async def test_create_invoice_success(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.create.return_value = {
            "Id": "999",
            "DocNumber": "1050",
            "TotalAmt": 2500.00,
            "CustomerRef": {"value": "42", "name": "Acme Corp"},
        }

        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_invoice"](
                    customer_id="42",
                    line_items=[
                        {"description": "Web Design", "amount": 2000},
                        {"description": "Hosting", "amount": 500},
                    ],
                    due_date="2026-04-30",
                    memo="March work",
                )

        assert "created successfully" in result
        assert "1050" in result
        assert "$2,500.00" in result
        mock_qbo.create.assert_called_once()

    async def test_create_invoice_missing_customer(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_invoice"](
                    customer_id="", line_items=[{"description": "Test", "amount": 100}]
                )

        assert "customer_id is required" in result

    async def test_create_invoice_no_line_items(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_invoice"](
                    customer_id="42", line_items=[]
                )

        assert "At least one line item" in result

    async def test_create_invoice_line_item_validation(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_invoice"](
                    customer_id="42",
                    line_items=[{"description": "Missing amount"}],
                )

        assert "must have either" in result


class TestRecordPayment:
    """Tests for the record_payment tool."""

    async def test_record_payment_success(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.get.return_value = {
            "Id": "101",
            "DocNumber": "1042",
            "Balance": 2500.00,
            "CustomerRef": {"value": "42", "name": "Acme Corp"},
        }
        mock_qbo.create.return_value = {"Id": "501"}

        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["record_payment"](
                    invoice_id="101",
                    amount=1000.00,
                    payment_date="2026-03-20",
                    payment_method="Check",
                    reference_number="4567",
                )

        assert "recorded successfully" in result
        assert "$1,000.00" in result
        assert "Remaining Bal" in result

    async def test_record_payment_full_amount(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.get.return_value = {
            "Id": "101",
            "DocNumber": "1042",
            "Balance": 500.00,
            "CustomerRef": {"value": "42", "name": "Acme Corp"},
        }
        mock_qbo.create.return_value = {"Id": "502"}

        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["record_payment"](
                    invoice_id="101", amount=500.00
                )

        assert "PAID IN FULL" in result

    async def test_record_payment_exceeds_balance(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.get.return_value = {
            "Id": "101",
            "DocNumber": "1042",
            "Balance": 100.00,
            "CustomerRef": {"value": "42", "name": "Acme Corp"},
        }

        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["record_payment"](
                    invoice_id="101", amount=500.00
                )

        assert "exceeds" in result
        mock_qbo.create.assert_not_called()

    async def test_record_payment_already_paid(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.get.return_value = {
            "Id": "101",
            "DocNumber": "1042",
            "Balance": 0,
            "CustomerRef": {"value": "42", "name": "Acme Corp"},
        }

        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["record_payment"](
                    invoice_id="101", amount=100.00
                )

        assert "already fully paid" in result

    async def test_record_payment_negative_amount(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["record_payment"](
                    invoice_id="101", amount=-50
                )

        assert "must be positive" in result


class TestCreateExpense:
    """Tests for the create_expense tool."""

    async def test_create_expense_success(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = [{"Id": "88", "DisplayName": "Office Depot"}]
        mock_qbo.create.return_value = {
            "Id": "601",
            "EntityRef": {"name": "Office Depot"},
        }

        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_expense"](
                    vendor_name="Office Depot",
                    amount=250.00,
                    category="Office Supplies",
                    payment_type="CreditCard",
                    expense_date="2026-03-15",
                    memo="Q1 supplies",
                )

        assert "recorded successfully" in result
        assert "$250.00" in result
        assert "Office Depot" in result

    async def test_create_expense_invalid_payment_type(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_expense"](
                    vendor_name="Test", amount=100, payment_type="Bitcoin"
                )

        assert "Invalid payment_type" in result

    async def test_create_expense_negative_amount(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_expense"](
                    vendor_name="Test", amount=-50
                )

        assert "must be positive" in result

    async def test_create_expense_missing_vendor(
        self, write_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        with patch("quickbooks_mcp.tools.write_ops.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.write_ops.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await write_tools["create_expense"](
                    vendor_name="", amount=100
                )

        assert "vendor_name is required" in result
