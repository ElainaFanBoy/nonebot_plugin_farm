import calendar
import random
from datetime import timedelta

from nonebot import logger
from zhenxun_utils.image_utils import BuildImage

from ..config import g_bIsDebug
from ..dbService import g_pDBService
from ..json import g_pJsonManager
from ..tool import g_pToolManager
from .database import CSqlManager


class CUserSignDB(CSqlManager):
    @classmethod
    async def initDB(cls):
        # userSignLog 表结构，每条为一次签到事件
        userSignLog = {
            "uid": "TEXT NOT NULL",  # 用户ID
            "signDate": "DATE NOT NULL",  # 签到日期
            "isSupplement": "TINYINT NOT NULL DEFAULT 0",  # 是否补签
            "exp": "INT NOT NULL DEFAULT 0",  # 当天签到经验
            "point": "INT NOT NULL DEFAULT 0",  # 当天签到金币
            "createdAt": "DATETIME NOT NULL DEFAULT (datetime(CURRENT_TIMESTAMP, 'localtime'))",  # 创建时间  # noqa: E501
            "PRIMARY KEY": "(uid, signDate)",
        }

        # userSignSummary 表结构，每用户一行用于缓存签到状态
        userSignSummary = {
            "uid": "TEXT PRIMARY KEY NOT NULL",  # 用户ID
            "totalSignDays": "INT NOT NULL DEFAULT 0",  # 累计签到天数
            "currentMonth": "CHAR(7) NOT NULL DEFAULT ''",  # 当前月份（如2025-05）
            "monthSignDays": "INT NOT NULL DEFAULT 0",  # 本月签到次数
            "lastSignDate": "DATE DEFAULT NULL",  # 上次签到日期
            "continuousDays": "INT NOT NULL DEFAULT 0",  # 连续签到天数
            "supplementCount": "INT NOT NULL DEFAULT 0",  # 补签次数
            "updatedAt": "DATETIME NOT NULL DEFAULT (datetime(CURRENT_TIMESTAMP, 'localtime'))",  # 更新时间  # noqa: E501
        }

        await cls.ensureTableSchema("userSignLog", userSignLog)
        await cls.ensureTableSchema("userSignSummary", userSignSummary)

    @classmethod
    async def getUserSignRewardByDate(cls, uid: str, date: str) -> tuple[int, int]:
        """根据指定日期获取用户签到随机奖励

        Args:
            uid (str): 用户Uid
            date (str): 用户签到日期 示例：2025-05-27

        Returns:
            tuple[int, int]: 经验、金币
        """
        try:
            async with cls._transaction():
                async with cls.m_pDB.execute(
                    "SELECT exp, point FROM userSignLog WHERE uid=? AND signDate=?",
                    (uid, date),
                ) as cursor:
                    row = await cursor.fetchone()

                if row is None:
                    return 0, 0

                exp = row["exp"]
                point = row["point"]

                return exp, point
        except Exception as e:
            logger.warning("获取用户签到数据失败", e=e)
            return 0, 0

    @classmethod
    async def getUserSignCountByDate(cls, uid: str, monthStr: str) -> int:
        """根据日期查询用户签到总天数

        Args:
            uid (str): 用户Uid
            monthStr (str): 需要查询的日期 示例: 2025-05

        Returns:
            int: 查询月总签到天数
        """
        try:
            sql = "SELECT COUNT(*) FROM userSignLog WHERE uid=? AND signDate LIKE ?"
            param = f"{monthStr}-%"
            async with cls.m_pDB.execute(sql, (uid, param)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.warning("统计用户月签到次数失败", e=e)
            return 0

    @classmethod
    async def hasSigned(cls, uid: str, signDate: str) -> bool:
        """判断指定日期是否已签到

        Args:
            uid (int): 用户ID
            signDate (str): 日期字符串 'YYYY-MM-DD'

        Returns:
            bool: True=已签到，False=未签到
        """
        try:
            sql = "SELECT 1 FROM userSignLog WHERE uid=? AND signDate=? LIMIT 1"
            async with cls.m_pDB.execute(sql, (uid, signDate)) as cursor:
                row = await cursor.fetchone()
                return row is not None
        except Exception as e:
            logger.warning("查询是否已签到失败", e=e)
            return False

    @classmethod
    async def sign(cls, uid: str, signDate: str = "") -> int:
        """签到 (基础随机 + 累积膨胀随机)"""
        try:
            # --- 1. 初始化与校验 ---
            if not signDate:
                signDate = g_pToolManager.dateTime().date().today().strftime("%Y-%m-%d")

            if await cls.hasSigned(uid, signDate):
                return 2

            todayStr = g_pToolManager.dateTime().date().today().strftime("%Y-%m-%d")
            # 补签判定：如果不是今天，视为补签
            isSupplement = 0 if signDate == todayStr else 1

            # --- 2. 预读取数据以计算连续天数 ---
            # 我们需要先知道通过这次签到，连续天数会变成多少，从而计算奖励
            async with cls.m_pDB.execute(
                "SELECT * FROM userSignSummary WHERE uid=?", (uid,)
            ) as cursor:
                summary_row = await cursor.fetchone()

            # 计算本次签到后的连续天数 (current_continuous_days)
            current_continuous_days = 1
            if summary_row and not isSupplement:
                last_date = summary_row["lastSignDate"]
                # 计算昨天的日期
                prev_date = (
                    g_pToolManager.dateTime().strptime(signDate, "%Y-%m-%d")
                    - timedelta(days=1)
                ).strftime("%Y-%m-%d")
                
                # 如果上次签到是昨天，则连续天数+1
                if last_date == prev_date:
                    current_continuous_days = summary_row["continuousDays"] + 1

            # --- 3. 奖励计算逻辑 (核心修改) ---
            
            # A. 基础奖励 (固定随机范围)
            base_exp = random.randint(5, 50)
            base_point = random.randint(200, 2000)

            # B. 累积奖励 (范围随天数扩大)
            extra_exp = 0
            extra_point = 0

            if current_continuous_days > 1 and not isSupplement:
                # 设置上限，比如连续签到30天后，奖励范围不再扩大，防止数值崩坏
                days_factor = min(current_continuous_days, 30)

                # 算法设计：
                # 经验加成：下限 = (天数-1)*8, 上限 = (天数-1)*11
                # 第一天(无加成): 0
                # 第二天: 8 ~ 11 (范围差3)
                # 第三天: 16 ~ 22 (范围差6)
                # 第十天: 54 ~ 95 (范围差41)
                # 第30天: 174 ~ 319 (范围差145)
                extra_exp_min = (days_factor - 1) * 8
                extra_exp_max = (days_factor - 1) * 11
                extra_exp = random.randint(extra_exp_min, extra_exp_max)

                # 积分加成：同理放大
                extra_point_min = (days_factor - 1) * 500
                extra_point_max = (days_factor - 1) * 1000
                extra_point = random.randint(extra_point_min, extra_point_max)

            # C. 汇总最终奖励
            final_exp = base_exp + extra_exp
            final_point = base_point + extra_point

            # 如果是补签，通常奖励减半或者没有额外奖励，这里简单做个减半处理
            if isSupplement:
                final_exp = int(final_exp * 0.5)
                final_point = int(final_point * 0.5)

            # --- 4. 数据库写入 (事务) ---
            async with cls._transaction():
                # 写入日志 (存总数)
                await cls.m_pDB.execute(
                    "INSERT INTO userSignLog (uid, signDate, isSupplement, exp, point) VALUES (?, ?, ?, ?, ?)",
                    (uid, signDate, isSupplement, final_exp, final_point),
                )

                # 更新汇总表
                currentMonth = signDate[:7]
                if summary_row:
                    monthSignDays = (
                        summary_row["monthSignDays"] + 1
                        if summary_row["currentMonth"] == currentMonth
                        else 1
                    )
                    totalSignDays = summary_row["totalSignDays"] + 1
                    # 注意：supplementCount 逻辑保留原样
                    supplementCount = (
                        summary_row["supplementCount"] + 1
                        if isSupplement
                        else summary_row["supplementCount"]
                    )
                    
                    # 更新
                    await cls.m_pDB.execute(
                        """
                        UPDATE userSignSummary
                        SET totalSignDays=?, currentMonth=?, monthSignDays=?, 
                            lastSignDate=?, continuousDays=?, supplementCount=?
                        WHERE uid=?
                        """,
                        (
                            totalSignDays, currentMonth, monthSignDays,
                            signDate, current_continuous_days, supplementCount, uid
                        ),
                    )
                else:
                    # 插入新用户记录
                    await cls.m_pDB.execute(
                        """
                        INSERT INTO userSignSummary
                        (uid, totalSignDays, currentMonth, monthSignDays, lastSignDate, continuousDays, supplementCount)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            uid, 1, currentMonth, 1, signDate, 1, 
                            1 if isSupplement else 0
                        ),
                    )

                # 发放实际奖励
                currentExp = await g_pDBService.user.getUserExpByUid(uid)
                await g_pDBService.user.updateUserExpByUid(uid, currentExp + final_exp)

                currentPoint = await g_pDBService.user.getUserPointByUid(uid)
                await g_pDBService.user.updateUserPointByUid(uid, currentPoint + final_point)

            return 1
            
        except Exception as e:
            logger.warning("执行签到失败", e=e)
            return 0

    @classmethod
    async def drawSignCalendarImage(cls, uid: str, year: int, month: int):
        # 绘制签到图，自动提取数据库中该用户该月的签到天数
        cellSize = 80
        padding = 40
        titleHeight = 80
        cols = 7
        rows = 6
        width = cellSize * cols + padding * 2
        height = cellSize * rows + padding * 2 + titleHeight

        img = BuildImage(width, height, color=(255, 255, 255))
        await img.text((padding, 20), f"{year}年{month}月签到表", font_size=36)

        firstWeekday, totalDays = calendar.monthrange(year, month)
        monthStr = f"{year:04d}-{month:02d}"
        try:
            sql = "SELECT signDate FROM userSignLog WHERE uid=? AND signDate LIKE ?"
            async with cls.m_pDB.execute(sql, (uid, f"{monthStr}-%")) as cursor:
                rows = await cursor.fetchall()
                signedDays = {int(r[0][-2:]) for r in rows if r[0][-2:].isdigit()}
        except Exception as e:
            logger.warning("绘制签到图时数据库查询失败", e=e)
            signedDays = set()

        for day in range(1, totalDays + 1):
            index = day + firstWeekday - 1
            row = index // cols
            col = index % cols
            x1 = padding + col * cellSize
            y1 = padding + titleHeight + row * cellSize
            x2 = x1 + cellSize - 10
            y2 = y1 + cellSize - 10
            color = (112, 196, 112) if day in signedDays else (220, 220, 220)
            await img.rectangle((x1, y1, x2, y2), fill=color, outline="black", width=2)
            await img.text((x1 + 10, y1 + 10), str(day), font_size=24)

        return img
