# -*- coding: UTF-8 -*-

import abc
import asyncio
import dataclasses
import logging
import re
import signal
import time
import types
import typing
from datetime import datetime, timedelta

__version__ = '0.0.1-dev7'

logger = logging.getLogger(__name__)

_SHUTDOWN_SIGNALS = frozenset({
    signal.SIGINT,
    signal.SIGTERM,
    signal.SIGQUIT,
})


class ShutdownSignalHolder:

    def __init__(self):
        self._current_signal = list()
        for sig in _SHUTDOWN_SIGNALS:
            signal.signal(signalnum=sig, handler=self.set_signal)

    @property
    def shutdown_signal_received(self) -> bool:
        if self._current_signal:
            logger.debug('All received signals: %s', self._current_signal)
            matched_signals = set(self._current_signal) & _SHUTDOWN_SIGNALS
            if matched_signals:
                logger.debug('matched signals: %s', matched_signals)
                return True
        return False

    def set_signal(self, received_signal: int, frame: types.FrameType) -> None:
        logger.info('Signal %s received.', received_signal)
        logger.debug('set_signal called with frame: %s', frame)
        self._current_signal.append(received_signal)


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
            crash_on_exception: bool = True,
    ):
        self.name: str = name
        self.allow_concurrent: bool = allow_concurrent
        self.crash_on_exception: bool = crash_on_exception
        self._cron_config: _CronConfig | None = None
        self._running_tasks: set[asyncio.Task] = set()

    @property
    def _name_left_blank(self):
        return f' {self.name}' if self.name else ''

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

    @abc.abstractmethod
    async def setup(self):
        ...

    @abc.abstractmethod
    async def teardown(self):
        ...

    @abc.abstractmethod
    async def run(self):
        ...

    async def _setup(self):
        logger.info('Running setup...')
        await self.setup()
        logger.info('Setup complete.')

    async def _teardown(self):
        logger.info('Running teardown...')
        await self.teardown()
        logger.info('Teardown complete.')

    async def _run(self):
        start_at = time.time()
        await self.run()
        logger.info('Run complete. Total cost %.3fs', time.time() - start_at)

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

    def _task_done_callback(self, task: asyncio.Task) -> None:
        if not task.exception():
            self._running_tasks.discard(task)

    async def schedule_foreground(self):
        """
        Start the task in the foreground.
        """
        if self._cron_config is None:
            raise SyntaxError('Cron config not set')
        logger.info('Task Info:')
        logger.info(f'  name: {self.name}')
        logger.info(f'  allow_concurrent: {self.allow_concurrent}')
        logger.info('CronConfig:')
        logger.info(f'  month: {self._cron_config.month}')
        logger.info(f'  day: {self._cron_config.day}')
        logger.info(f'  hour: {self._cron_config.hour}')
        logger.info(f'  minute: {self._cron_config.minute}')
        logger.info(f'  second: {self._cron_config.second}')
        logger.info(f'  weekday: {self._cron_config.weekday}')
        await self._setup()
        try:
            signal_holder = ShutdownSignalHolder()
            while True:
                if signal_holder.shutdown_signal_received:
                    logger.info('Shutdown signal received, exiting...')
                    raise asyncio.CancelledError
                now = datetime.now()
                now_without_microseconds = now.replace(microsecond=0)
                if self._should_trigger(now=now):
                    logger.info(
                        f'Task{self._name_left_blank} triggered at {now}.')
                    if (not self._running_tasks) or self.allow_concurrent:
                        created_task = asyncio.create_task(self._run())
                        self._running_tasks.add(created_task)
                        created_task.add_done_callback(
                            self._task_done_callback)
                    else:
                        logger.info('Task already running, skipped.')
                next_second = now_without_microseconds + timedelta(seconds=1)
                await asyncio.sleep((next_second - now).total_seconds())
                for t in self._running_tasks:
                    if t.done():
                        if exp := t.exception():
                            self._running_tasks.remove(t)
                            if self.crash_on_exception:
                                raise exp
                            else:
                                logger.error(exp, exc_info=True)
        except asyncio.CancelledError:
            if self._running_tasks:
                logger.info('Waiting for task to finish...')
                for task in self._running_tasks:
                    task.remove_done_callback(self._task_done_callback)
                res = await asyncio.gather(
                    *self._running_tasks, return_exceptions=True)
                logger.info('Tasks finished with results: %s', res)
            logger.info('All Task Done.')
        finally:
            await self._teardown()
