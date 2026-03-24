"""Builder for QuickBooks Query Language (similar to SQL) statements.

QuickBooks uses a simplified SQL-like query language for retrieving entities.
This builder provides a type-safe, injection-resistant way to construct queries.

Reference: https://developer.intuit.com/app/developer/qbo/docs/develop/explore-the-quickbooks-online-api/data-queries
"""

from __future__ import annotations

import re
from typing import Literal


# Characters that need escaping in QBO query string values
_UNSAFE_PATTERN = re.compile(r"['\\\x00-\x1f]")


def _escape_value(value: str) -> str:
    """Escape a string value for safe inclusion in a QBO query.

    Prevents injection by escaping single quotes and backslashes.

    Args:
        value: The raw string value.

    Returns:
        The escaped string (without surrounding quotes).
    """
    def _replace(match: re.Match[str]) -> str:
        char = match.group(0)
        if char == "'":
            return "\\'"
        if char == "\\":
            return "\\\\"
        # Strip control characters
        return ""

    return _UNSAFE_PATTERN.sub(_replace, value)


class QueryBuilder:
    """Fluent builder for QuickBooks Query Language statements.

    Usage:
        query = (
            QueryBuilder("Invoice")
            .select(["Id", "DocNumber", "TotalAmt", "Balance"])
            .where("Balance", ">", "0")
            .where("TxnDate", ">=", "2026-01-01")
            .order_by("TxnDate", "DESC")
            .limit(100)
            .build()
        )
    """

    VALID_OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "LIKE", "IN"}

    def __init__(self, entity: str) -> None:
        """Initialize the query builder for a specific entity type.

        Args:
            entity: The QuickBooks entity (e.g., Invoice, Customer, Purchase).
        """
        self._entity = entity
        self._columns: list[str] = ["*"]
        self._conditions: list[str] = []
        self._order_field: str | None = None
        self._order_dir: Literal["ASC", "DESC"] = "ASC"
        self._max_results: int | None = None
        self._start_position: int | None = None

    def select(self, columns: list[str]) -> QueryBuilder:
        """Set the columns to retrieve.

        Args:
            columns: List of column names.

        Returns:
            Self for chaining.
        """
        self._columns = columns
        return self

    def where(self, field: str, operator: str, value: str) -> QueryBuilder:
        """Add a WHERE condition.

        Args:
            field: The field name to filter on.
            operator: Comparison operator (=, !=, <, >, <=, >=, LIKE, IN).
            value: The value to compare against.

        Returns:
            Self for chaining.

        Raises:
            ValueError: If the operator is not valid.
        """
        op = operator.upper()
        if op not in self.VALID_OPERATORS:
            raise ValueError(
                f"Invalid operator '{operator}'. Must be one of: {self.VALID_OPERATORS}"
            )

        if op == "IN":
            # IN values should already be formatted as ('val1', 'val2')
            condition = f"{field} IN {value}"
        else:
            escaped = _escape_value(value)
            condition = f"{field} {op} '{escaped}'"

        self._conditions.append(condition)
        return self

    def where_in(self, field: str, values: list[str]) -> QueryBuilder:
        """Add a WHERE IN condition.

        Args:
            field: The field name.
            values: List of values for the IN clause.

        Returns:
            Self for chaining.
        """
        if not values:
            return self

        escaped = ", ".join(f"'{_escape_value(v)}'" for v in values)
        self._conditions.append(f"{field} IN ({escaped})")
        return self

    def order_by(self, field: str, direction: Literal["ASC", "DESC"] = "ASC") -> QueryBuilder:
        """Set the ORDER BY clause.

        Args:
            field: Field to order by.
            direction: Sort direction.

        Returns:
            Self for chaining.
        """
        self._order_field = field
        self._order_dir = direction
        return self

    def limit(self, max_results: int) -> QueryBuilder:
        """Set the maximum number of results.

        Args:
            max_results: Maximum results to return (QBO max is 1000).

        Returns:
            Self for chaining.
        """
        self._max_results = min(max_results, 1000)
        return self

    def offset(self, start_position: int) -> QueryBuilder:
        """Set the starting position for pagination.

        Args:
            start_position: 1-based start position.

        Returns:
            Self for chaining.
        """
        self._start_position = max(1, start_position)
        return self

    def build(self) -> str:
        """Build the final query string.

        Returns:
            The complete QBO query string.
        """
        columns = ", ".join(self._columns)
        query = f"SELECT {columns} FROM {self._entity}"

        if self._conditions:
            conditions = " AND ".join(self._conditions)
            query += f" WHERE {conditions}"

        if self._order_field:
            query += f" ORDERBY {self._order_field} {self._order_dir}"

        if self._max_results is not None:
            query += f" MAXRESULTS {self._max_results}"

        if self._start_position is not None:
            query += f" STARTPOSITION {self._start_position}"

        return query

    def count(self) -> str:
        """Build a COUNT query.

        Returns:
            The count query string.
        """
        query = f"SELECT COUNT(*) FROM {self._entity}"

        if self._conditions:
            conditions = " AND ".join(self._conditions)
            query += f" WHERE {conditions}"

        return query
