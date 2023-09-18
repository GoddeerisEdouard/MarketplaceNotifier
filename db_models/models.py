from tortoise import fields, Model


class Test(Model):
    id = fields.IntField(pk=True)
