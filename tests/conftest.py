"""Shared test fixtures for QuickBooks MCP Server tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from quickbooks_mcp.client.qbo_client import QBOClient
from quickbooks_mcp.config import Config
from quickbooks_mcp.utils.money import Money


@pytest.fixture
def mock_config() -> Config:
    """Create a test configuration."""
    return Config(
        qbo_client_id="test_client_id",
        qbo_client_secret="test_client_secret",
        qbo_redirect_uri="http://localhost:8080/callback",
        qbo_realm_id="123456789",
        license_key="test_license_key",
        log_level="DEBUG",
        sandbox=True,
    )


@pytest.fixture
def mock_qbo() -> AsyncMock:
    """Create a mock QBOClient with async methods.

    Returns an AsyncMock that behaves like QBOClient. All query/get/create
    methods return empty defaults -- override in individual tests.
    """
    qbo = AsyncMock(spec=QBOClient)
    qbo.query = AsyncMock(return_value=[])
    qbo.query_count = AsyncMock(return_value=0)
    qbo.get = AsyncMock(return_value={})
    qbo.create = AsyncMock(return_value={})
    qbo.update = AsyncMock(return_value={})
    qbo.get_report = AsyncMock(return_value={"Rows": {"Row": []}, "Header": {}, "Columns": {}})
    qbo.close = AsyncMock()
    return qbo


@pytest.fixture
def mock_server() -> MagicMock:
    """Create a mock MCP Server that captures tool registrations.

    Stores registered tools in a dict accessible via server.tools.
    """
    server = MagicMock()
    registered_tools: dict[str, Any] = {}

    def tool_decorator():
        def decorator(func: Any) -> Any:
            registered_tools[func.__name__] = func
            return func
        return decorator

    server.tool = tool_decorator
    server.tools = registered_tools
    return server


# -- Sample QuickBooks API response data --


@pytest.fixture
def sample_invoice() -> dict[str, Any]:
    """Sample invoice as returned by the QBO API."""
    return {
        "Id": "101",
        "DocNumber": "1042",
        "TxnDate": "2026-03-01",
        "DueDate": "2026-03-31",
        "TotalAmt": 2500.00,
        "Balance": 2500.00,
        "CustomerRef": {"value": "42", "name": "Acme Corp"},
        "Line": [
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": 2000.00,
                "Description": "Website Design",
                "SalesItemLineDetail": {
                    "Qty": 1,
                    "UnitPrice": 2000.00,
                },
            },
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": 500.00,
                "Description": "Hosting (Annual)",
                "SalesItemLineDetail": {
                    "Qty": 1,
                    "UnitPrice": 500.00,
                },
            },
            {
                "DetailType": "SubTotalLineDetail",
                "Amount": 2500.00,
            },
        ],
        "MetaData": {
            "CreateTime": "2026-03-01T10:00:00-08:00",
            "LastUpdatedTime": "2026-03-01T10:00:00-08:00",
        },
    }


@pytest.fixture
def sample_overdue_invoice() -> dict[str, Any]:
    """Sample overdue invoice (past due date with balance)."""
    return {
        "Id": "102",
        "DocNumber": "1039",
        "TxnDate": "2026-01-15",
        "DueDate": "2026-02-14",
        "TotalAmt": 1500.00,
        "Balance": 1500.00,
        "CustomerRef": {"value": "55", "name": "Widget Co"},
    }


@pytest.fixture
def sample_paid_invoice() -> dict[str, Any]:
    """Sample fully paid invoice."""
    return {
        "Id": "103",
        "DocNumber": "1035",
        "TxnDate": "2026-02-01",
        "DueDate": "2026-03-01",
        "TotalAmt": 750.00,
        "Balance": 0,
        "CustomerRef": {"value": "42", "name": "Acme Corp"},
    }


@pytest.fixture
def sample_expense() -> dict[str, Any]:
    """Sample purchase/expense from QBO API."""
    return {
        "Id": "201",
        "TxnDate": "2026-03-15",
        "TotalAmt": 350.00,
        "EntityRef": {"value": "88", "name": "Office Depot"},
        "AccountRef": {"value": "60", "name": "Checking"},
        "PaymentType": "CreditCard",
        "PrivateNote": "Office supplies for Q1",
        "Line": [
            {
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 350.00,
                "Description": "Printer paper and toner",
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": "70", "name": "Office Supplies"},
                },
            }
        ],
    }


@pytest.fixture
def sample_customer() -> dict[str, Any]:
    """Sample customer from QBO API."""
    return {
        "Id": "42",
        "DisplayName": "Acme Corp",
        "CompanyName": "Acme Corporation",
        "PrimaryEmailAddr": {"Address": "billing@acme.com"},
        "PrimaryPhone": {"FreeFormNumber": "(555) 123-4567"},
        "Balance": 2500.00,
        "Active": True,
        "MetaData": {
            "CreateTime": "2025-06-15T08:00:00-08:00",
        },
    }


@pytest.fixture
def sample_account() -> dict[str, Any]:
    """Sample bank account from QBO API."""
    return {
        "Id": "35",
        "Name": "Business Checking",
        "AccountType": "Bank",
        "AccountSubType": "Checking",
        "CurrentBalance": 45230.50,
        "Active": True,
    }


@pytest.fixture
def sample_payment() -> dict[str, Any]:
    """Sample payment from QBO API."""
    return {
        "Id": "301",
        "TotalAmt": 1000.00,
        "TxnDate": "2026-03-10",
        "CustomerRef": {"value": "42", "name": "Acme Corp"},
        "PaymentMethodRef": {"name": "Check"},
    }


@pytest.fixture
def sample_pnl_report() -> dict[str, Any]:
    """Sample Profit & Loss report response."""
    return {
        "Header": {
            "ReportName": "ProfitAndLoss",
            "DateMacro": "This Month",
            "StartPeriod": "2026-03-01",
            "EndPeriod": "2026-03-23",
        },
        "Columns": {
            "Column": [
                {"ColTitle": "", "ColType": "Account"},
                {"ColTitle": "Total", "ColType": "Money"},
            ]
        },
        "Rows": {
            "Row": [
                {
                    "type": "Section",
                    "Header": {"ColData": [{"value": "Income"}, {"value": ""}]},
                    "Rows": {
                        "Row": [
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Services"},
                                    {"value": "15000.00"},
                                ],
                            },
                        ]
                    },
                    "Summary": {
                        "ColData": [
                            {"value": "Total Income"},
                            {"value": "15000.00"},
                        ]
                    },
                },
                {
                    "type": "Section",
                    "Header": {"ColData": [{"value": "Expenses"}, {"value": ""}]},
                    "Rows": {
                        "Row": [
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Rent"},
                                    {"value": "3000.00"},
                                ],
                            },
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Payroll"},
                                    {"value": "8000.00"},
                                ],
                            },
                        ]
                    },
                    "Summary": {
                        "ColData": [
                            {"value": "Total Expenses"},
                            {"value": "11000.00"},
                        ]
                    },
                },
                {
                    "type": "Section",
                    "Summary": {
                        "ColData": [
                            {"value": "Net Income"},
                            {"value": "4000.00"},
                        ]
                    },
                },
            ]
        },
    }


@pytest.fixture
def sample_balance_sheet_report() -> dict[str, Any]:
    """Sample Balance Sheet report response."""
    return {
        "Header": {
            "ReportName": "BalanceSheet",
            "DateMacro": "Today",
        },
        "Columns": {
            "Column": [
                {"ColTitle": "", "ColType": "Account"},
                {"ColTitle": "Total", "ColType": "Money"},
            ]
        },
        "Rows": {
            "Row": [
                {
                    "type": "Section",
                    "Header": {"ColData": [{"value": "ASSETS"}, {"value": ""}]},
                    "Rows": {
                        "Row": [
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Total Bank Accounts"},
                                    {"value": "50000.00"},
                                ],
                            },
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Accounts Receivable (A/R)"},
                                    {"value": "12000.00"},
                                ],
                            },
                        ]
                    },
                    "Summary": {
                        "ColData": [
                            {"value": "Total Current Assets"},
                            {"value": "62000.00"},
                        ]
                    },
                },
                {
                    "type": "Section",
                    "Header": {"ColData": [{"value": "LIABILITIES"}, {"value": ""}]},
                    "Rows": {
                        "Row": [
                            {
                                "type": "Data",
                                "ColData": [
                                    {"value": "Accounts Payable"},
                                    {"value": "8000.00"},
                                ],
                            },
                        ]
                    },
                    "Summary": {
                        "ColData": [
                            {"value": "Total Current Liabilities"},
                            {"value": "8000.00"},
                        ]
                    },
                },
            ]
        },
    }
