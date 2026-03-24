"""Tests for expense tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from quickbooks_mcp.tools.expenses import register_expense_tools


@pytest.fixture
def expense_tools(mock_server: Any, mock_qbo: AsyncMock) -> dict[str, Any]:
    """Register expense tools and return the tool functions."""
    register_expense_tools(mock_server, mock_qbo)
    return mock_server.tools


class TestListExpenses:
    """Tests for the list_expenses tool."""

    async def test_list_expenses_returns_results(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_expense: dict[str, Any],
    ) -> None:
        mock_qbo.query.return_value = [sample_expense]

        result = await expense_tools["list_expenses"]()

        assert "Office Depot" in result
        assert "$350.00" in result
        assert "1 expense(s)" in result

    async def test_list_expenses_empty(
        self, expense_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        result = await expense_tools["list_expenses"]()

        assert "No expenses found" in result

    async def test_list_expenses_date_filter(
        self, expense_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        await expense_tools["list_expenses"](date_from="2026-03-01", date_to="2026-03-31")

        query_str = mock_qbo.query.call_args[0][0]
        assert "2026-03-01" in query_str
        assert "2026-03-31" in query_str

    async def test_list_expenses_vendor_filter(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_expense: dict[str, Any],
    ) -> None:
        mock_qbo.query.return_value = [sample_expense]

        result = await expense_tools["list_expenses"](vendor_name="Office")

        assert "Office Depot" in result

    async def test_list_expenses_vendor_filter_no_match(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_expense: dict[str, Any],
    ) -> None:
        mock_qbo.query.return_value = [sample_expense]

        result = await expense_tools["list_expenses"](vendor_name="Amazon")

        assert "No expenses found for vendor matching 'Amazon'" in result

    async def test_list_expenses_amount_filter(
        self, expense_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        await expense_tools["list_expenses"](min_amount=100.0, max_amount=500.0)

        query_str = mock_qbo.query.call_args[0][0]
        assert "100" in query_str
        assert "500" in query_str

    async def test_list_expenses_limit_clamped(
        self, expense_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        await expense_tools["list_expenses"](limit=200)

        query_str = mock_qbo.query.call_args[0][0]
        assert "MAXRESULTS 100" in query_str

    async def test_list_expenses_total_calculation(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        expenses = [
            {
                "Id": "1",
                "TxnDate": "2026-03-10",
                "TotalAmt": 100.00,
                "EntityRef": {"name": "Vendor A"},
                "AccountRef": {"name": "Checking"},
                "PaymentType": "Cash",
            },
            {
                "Id": "2",
                "TxnDate": "2026-03-12",
                "TotalAmt": 250.50,
                "EntityRef": {"name": "Vendor B"},
                "AccountRef": {"name": "Checking"},
                "PaymentType": "Check",
            },
        ]
        mock_qbo.query.return_value = expenses

        result = await expense_tools["list_expenses"]()

        assert "$350.50" in result
        assert "2 expense(s)" in result


class TestGetTopExpenses:
    """Tests for the get_top_expenses tool."""

    async def test_top_expenses_by_category(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_expense: dict[str, Any],
    ) -> None:
        mock_qbo.query.return_value = [sample_expense]

        result = await expense_tools["get_top_expenses"](group_by="category")

        assert "Top Expenses by Category" in result
        # The expense has an AccountBasedExpenseLineDetail with "Office Supplies"
        assert "Office Supplies" in result or "$350.00" in result

    async def test_top_expenses_by_vendor(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_expense: dict[str, Any],
    ) -> None:
        mock_qbo.query.return_value = [sample_expense]

        result = await expense_tools["get_top_expenses"](group_by="vendor")

        assert "Top Expenses by Vendor" in result
        assert "Office Depot" in result

    async def test_top_expenses_empty_period(
        self, expense_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        mock_qbo.query.return_value = []

        result = await expense_tools["get_top_expenses"](period="last_month")

        assert "No expenses found" in result

    async def test_top_expenses_multiple_vendors(
        self,
        expense_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        expenses = [
            {
                "Id": "1",
                "TotalAmt": 500.00,
                "EntityRef": {"name": "Amazon"},
                "AccountRef": {"name": "Checking"},
                "Line": [],
                "TxnDate": "2026-03-10",
            },
            {
                "Id": "2",
                "TotalAmt": 300.00,
                "EntityRef": {"name": "Office Depot"},
                "AccountRef": {"name": "Checking"},
                "Line": [],
                "TxnDate": "2026-03-12",
            },
            {
                "Id": "3",
                "TotalAmt": 200.00,
                "EntityRef": {"name": "Amazon"},
                "AccountRef": {"name": "Checking"},
                "Line": [],
                "TxnDate": "2026-03-15",
            },
        ]
        mock_qbo.query.return_value = expenses

        result = await expense_tools["get_top_expenses"](group_by="vendor")

        # Amazon should be first ($700 > $300)
        pos_amazon = result.find("Amazon")
        pos_office = result.find("Office Depot")
        assert pos_amazon < pos_office, "Higher-spending vendor should appear first"
        assert "$1,000.00" in result  # Grand total
