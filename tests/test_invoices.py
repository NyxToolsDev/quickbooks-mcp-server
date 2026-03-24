"""Tests for invoice tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from quickbooks_mcp.tools.invoices import register_invoice_tools


@pytest.fixture
def invoice_tools(mock_server: Any, mock_qbo: AsyncMock) -> dict[str, Any]:
    """Register invoice tools and return the tool functions."""
    register_invoice_tools(mock_server, mock_qbo)
    return mock_server.tools


class TestListInvoices:
    """Tests for the list_invoices tool."""

    async def test_list_invoices_returns_results(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock, sample_invoice: dict[str, Any]
    ) -> None:
        mock_qbo.query.return_value = [sample_invoice]

        result = await invoice_tools["list_invoices"]()

        assert "1042" in result
        assert "Acme Corp" in result
        assert "$2,500.00" in result
        mock_qbo.query.assert_called_once()

    async def test_list_invoices_empty(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        result = await invoice_tools["list_invoices"]()

        assert "No invoices found" in result

    async def test_list_invoices_status_filter_open(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock, sample_invoice: dict[str, Any]
    ) -> None:
        mock_qbo.query.return_value = [sample_invoice]

        result = await invoice_tools["list_invoices"](status="Open")

        query_str = mock_qbo.query.call_args[0][0]
        assert "Balance > '0'" in query_str

    async def test_list_invoices_status_filter_paid(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock, sample_paid_invoice: dict[str, Any]
    ) -> None:
        mock_qbo.query.return_value = [sample_paid_invoice]

        result = await invoice_tools["list_invoices"](status="Paid")

        query_str = mock_qbo.query.call_args[0][0]
        assert "Balance = '0'" in query_str
        assert "PAID" in result

    async def test_list_invoices_date_filter(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        await invoice_tools["list_invoices"](date_from="2026-01-01", date_to="2026-03-31")

        query_str = mock_qbo.query.call_args[0][0]
        assert "2026-01-01" in query_str
        assert "2026-03-31" in query_str

    async def test_list_invoices_customer_filter(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock, sample_invoice: dict[str, Any]
    ) -> None:
        mock_qbo.query.return_value = [sample_invoice]

        result = await invoice_tools["list_invoices"](customer_name="Acme")

        query_str = mock_qbo.query.call_args[0][0]
        assert "%Acme%" in query_str

    async def test_list_invoices_limit_clamped(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        await invoice_tools["list_invoices"](limit=500)

        query_str = mock_qbo.query.call_args[0][0]
        assert "MAXRESULTS 100" in query_str

    async def test_list_invoices_overdue_filter(
        self,
        invoice_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_overdue_invoice: dict[str, Any],
        sample_invoice: dict[str, Any],
    ) -> None:
        # sample_overdue_invoice has a past due date, sample_invoice may not
        mock_qbo.query.return_value = [sample_overdue_invoice, sample_invoice]

        result = await invoice_tools["list_invoices"](status="Overdue")

        # Should include the overdue one
        assert "Widget Co" in result or "overdue" in result.lower()


class TestGetInvoiceDetails:
    """Tests for the get_invoice_details tool."""

    async def test_get_details_returns_full_info(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock, sample_invoice: dict[str, Any]
    ) -> None:
        mock_qbo.get.return_value = sample_invoice

        result = await invoice_tools["get_invoice_details"](invoice_id="101")

        assert "Invoice #1042" in result
        assert "Acme Corp" in result
        assert "Website Design" in result
        assert "Hosting (Annual)" in result
        assert "$2,500.00" in result
        mock_qbo.get.assert_called_once_with("invoice", "101")

    async def test_get_details_shows_line_items(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock, sample_invoice: dict[str, Any]
    ) -> None:
        mock_qbo.get.return_value = sample_invoice

        result = await invoice_tools["get_invoice_details"](invoice_id="101")

        assert "Website Design" in result
        assert "$2,000.00" in result
        assert "Hosting (Annual)" in result
        assert "$500.00" in result


class TestGetOverdueInvoices:
    """Tests for the get_overdue_invoices tool."""

    async def test_overdue_returns_past_due(
        self,
        invoice_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_overdue_invoice: dict[str, Any],
    ) -> None:
        mock_qbo.query.return_value = [sample_overdue_invoice]

        result = await invoice_tools["get_overdue_invoices"]()

        assert "Widget Co" in result
        assert "$1,500.00" in result
        assert "days overdue" in result

    async def test_no_overdue_invoices(
        self, invoice_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        result = await invoice_tools["get_overdue_invoices"]()

        assert "No overdue invoices" in result

    async def test_overdue_sorted_by_days(
        self,
        invoice_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        invoices = [
            {
                "Id": "1",
                "DocNumber": "A",
                "TotalAmt": 100,
                "Balance": 100,
                "DueDate": "2026-02-01",
                "CustomerRef": {"name": "Customer A"},
            },
            {
                "Id": "2",
                "DocNumber": "B",
                "TotalAmt": 200,
                "Balance": 200,
                "DueDate": "2025-12-01",
                "CustomerRef": {"name": "Customer B"},
            },
        ]
        mock_qbo.query.return_value = invoices

        result = await invoice_tools["get_overdue_invoices"]()

        # Customer B should appear before Customer A (more overdue)
        pos_b = result.find("Customer B")
        pos_a = result.find("Customer A")
        assert pos_b < pos_a, "More overdue invoice should appear first"
