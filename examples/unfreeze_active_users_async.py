import asyncio
import logging

from sf_toolkit import SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.client import AsyncSalesforceClient, OrgType
from sf_toolkit.data import select
from sf_toolkit.data.fields import IdField, CheckboxField

from sf_toolkit.io import api

LOGGER = logging.getLogger()
logging.basicConfig(level=logging.INFO)


class UserLogin(SObject):
    Id = IdField()
    IsFrozen = CheckboxField()


async def unfreeze_active_users(conn: AsyncSalesforceClient):
    frozen_users = await (
        select(UserLogin)
        .where(IsFrozen=True)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
        .count_async()
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
        users_to_freeze = await freeze_query.execute_async(timeout=900)
        LOGGER.info("Got %d users to freeze", len(users_to_freeze))
        async for user in users_to_freeze:
            user.IsFrozen = True
        _ = await api.save_update_list_async(
            await users_to_freeze.as_list_async(), timeout=60
        )

    users_to_unfreeze = await (
        select(UserLogin)
        .where(IsFrozen=True)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
        .execute_bulk_async()
    )
    LOGGER.info(
        "Pulling %d users to unfreeze", len(await users_to_unfreeze.as_list_async())
    )

    async for user in users_to_unfreeze:
        user.IsFrozen = False

    LOGGER.info("Unfreezing %d users", len(await users_to_unfreeze.as_list_async()))

    bulk_job = await api.save_update_bulk_async(
        await users_to_unfreeze.as_list_async(), timeout=60
    )
    if not bulk_job:
        LOGGER.error("No data to process in bulk job")
        return

    while bulk_job.state not in ("Aborted", "JobComplete", "Failed"):
        LOGGER.info("Bulk job state: %s", bulk_job.state)
        await asyncio.sleep(5)
        bulk_job = await bulk_job.refresh_async()

    LOGGER.info("Bulk load finished %s", bulk_job.state)
    if bulk_job.state == "Failed":
        LOGGER.error("Bulk job failed with error: %s", bulk_job.errorMessage)


async def main():
    async with AsyncSalesforceClient(login=cli_login("heb--performtst")) as conn:
        await unfreeze_active_users(conn)


if __name__ == "__main__":
    asyncio.run(main())
