# -*- coding: UTF-8 -*-

import abc
import logging
import time

from atinycron.base.task_base import TaskBase

logger = logging.getLogger('atinycron')


class AbstractTask(TaskBase, metaclass=abc.ABCMeta):
    """
    Abstract base class for tasks.
    """

    def __init__(
            self, *, name: str = None, allow_concurrent: bool = False,
            crash_on_exception: bool = True, graceful_shutdown: bool = True,
    ):
        super(AbstractTask, self).__init__(
            name=name, allow_concurrent=allow_concurrent,
            crash_on_exception=crash_on_exception,
            graceful_shutdown=graceful_shutdown)

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
