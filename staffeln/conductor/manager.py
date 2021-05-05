import cotyledon
import datetime
from futurist import periodics
from oslo_log import log
import staffeln.conf
import threading
import time

from staffeln.common import constants
from staffeln.conductor import backup
from staffeln.common import context
from staffeln.common import time as xtime
from staffeln.i18n import _

LOG = log.getLogger(__name__)
CONF = staffeln.conf.CONF


class BackupManager(cotyledon.Service):
    name = "Staffeln conductor backup controller"

    def __init__(self, worker_id, conf):
        super(BackupManager, self).__init__(worker_id)
        self._shutdown = threading.Event()
        self.conf = conf
        self.ctx = context.make_context()
        LOG.info("%s init" % self.name)

    def run(self):
        LOG.info("%s run" % self.name)
        periodic_callables = [
            (self.backup_engine, (), {}),
        ]
        periodic_worker = periodics.PeriodicWorker(periodic_callables, schedule_strategy="last_finished")
        periodic_thread = threading.Thread(target=periodic_worker.start)
        periodic_thread.daemon = True
        periodic_thread.start()

    def terminate(self):
        LOG.info("%s terminate" % self.name)
        super(BackupManager, self).terminate()

    def reload(self):
        LOG.info("%s reload" % self.name)

    # Check if the backup count is over the limit
    # TODO(Alex): how to count the backup number
    #  only available backups are calculated?
    def _over_limitation(self):
        LOG.info(_("Checking the backup limitation..."))
        max_count = CONF.conductor.max_backup_count
        current_count = len(backup.Backup().get_backups())
        if max_count <= current_count:
            # TODO(Alex): Send notification
            LOG.info(_("The backup limit is over."))
            return True
        LOG.info(_("The max limit is %s, and current backup count is %s" % (max_count, current_count)))
        return False

    # Manage active backup generators
    def _process_wip_tasks(self):
        LOG.info(_("Processing WIP backup generators..."))
        queues_started = backup.Backup().get_queues(
            filters={"backup_status": constants.BACKUP_WIP}
        )
        if len(queues_started) != 0:
            for queue in queues_started: backup.Backup().check_volume_backup_status(queue)

    # Create backup generators
    def _process_new_tasks(self):
        LOG.info(_("Creating new backup generators..."))
        queues_to_start = backup.Backup().get_queues(
            filters={"backup_status": constants.BACKUP_PLANNED}
        )
        if len(queues_to_start) != 0:
            for queue in queues_to_start:
                backup.Backup().volume_backup_initiate(queue)

    # Refresh the task queue
    # TODO(Alex): need to escalate discussion
    #  how to manage last backups not finished yet
    def _update_task_queue(self):
        LOG.info(_("Updating backup task queue..."))
        all_tasks = backup.Backup().get_queues()
        if len(all_tasks) == 0:
            backup.Backup().create_queue()
        else:
            LOG.info(_("The last backup cycle is not finished yet."
                       "So the new backup cycle is skipped."))

    @periodics.periodic(spacing=CONF.conductor.backup_service_period, run_immediately=True)
    def backup_engine(self):
        LOG.info("backing... %s" % str(time.time()))
        LOG.info("%s periodics" % self.name)

        if self._over_limitation(): return
        self._update_task_queue()
        self._process_wip_tasks()
        self._process_new_tasks()


class RotationManager(cotyledon.Service):
    name = "Staffeln conductor rotation controller"

    def __init__(self, worker_id, conf):
        super(RotationManager, self).__init__(worker_id)
        self._shutdown = threading.Event()
        self.conf = conf
        LOG.info("%s init" % self.name)

    def run(self):
        LOG.info("%s run" % self.name)

        periodic_callables = [
            (self.rotation_engine, (), {}),
        ]
        periodic_worker = periodics.PeriodicWorker(periodic_callables, schedule_strategy="last_finished")
        periodic_thread = threading.Thread(target=periodic_worker.start)
        periodic_thread.daemon = True
        periodic_thread.start()

    def terminate(self):
        LOG.info("%s terminate" % self.name)
        super(RotationManager, self).terminate()

    def reload(self):
        LOG.info("%s reload" % self.name)

    @periodics.periodic(spacing=CONF.conductor.retention_service_period, run_immediately=True)
    def rotation_engine(self):
        LOG.info("%s rotation_engine" % self.name)
        # TODO(Alex): No limitation for retention?
        #  Even though, the backup count is over the limit, the retention service will
        #  continue working?
        #     filter based on backup status
        #     filter based on backup creation time
        # 2. delete the backups


        # 1. get the list of backups to remove based on the retention time
        threshold_strtime = self.get_threshold_strtime()
        if threshold_strtime == None: return
        backups = backup.Backup().get_backups(filters={"created_at__lt", threshold_strtime})

        # 2. remove the backups
        for retention_backup in backups:
            # 1. check the backup status and delete only available backups
            if not backup.Backup().check_backup_status(retention_backup): continue
            # 2. remove backup

            pass

    # get the threshold time str
    def get_threshold_strtime(self):
        time_delta_dict = xtime.parse_timedelta_string(CONF.conductor.retention_time)
        if time_delta_dict == None: return None

        res = xtime.timeago(
            years= time_delta_dict["years"],
            months= time_delta_dict["months"],
            weeks= time_delta_dict["weeks"],
            days= time_delta_dict["days"],
        )
        if res == None: LOG.info(_("Retention time format is invalid. "
                                   "Follow <YEARS>y<MONTHS>m<WEEKS>w<DAYS>d."))

        return datetime.datetime.strptime(res, constants.DEFAULT_TIME_FORMAT)

