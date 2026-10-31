"""Shared display rules for market estimates in chaos-equivalent units."""
import math


def format_price(chaos, divine_chaos=None):
    if not isinstance(chaos, (int, float)) or not math.isfinite(chaos) or chaos < 0:
        return "Unknown"
    if divine_chaos and math.isfinite(divine_chaos) and divine_chaos > 0 and chaos > divine_chaos * 10:
        return f"{chaos / divine_chaos:.2f}".rstrip('0').rstrip('.') + 'd'
    return f"{math.floor(chaos + .5)}c"


def format_range(low, high, divine_chaos=None):
    first, last = format_price(low, divine_chaos), format_price(high, divine_chaos)
    return first if first == last else first + '–' + last
