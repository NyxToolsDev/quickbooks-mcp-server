"""Tests for financial report tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from quickbooks_mcp.tools.reports import register_report_tools


@pytest.fixture
def report_tools(mock_server: Any, mock_qbo: AsyncMock) -> dict[str, Any]:
    """Register report tools with a valid premium license and return tool functions."""
    with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
        with patch("quickbooks_mcp.tools.reports.validate_license") as mock_validate:
            from quickbooks_mcp.utils.license import LicenseStatus

            mock_validate.return_value = LicenseStatus(
                valid=True,
                license_key="test_key",
                customer_name="Test User",
                status="active",
                error="",
            )
            register_report_tools(mock_server, mock_qbo, "test_key")
    return mock_server.tools


@pytest.fixture
def free_report_tools(mock_server: Any, mock_qbo: AsyncMock) -> dict[str, Any]:
    """Register report tools with no license (free tier)."""
    register_report_tools(mock_server, mock_qbo, "")
    return mock_server.tools


class TestPremiumGate:
    """Tests that premium tools correctly check license status."""

    async def test_reports_require_license(
        self, free_report_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_report_tools["get_profit_and_loss"]()

        assert "premium" in result.lower() or "license" in result.lower()
        # Should not have made any API calls
        mock_qbo.get_report.assert_not_called()

    async def test_balance_sheet_requires_license(
        self, free_report_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_report_tools["get_balance_sheet"]()

        assert "premium" in result.lower() or "license" in result.lower()

    async def test_cash_flow_requires_license(
        self, free_report_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_report_tools["get_cash_flow"]()

        assert "premium" in result.lower() or "license" in result.lower()

    async def test_ar_aging_requires_license(
        self, free_report_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_report_tools["get_accounts_receivable_aging"]()

        assert "premium" in result.lower() or "license" in result.lower()

    async def test_ap_aging_requires_license(
        self, free_report_tools: dict[str, Any], mock_qbo: AsyncMock
    ) -> None:
        result = await free_report_tools["get_accounts_payable_aging"]()

        assert "premium" in result.lower() or "license" in result.lower()


class TestProfitAndLoss:
    """Tests for the get_profit_and_loss tool."""

    async def test_pnl_returns_formatted_report(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_pnl_report: dict[str, Any],
    ) -> None:
        mock_qbo.get_report.return_value = sample_pnl_report

        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await report_tools["get_profit_and_loss"]()

        assert "ProfitAndLoss" in result or "Profit" in result
        assert "Income" in result
        assert "Expenses" in result
        mock_qbo.get_report.assert_called_once()

    async def test_pnl_custom_date_range(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_pnl_report: dict[str, Any],
    ) -> None:
        mock_qbo.get_report.return_value = sample_pnl_report

        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await report_tools["get_profit_and_loss"](
                    period="custom",
                    date_from="2026-01-01",
                    date_to="2026-03-31",
                )

        call_args = mock_qbo.get_report.call_args
        assert call_args[0][0] == "ProfitAndLoss"
        params = call_args[1].get("params") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["params"]
        assert params["start_date"] == "2026-01-01"
        assert params["end_date"] == "2026-03-31"


class TestBalanceSheet:
    """Tests for the get_balance_sheet tool."""

    async def test_balance_sheet_returns_report(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
        sample_balance_sheet_report: dict[str, Any],
    ) -> None:
        mock_qbo.get_report.return_value = sample_balance_sheet_report

        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                result = await report_tools["get_balance_sheet"]()

        assert "BalanceSheet" in result or "Balance Sheet" in result
        assert "ASSETS" in result or "Asset" in result


class TestCashFlow:
    """Tests for the get_cash_flow tool."""

    async def test_cash_flow_calls_correct_report(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                await report_tools["get_cash_flow"]()

        call_args = mock_qbo.get_report.call_args
        assert call_args[0][0] == "CashFlow"


class TestAgingReports:
    """Tests for the aging report tools."""

    async def test_ar_aging_calls_correct_report(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                await report_tools["get_accounts_receivable_aging"]()

        call_args = mock_qbo.get_report.call_args
        assert call_args[0][0] == "AgedReceivableDetail"

    async def test_ap_aging_calls_correct_report(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                await report_tools["get_accounts_payable_aging"]()

        call_args = mock_qbo.get_report.call_args
        assert call_args[0][0] == "AgedPayableDetail"

    async def test_ar_aging_with_custom_date(
        self,
        report_tools: dict[str, Any],
        mock_qbo: AsyncMock,
    ) -> None:
        with patch("quickbooks_mcp.tools.reports.require_premium", return_value=None):
            with patch("quickbooks_mcp.tools.reports.validate_license") as mv:
                from quickbooks_mcp.utils.license import LicenseStatus

                mv.return_value = LicenseStatus(
                    valid=True, license_key="k", customer_name="", status="active", error=""
                )
                await report_tools["get_accounts_receivable_aging"](as_of_date="2026-02-28")

        call_args = mock_qbo.get_report.call_args
        params = call_args[1].get("params") or call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["params"]
        assert params["end_date"] == "2026-02-28"
