from nonebot import logger

from .database import CSqlManager


class CUserFishingStateDB(CSqlManager):
    @classmethod
    async def initDB(cls):
        fishingState = {
            "uid": "TEXT PRIMARY KEY",          # 用户Uid
            "lastFishTs": "INTEGER NOT NULL DEFAULT 0",  # 上次钓鱼时间戳
            "dailyDate": "TEXT NOT NULL DEFAULT ''",     # 当日日期 YYYY-MM-DD
            "dailyCount": "INTEGER NOT NULL DEFAULT 0",  # 当天已钓次数
        }

        await cls.ensureTableSchema("userFishingState", fishingState)

    @classmethod
    async def getStateByUid(cls, uid: str) -> dict:
        """根据用户uid获取钓鱼状态"""
        if not uid:
            return {}

        try:
            async with cls.m_pDB.execute(
                "SELECT * FROM userFishingState WHERE uid = ?",
                (uid,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else {}
        except Exception as e:
            logger.warning("getStateByUid 查询失败！", e=e)
            return {}

    @classmethod
    async def upsertStateByUid(
        cls,
        uid: str,
        lastFishTs: int,
        dailyDate: str,
        dailyCount: int,
    ) -> bool:
        """更新或插入用户钓鱼状态（事务版本）"""
        if not uid:
            return False

        try:
            async with cls._transaction():
                return await cls._upsertStateByUid(uid, lastFishTs, dailyDate, dailyCount)
        except Exception as e:
            logger.warning("upsertStateByUid 失败！", e=e)
            return False

    @classmethod
    async def _upsertStateByUid(
        cls,
        uid: str,
        lastFishTs: int,
        dailyDate: str,
        dailyCount: int,
    ) -> bool:
        """更新或插入用户钓鱼状态（非事务版本，供外层总事务调用）"""
        try:
            async with cls.m_pDB.execute(
                "SELECT 1 FROM userFishingState WHERE uid = ?",
                (uid,),
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                await cls.m_pDB.execute(
                    """
                    UPDATE userFishingState
                    SET lastFishTs = ?, dailyDate = ?, dailyCount = ?
                    WHERE uid = ?
                    """,
                    (lastFishTs, dailyDate, dailyCount, uid),
                )
            else:
                await cls.m_pDB.execute(
                    """
                    INSERT INTO userFishingState (uid, lastFishTs, dailyDate, dailyCount)
                    VALUES (?, ?, ?, ?)
                    """,
                    (uid, lastFishTs, dailyDate, dailyCount),
                )

            return True
        except Exception as e:
            logger.warning("_upsertStateByUid 失败！", e=e)
            return False

    @classmethod
    async def resetDailyCountByUid(cls, uid: str, dailyDate: str) -> bool:
        """重置指定用户的当日钓鱼计数"""
        if not uid:
            return False

        try:
            async with cls._transaction():
                state = await cls.getStateByUid(uid)

                if state:
                    await cls.m_pDB.execute(
                        """
                        UPDATE userFishingState
                        SET dailyDate = ?, dailyCount = 0
                        WHERE uid = ?
                        """,
                        (dailyDate, uid),
                    )
                else:
                    await cls.m_pDB.execute(
                        """
                        INSERT INTO userFishingState (uid, lastFishTs, dailyDate, dailyCount)
                        VALUES (?, 0, ?, 0)
                        """,
                        (uid, dailyDate),
                    )
            return True
        except Exception as e:
            logger.warning("resetDailyCountByUid 失败！", e=e)
            return False