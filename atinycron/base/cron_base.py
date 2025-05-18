# -*- coding: UTF-8 -*-
import dataclasses
import re
import typing


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class CronField:
    values: typing.Sequence[int]
    is_wildcard: bool

    @classmethod
    def from_string(
            cls, *, field_str: str, min_value: int, max_value: int,
    ) -> 'CronField':
        values = set()
        parts = field_str.split(',')
        all_possible = set(range(min_value, max_value + 1))

        for part in parts:
            step = 1
            if '/' in part:
                part, step_str = part.split('/', 1)
                step = int(step_str)
                if step < 1:
                    raise SyntaxError(f'Step must be ≥1: {step_str}')

            if part == '*':
                start = min_value
                end = max_value
            elif '-' in part:
                start, end = part.split('-', 1)
                start = int(start)
                end = int(end)
                if start < min_value or end > max_value or start > end:
                    raise SyntaxError(
                        f'Invalid range {part} for {min_value}-{max_value}')
            else:
                if not re.match(r'^\d+$', part):
                    raise SyntaxError(f'Invalid value: {part}')
                start = end = int(part)

            current = start
            while current <= end:
                if min_value <= current <= max_value:
                    for value in range(current, min(end, max_value) + 1, step):
                        values.add(value)
                    break
                current += step

        if not values:
            raise SyntaxError(f'No values parsed from {field_str}')

        is_wildcard = (values == all_possible)
        return cls(values=sorted(values), is_wildcard=is_wildcard)


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class CronConfig:
    month: str = '*'
    day: str = '*'
    hour: str = '*'
    minute: str = '*'
    second: str = '*'
    weekday: str = '*'
    month_field: CronField
    day_field: CronField
    hour_field: CronField
    minute_field: CronField
    second_field: CronField
    weekday_field: CronField

    @classmethod
    def make(
            cls, *, month: str = '*', day: str = '*',
            hour: str = '*', minute: str = '*', second: str = '*',
            weekday: str = '*',
    ) -> 'CronConfig':
        fields = (month, day, hour, minute, second, weekday)
        if all(map(lambda x: not bool(x), fields)):
            raise SyntaxError('At least one time field must be provided')
        month_field = CronField.from_string(
            field_str=month, min_value=1, max_value=12)
        day_field = CronField.from_string(
            field_str=day, min_value=1, max_value=31)
        hour_field = CronField.from_string(
            field_str=hour, min_value=0, max_value=23)
        minute_field = CronField.from_string(
            field_str=minute, min_value=0, max_value=59)
        second_field = CronField.from_string(
            field_str=second, min_value=0, max_value=59)
        weekday_str = weekday.replace('0', '7')
        weekday_field = CronField.from_string(
            field_str=weekday_str, min_value=1, max_value=7)
        return cls(
            month=month, day=day, hour=hour, minute=minute,
            second=second, weekday=weekday,
            month_field=month_field, day_field=day_field,
            hour_field=hour_field, minute_field=minute_field,
            second_field=second_field, weekday_field=weekday_field,
        )
