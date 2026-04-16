import random
import time

from nonebot import logger
from zhenxun_utils.image_utils import ImageTemplate

from ..config import g_sTranslation
from ..dbService import g_pDBService
from ..json import g_pJsonManager
from ..tool import g_pToolManager


class CFishingManager:
    @classmethod
    def _t(cls, group: str, key: str, default: str) -> str:
        """读取翻译文本，若 config.py 里尚未配置则使用默认值"""
        return g_sTranslation.get(group, {}).get(key, default)

    @classmethod
    def _bait_item_key(cls, bait_name: str) -> str:
        return f"bait:{bait_name}"

    @classmethod
    def _fish_item_key(cls, fish_name: str) -> str:
        return f"fish:{fish_name}"

    @classmethod
    def _get_bait_map(cls) -> dict:
        return g_pJsonManager.m_pBait.get("bait", {})

    @classmethod
    def _get_fish_map(cls) -> dict:
        return g_pJsonManager.m_pFish.get("fish", {})

    @classmethod
    def _get_pool_map(cls) -> dict:
        return g_pJsonManager.m_pFishPool.get("pool", {})

    @classmethod
    def _get_system_map(cls) -> dict:
        return g_pJsonManager.m_pFishingSystem.get("system", {})

    @classmethod
    async def resolve_bait(cls, uid: str, bait_name: str = "") -> dict | None:
        """
        解析本次钓鱼要使用的鱼饵

        返回:
            {
                "name": 鱼饵名,
                "info": 鱼饵配置,
                "count": 当前库存,
                "itemKey": 背包键名
            }
        """
        bait_map = cls._get_bait_map()
        if not bait_map:
            logger.warning("resolve_bait 失败：bait.json 未正确加载")
            return None

        inventory = await g_pDBService.userItem.getUserItemByUid(uid)
        if not inventory:
            return None

        # 指定鱼饵：优先用指定鱼饵
        if isinstance(bait_name, str) and bait_name.strip():
            bait_name = bait_name.strip()
            bait_info = bait_map.get(bait_name)
            if not bait_info:
                return None

            item_key = cls._bait_item_key(bait_name)
            count = inventory.get(item_key, 0)
            if count <= 0:
                return None

            return {
                "name": bait_name,
                "info": bait_info,
                "count": count,
                "itemKey": item_key,
            }

        # 未指定鱼饵：按系统配置默认使用最低/最高级可用鱼饵
        usable_baits: list[dict] = []
        for name, info in bait_map.items():
            item_key = cls._bait_item_key(name)
            count = inventory.get(item_key, 0)
            if count > 0:
                usable_baits.append(
                    {
                        "name": name,
                        "info": info,
                        "count": count,
                        "itemKey": item_key,
                    }
                )

        if not usable_baits:
            return None

        strategy = cls._get_system_map().get("defaultUseStrategy", "lowest_level")

        if strategy == "highest_level":
            usable_baits.sort(
                key=lambda x: (
                    int(x["info"].get("baitLevel", 0)),
                    int(x["info"].get("unlockLevel", 0)),
                ),
                reverse=True,
            )
        else:
            usable_baits.sort(
                key=lambda x: (
                    int(x["info"].get("baitLevel", 0)),
                    int(x["info"].get("unlockLevel", 0)),
                )
            )

        return usable_baits[0]

    @classmethod
    async def fish(cls, uid: str, bait_name: str = "") -> str:
        """
        执行一次钓鱼
        流程：
        1. 解析鱼饵
        2. 检查CD和每日次数
        3. 扣鱼饵
        4. 判定逃跑
        5. 按权重抽鱼
        6. 增加经验、放入背包、更新状态
        """
        bait_map = cls._get_bait_map()
        fish_map = cls._get_fish_map()
        pool_map = cls._get_pool_map()
        system_map = cls._get_system_map()

        if not bait_map or not fish_map or not pool_map or not system_map:
            logger.warning("fish 失败：钓鱼配置未正确加载")
            return cls._t("fishing", "configError", "❌ 钓鱼配置加载失败，请联系管理员")

        bait_data = await cls.resolve_bait(uid, bait_name)
        if not bait_data:
            return cls._t("fishing", "noBait", "🪱 你没有可用的鱼饵，先去物品商店看看吧")

        use_bait_name = bait_data["name"]
        bait_info = bait_data["info"]
        bait_item_key = bait_data["itemKey"]

        # 用户等级
        level_info = await g_pDBService.user.getUserLevelByUid(uid)
        user_level = level_info[0] if isinstance(level_info, tuple) and len(level_info) >= 1 else 0
        if user_level < 0:
            user_level = 0

        # 每日次数 + CD 检查
        state = await g_pDBService.userFishingState.getStateByUid(uid)
        now_dt = g_pToolManager.dateTime()
        today_str = now_dt.strftime("%Y-%m-%d")
        now_ts = int(time.time())

        cooldown_seconds = int(system_map.get("cooldownSeconds", 20))
        daily_limit = int(system_map.get("dailyLimit", 10))

        last_fish_ts = int(state.get("lastFishTs", 0)) if state else 0
        daily_date = str(state.get("dailyDate", "")) if state else ""
        daily_count = int(state.get("dailyCount", 0)) if state else 0

        if daily_date != today_str:
            daily_date = today_str
            daily_count = 0

        remain_cd = cooldown_seconds - (now_ts - last_fish_ts)
        if remain_cd > 0:
            return cls._t("fishing", "cooldown", "⏳ 钓鱼太频繁了，请 {sec} 秒后再试").format(
                sec=remain_cd
            )

        if daily_count >= daily_limit:
            return cls._t("fishing", "dailyLimit", "📅 你今天的钓鱼次数已经用完啦，明天再来吧")

        # 再次确认背包里鱼饵数量足够
        current_bait_count = await g_pDBService.userItem.getUserItemByName(uid, bait_item_key)
        if current_bait_count is None or current_bait_count <= 0:
            return cls._t("fishing", "noBait", "🪱 你没有可用的鱼饵，先去物品商店看看吧")

        # 构造鱼池
        raw_pool = pool_map.get(use_bait_name, [])
        if not raw_pool:
            logger.warning(f"fish 失败：鱼池 {use_bait_name} 不存在或为空")
            return cls._t("fishing", "emptyPool", "❌ 当前鱼池为空，请联系管理员检查配置")

        available_pool: list[dict] = []
        for entry in raw_pool:
            fish_name = entry.get("fish", "")
            fish_info = fish_map.get(fish_name)
            if not fish_info:
                logger.warning(f"fish_pool.json 中的鱼 {fish_name} 未在 fish.json 中定义")
                continue

            # 第一版：按 fish.level * 20 设置最低等级门槛
            required_level = int(fish_info.get("level", 0)) * 20
            if user_level < required_level:
                continue

            weight = int(entry.get("weight", 0))
            if weight <= 0:
                continue

            available_pool.append(entry)

        if not available_pool:
            return cls._t("fishing", "noAvailableFish", "🎣 当前鱼饵暂无可钓鱼种，请提升等级后再来试试")

        # 先扣鱼饵
        if not await g_pDBService.userItem.addUserItemByUid(uid, bait_item_key, -1):
            return cls._t("fishing", "consumeError", "❌ 扣除鱼饵失败，请稍后重试")

        # 逃跑判定
        escape_rate = float(bait_info.get("escapeRate", system_map.get("defaultEscapeRate", 0.2)))
        if random.random() < escape_rate:
            ok = await g_pDBService.userFishingState.upsertStateByUid(
                uid=uid,
                lastFishTs=now_ts,
                dailyDate=today_str,
                dailyCount=daily_count + 1,
            )
            if not ok:
                logger.warning(f"用户 {uid} 钓鱼逃跑后更新状态失败")

            return cls._t(
                "fishing",
                "escape",
                "🐟 你使用了{name}，静静等待了一会儿……可惜鱼逃走了",
            ).format(name=use_bait_name)

        # 按权重抽鱼
        population = [x["fish"] for x in available_pool]
        weights = [int(x["weight"]) for x in available_pool]
        result_fish_name = random.choices(population=population, weights=weights, k=1)[0]

        result_fish_info = fish_map.get(result_fish_name)
        if not result_fish_info:
            logger.warning(f"fish 抽中鱼 {result_fish_name} 但 fish.json 中不存在")
            return cls._t("fishing", "drawError", "❌ 抽鱼失败，请联系管理员检查配置")

        exp_gain = int(result_fish_info.get("exp", 0))
        current_exp = await g_pDBService.user.getUserExpByUid(uid)
        if current_exp < 0:
            current_exp = 0

        # 加经验
        if not await g_pDBService.user.updateUserExpByUid(uid, current_exp + exp_gain):
            logger.warning(f"用户 {uid} 增加钓鱼经验失败")

        # 鱼放入背包
        fish_item_key = cls._fish_item_key(result_fish_name)
        if not await g_pDBService.userItem.addUserItemByUid(uid, fish_item_key, 1):
            logger.warning(f"用户 {uid} 钓鱼入库失败：{result_fish_name}")

        # 更新状态
        if not await g_pDBService.userFishingState.upsertStateByUid(
            uid=uid,
            lastFishTs=now_ts,
            dailyDate=today_str,
            dailyCount=daily_count + 1,
        ):
            logger.warning(f"用户 {uid} 钓鱼后更新状态失败")

        if result_fish_info.get("isKing", False):
            return cls._t(
                "fishing",
                "successKing",
                "👑 你使用了{name}，水面忽然泛起异光！\n竟然钓到了一条【{fish}】！\n✨ 经验 +{exp}",
            ).format(name=use_bait_name, fish=result_fish_name, exp=exp_gain)

        return cls._t(
            "fishing",
            "success",
            "🐟 你使用了{name}，静静等待后……\n哇！你钓到了一条【{fish}】！\n✨ 经验 +{exp}",
        ).format(name=use_bait_name, fish=result_fish_name, exp=exp_gain)

    @classmethod
    async def getUserBaitByUid(cls, uid: str) -> bytes:
        """获取用户鱼饵仓库（图片）"""
        data_list = []
        column_name = ["-", "鱼饵名称", "数量", "单价", "点券", "解锁等级", "鱼饵等级"]

        inventory = await g_pDBService.userItem.getUserItemByUid(uid)
        bait_map = cls._get_bait_map()

        if not inventory or not bait_map:
            result = await ImageTemplate.table_page(
                "鱼饵仓库",
                "购买示例：@IRONY 购买物品 普通鱼饵 [数量]",
                column_name,
                data_list,
            )
            return result.pic2bytes()

        rows: list[list] = []
        for item_key, count in inventory.items():
            if not item_key.startswith("bait:"):
                continue

            bait_name = item_key[5:]
            bait_info = bait_map.get(bait_name)
            if not bait_info:
                continue

            rows.append(
                [
                    "",
                    bait_name,
                    count,
                    int(bait_info.get("point", 0)),
                    int(bait_info.get("vipPoint", 0)),
                    int(bait_info.get("unlockLevel", 0)),
                    int(bait_info.get("baitLevel", 0)),
                ]
            )

        rows.sort(key=lambda x: (x[6], x[5], x[1]))

        result = await ImageTemplate.table_page(
            "鱼饵仓库",
            "购买示例：@IRONY 购买物品 普通鱼饵 [数量]",
            column_name,
            rows,
        )
        return result.pic2bytes()

    @classmethod
    async def getUserFishByUid(cls, uid: str) -> bytes:
        """获取用户鱼获仓库（图片）"""
        data_list = []
        column_name = ["-", "鱼名称", "数量", "等级", "单价", "经验", "鱼王"]

        inventory = await g_pDBService.userItem.getUserItemByUid(uid)
        fish_map = cls._get_fish_map()

        if not inventory or not fish_map:
            result = await ImageTemplate.table_page(
                "鱼获仓库",
                "出售示例：@IRONY 出售鱼产 河豚 [数量]",
                column_name,
                data_list,
            )
            return result.pic2bytes()

        rows: list[list] = []
        for item_key, count in inventory.items():
            if not item_key.startswith("fish:"):
                continue

            fish_name = item_key[5:]
            fish_info = fish_map.get(fish_name)
            if not fish_info:
                continue

            rows.append(
                [
                    "",
                    fish_name,
                    count,
                    int(fish_info.get("level", 0)),
                    int(fish_info.get("sellPoint", 0)),
                    int(fish_info.get("exp", 0)),
                    "是" if fish_info.get("isKing", False) else "否",
                ]
            )

        rows.sort(key=lambda x: (-x[3], -x[4], x[1]))

        result = await ImageTemplate.table_page(
            "鱼获仓库",
            "出售示例：@IRONY 出售鱼产 河豚 [数量]",
            column_name,
            rows,
        )
        return result.pic2bytes()

    @classmethod
    async def sellFishByUid(cls, uid: str, name: str = "", num: int = 1) -> str:
        """出售鱼获，逻辑风格对齐 sellPlantByUid"""
        fish_map = cls._get_fish_map()
        inventory = await g_pDBService.userItem.getUserItemByUid(uid)

        if not fish_map:
            return cls._t("sellFish", "configError", "❌ 鱼类配置加载失败，请联系管理员")

        user_fish: dict[str, int] = {}
        if inventory:
            for item_key, count in inventory.items():
                if item_key.startswith("fish:"):
                    fish_name = item_key[5:]
                    user_fish[fish_name] = count

        if not user_fish:
            return cls._t("sellFish", "no", "🤷‍♀️ 你的背包里没有可以出售的鱼")

        if not isinstance(name, str) or name.strip() == "":
            name = ""

        is_all = num == -1

        if name == "":
            total_point = 0
            for fish_name, count in user_fish.items():
                fish_info = fish_map.get(fish_name)
                if not fish_info:
                    continue

                total_point += int(fish_info.get("sellPoint", 0)) * count
                await g_pDBService.userItem.updateUserItemByName(
                    uid,
                    cls._fish_item_key(fish_name),
                    0,
                )

            current_point = await g_pDBService.user.getUserPointByUid(uid)
            if current_point < 0:
                current_point = 0

            await g_pDBService.user.updateUserPointByUid(uid, current_point + total_point)

            return cls._t(
                "sellFish",
                "successAll",
                "💰 成功出售全部鱼获，获得农场币：{point}，当前农场币：{num}",
            ).format(point=total_point, num=current_point + total_point)

        if name not in user_fish:
            return cls._t(
                "sellFish",
                "error",
                "❌ 出售鱼获{name}出错：背包中不存在该鱼",
            ).format(name=name)

        available = user_fish[name]
        sell_amount = available if is_all else min(available, num)

        if sell_amount <= 0:
            return cls._t(
                "sellFish",
                "error1",
                "❌ 出售鱼获{name}出错：数量不足",
            ).format(name=name)

        fish_info = fish_map.get(name)
        if not fish_info:
            return cls._t(
                "sellFish",
                "configError",
                "❌ 鱼类配置加载失败，请联系管理员",
            )

        total_point = int(fish_info.get("sellPoint", 0)) * sell_amount

        await g_pDBService.userItem.updateUserItemByName(
            uid,
            cls._fish_item_key(name),
            available - sell_amount,
        )

        current_point = await g_pDBService.user.getUserPointByUid(uid)
        if current_point < 0:
            current_point = 0

        await g_pDBService.user.updateUserPointByUid(uid, current_point + total_point)

        return cls._t(
            "sellFish",
            "success",
            "💰 成功出售{name}，获得农场币：{point}，当前农场币：{num}",
        ).format(name=name, point=total_point, num=current_point + total_point)


g_pFishingManager = CFishingManager()