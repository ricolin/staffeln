from openstack import exceptions
from openstack import proxy
from staffeln.common import auth
from staffeln import conf

import tenacity

CONF = conf.CONF

class OpenstackSDK():

    def __init__(self):
        self.conn_list = {}
        self.conn = auth.create_connection()


    def set_project(self, project):
        project_id = project.get('id')

        if project_id in self.conn_list:
            self.conn = self.conn_list[project_id]
        else:
            conn = self.conn.connect_as_project(project)
            self.conn = conn

    # user
    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(exceptions.HttpException),
        wait=tenacity.wait_exponential(max=180),
        stop=tenacity.stop_after_delay(CONF.conductor.retry_timeout))
    def get_user_id(self):
        user_name = self.conn.config.auth["username"]
        if "user_domain_id" in self.conn.config.auth:
            domain_id = self.conn.config.auth["user_domain_id"]
            user = self.conn.get_user(name_or_id=user_name, domain_id=domain_id)
        elif "user_domain_name" in self.conn.config.auth:
            domain_name = self.conn.config.auth["user_domain_name"]
            user = self.conn.get_user(name_or_id=user_name, domain_id=domain_name)
        else:
            user = self.conn.get_user(name_or_id=user_name)
        return user.id

    ############## project
    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(exceptions.HttpException),
        wait=tenacity.wait_exponential(max=180),
        stop=tenacity.stop_after_delay(CONF.conductor.retry_timeout))
    def get_projects(self):
        return self.conn.list_projects()


    ############## server
    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(exceptions.HttpException),
        wait=tenacity.wait_exponential(max=180),
        stop=tenacity.stop_after_delay(CONF.conductor.retry_timeout))
    def get_servers(self, project_id, all_projects=True, details=True):
        return self.conn.compute.servers(
            details=details, all_projects=all_projects, project_id=project_id
        )


    ############## volume
    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(exceptions.HttpException),
        wait=tenacity.wait_exponential(max=180),
        stop=tenacity.stop_after_delay(CONF.conductor.retry_timeout))
    def get_volume(self, uuid, project_id):
        return self.conn.get_volume_by_id(uuid)


    ############## backup
    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(exceptions.HttpException),
        wait=tenacity.wait_exponential(max=180),
        stop=tenacity.stop_after_delay(CONF.conductor.retry_timeout))
    def get_backup(self, uuid, project_id=None):
        # return conn.block_storage.get_backup(
        #     project_id=project_id, backup_id=uuid,
        # )
        # conn.block_storage.backups(volume_id=uuid,project_id=project_id)
        return self.conn.get_volume_backup(uuid)


    def create_backup(self, volume_id, project_id, force=True, wait=False):
        # return conn.block_storage.create_backup(
        #     volume_id=queue.volume_id, force=True, project_id=queue.project_id,
        # )
        return self.conn.create_volume_backup(
            volume_id=volume_id, force=force, wait=wait,
        )


    def delete_backup(self, uuid, project_id=None, force=True):
        # Note(Alex): v3 is not supporting force delete?
        # conn.block_storage.delete_backup(
        #     project_id=project_id, backup_id=uuid,
        # )
        try:
            self.conn.delete_volume_backup(uuid, force=force)
            # TODO(Alex): After delete the backup generator, need to set the volume status again
        except exceptions.ResourceNotFound:
            return


    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(exceptions.HttpException),
        wait=tenacity.wait_exponential(max=180),
        stop=tenacity.stop_after_delay(CONF.conductor.retry_timeout))
    def get_backup_quota(self, project_id):
        # quota = conn.get_volume_quotas(project_id)
        quota = self._get_volume_quotas(project_id)
        return quota.backups


    # rewrite openstasdk._block_storage.get_volume_quotas
    # added usage flag
    # ref: https://docs.openstack.org/api-ref/block-storage/v3/?expanded=#show-quota-usage-for-a-project
    def _get_volume_quotas(self, project_id, usage=True):
        """ Get volume quotas for a project

        :param name_or_id: project name or id
        :raises: OpenStackCloudException if it's not a valid project

        :returns: Munch object with the quotas
        """

        if usage:
            resp = self.conn.block_storage.get(
                '/os-quota-sets/{project_id}?usage=True'.format(project_id=project_id))
        else:
            resp = self.conn.block_storage.get(
                '/os-quota-sets/{project_id}'.format(project_id=project_id))
        data = proxy._json_response(
            resp,
            error_message="cinder client call failed")
        return self.conn._get_and_munchify('quota_set', data)

