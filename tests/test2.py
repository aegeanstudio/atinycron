# -*- coding: UTF-8 -*-

import asyncio
import logging

from atinycron import RegisterTask

logging.basicConfig(level=logging.INFO)

task = RegisterTask()


@task.register_run
async def run():
    print('run')
    await asyncio.sleep(2)


@task.register_setup
async def setup():
    pass


@task.register_teardown
async def teardown():
    pass


task.cron_config_set()


if __name__ == '__main__':
    asyncio.run(task.schedule_foreground())
