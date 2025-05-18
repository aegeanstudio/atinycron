# -*- coding: UTF-8 -*-

import asyncio
import logging
import time

from atinycron.base.task_base import TaskBase
from atinycron.base.typing_base import AsyncCallable

logger = logging.getLogger('atinycron')


class RegisterTask(TaskBase):

    def __init__(
            self, *, name: str = None, allow_concurrent: bool = False,
            crash_on_exception: bool = True, graceful_shutdown: bool = True,
    ):
        super(RegisterTask, self).__init__(
            name=name, allow_concurrent=allow_concurrent,
            crash_on_exception=crash_on_exception,
            graceful_shutdown=graceful_shutdown)
        self._setup_func: AsyncCallable | None = None
        self._teardown_func: AsyncCallable | None = None
        self._run_func: AsyncCallable | None = None

    def register_setup(
            self, setup_func: AsyncCallable,
    ) -> None:
        if not asyncio.iscoroutinefunction(setup_func):
            raise TypeError('setup_func must be an async function')
        self._setup_func = setup_func

    def register_teardown(
            self, teardown_func: AsyncCallable,
    ) -> None:
        if not asyncio.iscoroutinefunction(teardown_func):
            raise TypeError('teardown_func must be an async function')
        self._teardown_func = teardown_func

    def register_run(
            self, run_func: AsyncCallable,
    ) -> None:
        if not asyncio.iscoroutinefunction(run_func):
            raise TypeError('run_func must be an async function')
        self._run_func = run_func

    async def _setup(self):
        logger.info('Running setup...')
        await self._setup_func()
        logger.info('Setup complete.')

    async def _teardown(self):
        logger.info('Running teardown...')
        await self._teardown_func()
        logger.info('Teardown complete.')

    async def _run(self):
        start_at = time.time()
        await self._run_func()
        logger.info('Run complete. Total cost %.3fs', time.time() - start_at)
