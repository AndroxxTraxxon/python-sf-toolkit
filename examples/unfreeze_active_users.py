import asyncio
from gc import freeze
import logging

from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.data import select
from sf_toolkit.data.fields import IdField, CheckboxField

from sf_toolkit.interfaces import OrgType
from sf_toolkit.io.api import save_list, save_update_bulk

LOGGER = logging.getLogger()
logging.basicConfig(level=logging.INFO)


class UserLogin(SObject):
    Id = IdField()
    IsFrozen = CheckboxField()


async def unfreeze_active_users(conn: SalesforceClient):
    frozen_users = (
        select(UserLogin)
        .where(IsFrozen=True)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
        .count()
    )
    if not frozen_users and conn.org_type != OrgType.PRODUCTION:
        LOGGER.info("Pulling 5 users to freeze for testing")
        freeze_query = (
            select(UserLogin)
            .where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
            .and_where(UserId__ne=conn._userinfo.user_id)
            .limit(5)
        )
        LOGGER.info(freeze_query)
        users_to_freeze = freeze_query.execute(timeout=900)
        LOGGER.info("Got %d users to freeze", len(users_to_freeze))
        async for user in users_to_freeze:
            user.IsFrozen = True
        save_list(users_to_freeze.as_list(), timeout=60)

    users_to_unfreeze = (
        select(UserLogin)
        .where(IsFrozen=True)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
        .execute(timeout=900)
    )
    LOGGER.info("Pulling %d users to unfreeze", len(users_to_unfreeze))

    async for user in users_to_unfreeze:
        user.IsFrozen = False

    LOGGER.info("Unfreezing %d users", len(users_to_unfreeze))

    bulk_job = save_update_bulk(users_to_unfreeze.as_list(), timeout=60)
    if not bulk_job:
        LOGGER.error("No data to process in bulk job")
        return

    while bulk_job.state not in ("Aborted", "JobComplete", "Failed"):
        LOGGER.info("Bulk job state: %s", bulk_job.state)
        await asyncio.sleep(5)
        bulk_job = bulk_job.refresh()

    LOGGER.info("Bulk load finished %s", bulk_job.state)
    if bulk_job.state == "Failed":
        LOGGER.error("Bulk job failed with error: %s", bulk_job.errorMessage)


def main():
    with SalesforceClient(login=cli_login("test-x3vxvh4zznqi@example.com")) as conn:
        asyncio.run(unfreeze_active_users(conn))


if __name__ == "__main__":
    main()
