import asyncio
from gc import freeze
import logging

from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.client import OrgType
from sf_toolkit.data import select
from sf_toolkit.data.fields import IdField, CheckboxField

from sf_toolkit.io.api import save_list, save_update_bulk


LOGGER = logging.getLogger()
logging.basicConfig(level=logging.INFO)


class UserLogin(SObject):
    Id = IdField()
    IsFrozen = CheckboxField()


async def freeze_users(conn: SalesforceClient):
    freeze_query = (
        select(UserLogin)
        .where(IsFrozen=False)
        .and_where(UserId__ne=conn._userinfo.user_id)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive = TRUE")
        .limit(50)
    )
    LOGGER.info(freeze_query)
    users_to_freeze = freeze_query.execute(timeout=900)
    LOGGER.info("Got %d users to freeze", len(users_to_freeze))
    async for user in users_to_freeze:
        user.IsFrozen = True
    results = save_list(users_to_freeze.as_list(), timeout=60)
    LOGGER.info("Frozen %d users", sum(1 for result in results if result.success))

    frozen_user_count = (
        select(UserLogin)
        .where(IsFrozen=True)
        .and_where(UserId__in="SELECT Id FROM User WHERE IsActive=TRUE")
        .count(timeout=900)
    )
    LOGGER.info("Total frozen users: %d", frozen_user_count)


def main():
    with SalesforceClient(login=cli_login("heb--performtst")) as conn:
        assert conn.org_type != OrgType.PRODUCTION, (
            "This script should not be run against production orgs."
        )
        asyncio.run(freeze_users(conn))


if __name__ == "__main__":
    main()
