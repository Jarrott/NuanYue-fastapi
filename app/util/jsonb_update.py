from sqlalchemy import func, update, cast, text
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal


class JsonbManager:
    @staticmethod
    def _normalize(value):
        if isinstance(value, Decimal):
            return float(value)
        return value

    @staticmethod
    def _path(key: str):
        return array(key.split("."))

    @classmethod
    async def set(cls, session: AsyncSession, model, pk: int, key: str, value):
        stmt = (
            update(model)
            .where(model.id == pk)
            .values(
                extra=func.jsonb_set(
                    func.coalesce(model.extra, cast({}, JSONB)),
                    cls._path(key),
                    cast(cls._normalize(value), JSONB),
                    True
                )
            )
        )
        await session.execute(stmt)

    @classmethod
    async def inc(cls, session: AsyncSession, model, pk: int, key: str, amount):
        amount = cls._normalize(amount)

        stmt = (
            update(model)
            .where(model.id == pk)
            .values(
                extra=func.jsonb_set(
                    func.coalesce(model.extra, cast({}, JSONB)),
                    cls._path(key),
                    cast(
                        func.coalesce(
                            cast(func.jsonb_extract_path_text(model.extra, *key.split(".")), JSONB).astext.cast(Float),
                            0
                        ) + amount,
                        JSONB
                    ),
                    True
                )
            )
        )
        await session.execute(stmt)

    @classmethod
    async def remove(cls, session: AsyncSession, model, pk: int, key: str):
        stmt = (
            update(model)
            .where(model.id == pk)
            .values(
                extra=model.extra.op("#-")(cls._path(key))
            )
        )
        await session.execute(stmt)

    @classmethod
    async def append(cls, session: AsyncSession, model, pk: int, key: str, value):
        stmt = (
            update(model)
            .where(model.id == pk)
            .values(
                extra=func.jsonb_set(
                    func.coalesce(model.extra, cast({}, JSONB)),
                    cls._path(key),
                    func.jsonb_build_array(
                        *[model.extra[key], cls._normalize(value)]
                    ),
                    True
                )
            )
        )
        await session.execute(stmt)

    @staticmethod
    async def set_path(session, model, pk: int, path: str, value: any):
        keys = path.split(".")  # e.g. ['sensitive','login_devices']
        pg_path = "{" + ",".join(keys) + "}"

        await session.execute(
            text(f"""
                UPDATE "{model.__tablename__}"
                SET extra = jsonb_set(
                    COALESCE(extra, '{{}}'::jsonb),
                    :pg_path,
                    to_jsonb(:value),
                    true
                )
                WHERE id = :id
            """),
            {"id": pk, "pg_path": pg_path, "value": value}
        )