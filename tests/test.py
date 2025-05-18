# -*- coding: UTF-8 -*-
import asyncio
import logging

from atinycron import AbstractTask

logging.basicConfig(level=logging.INFO)


class TestTask(AbstractTask):
    async def setup(self):
        print('Setup')

    async def teardown(self):
        print('Teardown')

    async def run(self):
        print('Running task')
        await asyncio.sleep(2)
        print('Task finished')
        raise


if __name__ == '__main__':
    test_task = TestTask(name='test_task', allow_concurrent=True)
    test_task.cron_config_set()
    asyncio.run(test_task.schedule_foreground())
