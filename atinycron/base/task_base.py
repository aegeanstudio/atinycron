# -*- coding: UTF-8 -*-
import abc
import asyncio
import logging
from datetime import datetime, timedelta

from atinycron.base.cron_base import CronConfig
from atinycron.base.signal_base import ShutdownSignalHolder

logger = logging.getLogger('atinycron')


class TaskBase(metaclass=abc.ABCMeta):
    """
    Abstract base class for tasks.
    """

    def __init__(
            self, *, name: str = None, allow_concurrent: bool = False,
            crash_on_exception: bool = True, graceful_shutdown: bool = True,
    ):
        self.name: str = name
        self.allow_concurrent: bool = allow_concurrent
        self.crash_on_exception: bool = crash_on_exception
        self.graceful_shutdown: bool = graceful_shutdown    # TODO
        self._cron_config: CronConfig | None = None
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
        self._cron_config = CronConfig.make(
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

    def _task_done_callback(self, task: asyncio.Task) -> None:
        if not task.exception():
            self._running_tasks.discard(task)

    @abc.abstractmethod
    async def _setup(self):
        ...

    @abc.abstractmethod
    async def _teardown(self):
        ...

    @abc.abstractmethod
    async def _run(self):
        ...

    def _log_task_info(self):
        logger.info('Task Info:')
        logger.info(f'  name: {self.name}')
        logger.info(f'  allow_concurrent: {self.allow_concurrent}')
        logger.info(f'  crash_on_exception: {self.crash_on_exception}')
        logger.info(f'  graceful_shutdown: {self.graceful_shutdown}')

    def _log_cron_config(self):
        logger.info('CronConfig:')
        logger.info(f'  month: {self._cron_config.month}')
        logger.info(f'  day: {self._cron_config.day}')
        logger.info(f'  hour: {self._cron_config.hour}')
        logger.info(f'  minute: {self._cron_config.minute}')
        logger.info(f'  second: {self._cron_config.second}')
        logger.info(f'  weekday: {self._cron_config.weekday}')

    async def schedule_foreground(self):
        """
        Start the task in the foreground.
        """
        if self._cron_config is None:
            raise SyntaxError('Cron config not set')
        self._log_task_info()
        self._log_cron_config()
        await self._setup()
        signal_holder = ShutdownSignalHolder()
        try:
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

    async def start_once_immediately(self):
        self._log_task_info()
        self._log_cron_config()
        logger.info('Starting task once immediately...')
        await self._setup()
        try:
            await self._run()
        finally:
            await self._teardown()
