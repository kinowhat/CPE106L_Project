from datetime import datetime, time, timedelta

from django import template
from django.utils import timezone

register = template.Library()


# ---------- helpers ----------

def _get(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _local(dt):
    return timezone.localtime(dt) if timezone.is_aware(dt) else dt


def _blend(light, strong, t):
    return tuple(round(l + (s - l) * t) for l, s in zip(light, strong))


# ---------- filters ----------

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def nth(items, i):
    try:
        return list(items)[int(i)]
    except (IndexError, TypeError, ValueError):
        return None


@register.filter
def segment(event, day):
    """The part of an event that falls on `day`, clipped to midnight."""
    if day is None:
        return None
    if isinstance(day, datetime):
        day = _local(day).date() if timezone.is_aware(day) else day.date()

    start, end = _local(event.start_time), _local(event.end_time)

    day_start = datetime.combine(day, time.min)
    if timezone.is_aware(start):
        day_start = timezone.make_aware(day_start, timezone.get_current_timezone())
    day_end = day_start + timedelta(days=1)

    seg_start = max(start, day_start)
    seg_end = min(end, day_end)
    if seg_end <= seg_start:
        return None

    return {
        "hour": seg_start.hour,
        "minute": seg_start.minute,
        "duration": max(int((seg_end - seg_start).total_seconds() // 60), 15),
        "continued": start < day_start,   # started on a previous day
        "continues": end > day_end,       # runs into the next day
    }


@register.filter
def column(grid, i):
    """All cells of one day column, top to bottom."""
    i = int(i)
    return [_get(row, "cells")[i] for row in grid]


@register.filter
def busy_blocks(grid, i):
    """Merge consecutive busy hours with identical availability into blocks."""
    i = int(i)
    blocks, current = [], None

    LIGHT = (252, 218, 212)   # barely anyone busy: pale red
    STRONG = (196, 28, 40)    # everyone busy: deep red

    for hour, row in enumerate(grid):
        cell = _get(row, "cells")[i]
        free, total = _get(cell, "free"), _get(cell, "total")
        labels = list(_get(cell, "labels") or [])
        busy = bool(total) and free < total
        sig = (free, tuple(labels))

        if busy and current and current["sig"] == sig and current["next_hour"] == hour:
            current["span"] += 1
            current["next_hour"] = hour + 1
            current["end"] = _get(cell, "end")
        elif busy:
            t = 1 - free / total            # 0 = nobody busy, 1 = everyone busy
            r, g, b = _blend(LIGHT, STRONG, t)
            current = {
                "hour": hour,
                "span": 1,
                "next_hour": hour + 1,
                "free": free,
                "total": total,
                "labels": labels,
                "start": _get(cell, "start"),
                "end": _get(cell, "end"),
                "color": f"rgb({r},{g},{b})",
                "text": "#ffffff" if t > 0.55 else "#1c1c1c",
                "sig": sig,
            }
            blocks.append(current)
        else:
            current = None

    return blocks