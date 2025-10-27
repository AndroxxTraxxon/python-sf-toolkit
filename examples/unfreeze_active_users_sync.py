import logging

from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.data import select
from sf_toolkit.data.fields import IdField, CheckboxField

from sf_toolkit.io import api

LOGGER = logging.getLogger()
logging.basicConfig(level=logging.INFO)


class User(SObject):
    Id = IdField()


class UserLogin(SObject):
    Id = IdField()
    IsFrozen = CheckboxField()


def unfreeze_active_users():
    users_to_unfreeze = (
        select(UserLogin)
        .where(IsFrozen=True)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
        .execute_bulk()
    )

    for user in users_to_unfreeze:
        user.IsFrozen = False

    users_list = users_to_unfreeze.as_list()
    LOGGER.info("Unfreezing %d users", len(users_list))

    bulk_job = api.save_update_bulk(users_to_unfreeze.as_list(), timeout=60)
    if not bulk_job:
        LOGGER.error("No data to process in bulk job")
        return
    bulk_job.monitor_until_complete()

    LOGGER.info("Bulk load finished %s", bulk_job.state)
    if bulk_job.state == "Failed":
        LOGGER.error("Bulk job failed with error: %s", bulk_job.errorMessage)


def main():
    with SalesforceClient(login=cli_login("heb--performtst")):
        unfreeze_active_users()


if __name__ == "__main__":
    main()
