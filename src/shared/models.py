import re

from tortoise import fields, Model
from tortoise.validators import RegexValidator


class QueryInfo(Model):
    """
    query info to be monitored
    """
    id = fields.IntField(pk=True) # so it can be easily removed
    browser_url = fields.CharField(
        unique=True,
        max_length=500,
        # update this! regex should be way broader
        validators=[RegexValidator(
            r'^https:\/\/www\.2dehands\.be\/(?:q|l)\/[^?]*$',
            re.M)],
        description="browser URL for user to see the listings on the website"
    )
    request_url = fields.CharField(
        unique=True,
        max_length=500,
        # update this! regex should be way broader
        validators=[RegexValidator(
            r'^https://www\.2dehands\.be/lrp/api/search\?.*',
            re.M)],
        description="url to use for GET request"
    )
    query = fields.CharField(max_length=60, null=True)
    next_check_time = fields.DatetimeField(null=True, description="When this query will be checked next")
    is_healthy = fields.BooleanField(default=True)
