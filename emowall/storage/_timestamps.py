"""Private exact UTC timestamp keys for the approved Storage v1.3 read profile."""

from __future__ import annotations

import calendar
import datetime
import re


class UnsupportedTimestamp(Exception):
    """The value is outside the finite v1.3 profile; it may still be valid ISO."""


_SUFFIX = r"(?:Z|\+00:00|\+0000|\+00)"
_FRACTION = r"(?P<fraction>[.,][0-9]+)?"
_EXTENDED = re.compile(
    r"(?P<year>[0-9]{4})"
    r"(?:-(?P<cal_month>[0-9]{2})-(?P<cal_day>[0-9]{2})"
    r"|-W(?P<week>[0-9]{2})-(?P<weekday>[0-9])"
    r"|-(?P<ordinal>[0-9]{3}))"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    + _FRACTION + _SUFFIX
)
_BASIC = re.compile(
    r"(?P<year>[0-9]{4})"
    r"(?:(?P<cal_month>[0-9]{2})(?P<cal_day>[0-9]{2})"
    r"|W(?P<week>[0-9]{2})(?P<weekday>[0-9])"
    r"|(?P<ordinal>[0-9]{3}))"
    r"T(?P<hour>[0-9]{2})(?P<minute>[0-9]{2})(?P<second>[0-9]{2})"
    + _FRACTION + _SUFFIX
)


def timestamp_key(value: str) -> tuple[int, int, str]:
    """Return (Gregorian ordinal, seconds in day, exact fractional digits).

    Fractional digits have trailing zeroes removed. Lexicographic comparison of
    these digit strings then matches numeric comparison with implicit zero
    padding, without float or microsecond conversion. No user text enters errors.

    ``UnsupportedTimestamp`` marks a profile boundary. ``ValueError`` or
    ``OverflowError`` means a matching shape has invalid fields or crosses the
    supported Gregorian range. Callers map either to the public error.
    """
    if not isinstance(value, str):
        raise UnsupportedTimestamp("unsupported or unrecognized timestamp")
    match = _EXTENDED.fullmatch(value) or _BASIC.fullmatch(value)
    if match is None:
        raise UnsupportedTimestamp("unsupported or unrecognized timestamp")

    year = int(match.group("year"))
    if not 1 <= year <= 9999:
        raise UnsupportedTimestamp("year outside supported profile")
    week = match.group("week")
    ordinal = match.group("ordinal")
    if week is not None:
        day = datetime.date.fromisocalendar(
            year, int(week), int(match.group("weekday"))
        )
    elif ordinal is not None:
        number = int(ordinal)
        last = 366 if calendar.isleap(year) else 365
        if not 1 <= number <= last:
            raise ValueError("invalid ordinal day")
        day = datetime.date(year, 1, 1) + datetime.timedelta(days=number - 1)
    else:
        day = datetime.date(
            year, int(match.group("cal_month")), int(match.group("cal_day"))
        )

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    fraction = match.group("fraction")
    fraction_digits = fraction[1:].rstrip("0") if fraction is not None else ""

    if hour > 24 or minute > 59 or second > 60:
        raise ValueError("invalid time field")
    if hour == 24:
        if minute or second or fraction_digits:
            raise ValueError("24:00 requires zero minutes, seconds and fraction")
    if second == 60:
        raise UnsupportedTimestamp("possible leap second outside supported profile")
    if hour == 24:
        day += datetime.timedelta(days=1)
        hour = 0
    return day.toordinal(), hour * 3600 + minute * 60 + second, fraction_digits
