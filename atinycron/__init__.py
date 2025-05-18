# -*- coding: UTF-8 -*-

import abc
import asyncio
import dataclasses
import re
import typing
from datetime import datetime, timedelta

__version__ = '0.0.1-dev1'


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class _CronField:
    values: typing.Sequence[int]
    is_wildcard: bool

    @classmethod
    def from_string(
            cls, *, field_str: str, min_value: int, max_value: int,
    ) -> '_CronField':
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
        return cls(
            values=tuple(sorted(values)), is_wildcard=is_wildcard,
        )


@dataclasses.dataclass(slots=True, kw_only=True)
class _CronConfig:
    month: str = '*'
    day: str = '*'
    hour: str = '*'
    minute: str = '*'
    second: str = '*'
    weekday: str = '*'
    month_field: _CronField
    day_field: _CronField
    hour_field: _CronField
    minute_field: _CronField
    second_field: _CronField
    weekday_field: _CronField

    @classmethod
    def make(
            cls, *, month: str = '*', day: str = '*',
            hour: str = '*', minute: str = '*', second: str = '*',
            weekday: str = '*',
    ) -> '_CronConfig':
        fields = (month, day, hour, minute, second, weekday)
        if all(map(lambda x: not bool(x), fields)):
            raise SyntaxError('At least one time field must be provided')
        month_field = _CronField.from_string(
            field_str=month, min_value=1, max_value=12)
        day_field = _CronField.from_string(
            field_str=day, min_value=1, max_value=31)
        hour_field = _CronField.from_string(
            field_str=hour, min_value=0, max_value=23)
        minute_field = _CronField.from_string(
            field_str=minute, min_value=0, max_value=59)
        second_field = _CronField.from_string(
            field_str=second, min_value=0, max_value=59)
        weekday_str = weekday.replace('0', '7')
        weekday_field = _CronField.from_string(
            field_str=weekday_str, min_value=1, max_value=7)
        return cls(
            month=month, day=day, hour=hour, minute=minute,
            second=second, weekday=weekday,
            month_field=month_field, day_field=day_field,
            hour_field=hour_field, minute_field=minute_field,
            second_field=second_field, weekday_field=weekday_field,
        )


class AbstractTask(metaclass=abc.ABCMeta):
    """
    Abstract base class for tasks.
    """
    def __init__(
            self, *, name: str = None, allow_concurrent: bool = False,
    ):
        self.name = name
        self.allow_concurrent = allow_concurrent
        self._cron_config: _CronConfig | None = None

    def cron_config_set(
            self, *, month: str = '*', day: str = '*',
            hour: str = '*', minute: str = '*', second: str = '*',
            weekday: str = '*',
    ) -> None:
        """
        Configure the cron schedule for the task.
        """
        self._cron_config = _CronConfig.make(
            month=month, day=day, hour=hour, minute=minute,
            second=second, weekday=weekday)

    def _should_trigger(self, now: datetime) -> bool:
        second_ok = now.second in self._cron_config.second_field.values
        minute_ok = now.minute in self._cron_config.minute_field.values
        hour_ok = now.hour in self._cron_config.hour_field.values
        month_ok = now.month in self._cron_config.month_field.values

        day_ok = now.day in self._cron_config.day_field.values
        weekday_ok = now.isoweekday() in self._cron_config.weekday_field.values
        day_wild = self._cron_config.day_field.is_wildcard
        weekday_wild = self._cron_config.weekday_field.is_wildcard

        date_ok = (day_ok or weekday_ok) if not (
                    day_wild and weekday_wild) else True

        return all((second_ok, minute_ok, hour_ok, month_ok, date_ok))

    async def _setup(self):
        await self.setup()

    @abc.abstractmethod
    async def setup(self):
        ...

    @abc.abstractmethod
    async def teardown(self):
        ...

    @abc.abstractmethod
    async def run(self):
        ...

    async def schedule_foreground(self):
        """
        Start the task in the foreground.
        """
        if self._cron_config is None:
            raise SyntaxError('Cron config not set')
        await self.setup()
        running_tasks = set()
        task_done_callback = lambda t: running_tasks.discard(t)     # noqa
        try:
            while True:
                now = datetime.now()
                now_without_microseconds = now.replace(microsecond=0)
                if self._should_trigger(now=now):
                    print(f'Task triggered at {now}.')
                    if (not running_tasks) or self.allow_concurrent:
                        created_task = asyncio.create_task(self.run())
                        running_tasks.add(created_task)
                        created_task.add_done_callback(task_done_callback)
                    else:
                        print('Task already running, skipped.')
                next_second = now_without_microseconds + timedelta(seconds=1)
                await asyncio.sleep((next_second - now).total_seconds())
        except asyncio.CancelledError:
            if running_tasks:
                print('Waiting for task to finish...')
                for task in running_tasks:
                    task.remove_done_callback(task_done_callback)
                await asyncio.gather(*running_tasks, return_exceptions=True)
            print('All Task Done.')
        finally:
            await self.teardown()
