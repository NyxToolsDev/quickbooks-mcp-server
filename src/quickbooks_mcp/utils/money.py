"""Decimal-based money handling to avoid floating-point errors.

All monetary calculations in the server should use the Money class to
ensure precision. QuickBooks returns amounts as floats in JSON, but we
convert them to Decimal immediately upon receipt.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Union


class Money:
    """Immutable decimal money value with proper rounding.

    Wraps Python's Decimal for safe currency arithmetic. All operations
    return new Money instances.
    """

    __slots__ = ("_amount",)

    def __init__(self, amount: Union[str, float, int, Decimal, "Money"] = 0) -> None:
        if isinstance(amount, Money):
            self._amount = amount._amount
        elif isinstance(amount, Decimal):
            self._amount = amount
        elif isinstance(amount, float):
            # Convert float via string to avoid float precision issues
            self._amount = Decimal(str(amount))
        else:
            self._amount = Decimal(str(amount))

    @property
    def amount(self) -> Decimal:
        """The underlying Decimal value."""
        return self._amount

    def round(self, places: int = 2) -> Money:
        """Round to the specified number of decimal places."""
        quantize_str = "0." + "0" * places
        return Money(self._amount.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))

    def __add__(self, other: Money | int | float) -> Money:
        if isinstance(other, (int, float)):
            other = Money(other)
        return Money(self._amount + other._amount)

    def __radd__(self, other: Money | int | float) -> Money:
        return self.__add__(other)

    def __sub__(self, other: Money | int | float) -> Money:
        if isinstance(other, (int, float)):
            other = Money(other)
        return Money(self._amount - other._amount)

    def __mul__(self, other: int | float | Decimal) -> Money:
        return Money(self._amount * Decimal(str(other)))

    def __truediv__(self, other: int | float | Decimal) -> Money:
        return Money(self._amount / Decimal(str(other)))

    def __neg__(self) -> Money:
        return Money(-self._amount)

    def __abs__(self) -> Money:
        return Money(abs(self._amount))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self._amount == other._amount
        if isinstance(other, (int, float, Decimal)):
            return self._amount == Decimal(str(other))
        return NotImplemented

    def __lt__(self, other: Money | int | float) -> bool:
        if isinstance(other, Money):
            return self._amount < other._amount
        return self._amount < Decimal(str(other))

    def __le__(self, other: Money | int | float) -> bool:
        if isinstance(other, Money):
            return self._amount <= other._amount
        return self._amount <= Decimal(str(other))

    def __gt__(self, other: Money | int | float) -> bool:
        if isinstance(other, Money):
            return self._amount > other._amount
        return self._amount > Decimal(str(other))

    def __ge__(self, other: Money | int | float) -> bool:
        if isinstance(other, Money):
            return self._amount >= other._amount
        return self._amount >= Decimal(str(other))

    def __float__(self) -> float:
        return float(self._amount)

    def __str__(self) -> str:
        rounded = self.round(2)
        return f"${rounded._amount:,.2f}"

    def __repr__(self) -> str:
        return f"Money('{self._amount}')"

    def to_float(self) -> float:
        """Convert to float for JSON serialization."""
        return float(self.round(2)._amount)

    @classmethod
    def sum(cls, values: list[Money]) -> Money:
        """Sum a list of Money values."""
        total = Decimal("0")
        for v in values:
            total += v._amount
        return cls(total)

    @classmethod
    def from_qbo(cls, value: float | str | int | None) -> Money:
        """Create Money from a QuickBooks API response value.

        Args:
            value: The amount from the QBO API (typically a float).

        Returns:
            A Money instance, or Money(0) if value is None.
        """
        if value is None:
            return cls(0)
        return cls(value)
