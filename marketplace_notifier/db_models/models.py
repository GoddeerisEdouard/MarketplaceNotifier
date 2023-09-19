from enum import Enum

from tortoise import fields, Model


class Marketplace(str, Enum):
    TWEEDEHANDS = "TWEEDEHANDS"


class ListingInfo(Model):
    """
    minimal listing info stored to compare with other listings
    """
    id = fields.CharField(pk=True, max_length=11)
    title = fields.CharField(max_length=60)
    date = fields.DatetimeField()
    marketplace = fields.CharEnumField(Marketplace)
