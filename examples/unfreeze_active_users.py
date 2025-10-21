import asyncio
from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.data.fields import IdField, CheckboxField
import logging

LOGGER = logging.getLogger()
logging.basicConfig(level=logging.INFO)


class UserLogin(SObject):
    Id = IdField()
    IsFrozen = CheckboxField()


async def unfreeze_active_users():
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

    users_to_unfreeze.as_list().save_update(timeout=60)


with SalesforceClient(login=cli_login("uatlite")) as client:
    asyncio.run(unfreeze_active_users())
