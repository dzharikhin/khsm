# coding=utf-8

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from tzlocal import get_localzone

import loggers
import service

logger = loggers.logging.getLogger(__name__)


def task():
    service.init()
    service.reset_data()


if __name__ == "__main__":
    sched = BlockingScheduler(timezone=get_localzone())
    sched.add_job(task, CronTrigger.from_crontab('*/30 * * * *'))
    sched.start()

