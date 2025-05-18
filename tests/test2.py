# -*- coding: UTF-8 -*-

import asyncio
import functools
import logging

import click

from atinycron import RegisterTask

logging.basicConfig(level=logging.INFO)

task = RegisterTask()


async def run(seconds: int):
    print('running task')
    await asyncio.sleep(seconds)
    print('task done')


@task.register_setup
async def setup():
    pass


@task.register_teardown
async def teardown():
    pass


task.cron_config_set()


@click.command()
@click.option('--seconds', type=int, help='Run every N seconds')
def main(seconds):
    if not seconds:
        task.register_run(functools.partial(run, seconds=1))
        asyncio.run(task.start_once_immediately())
    else:
        patched_run = functools.partial(run, seconds=seconds)
        task.register_run(patched_run)
        asyncio.run(task.schedule_foreground())


if __name__ == '__main__':
    main()
