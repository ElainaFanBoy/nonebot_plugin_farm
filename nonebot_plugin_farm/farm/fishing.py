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
    def _get_current_time_tag(cls) -> str:
        """根据当前服务器时间返回 morning / afternoon / night"""
        now_dt = g_pToolManager.dateTime()
        hour = now_dt.hour

        if 6 <= hour < 12:
            return "morning"
        if 12 <= hour < 20:
            return "afternoon"
        return "night"

    @classmethod
    def _match_time_rule(cls, rule: str | None) -> bool:
        """
        判断当前时间是否满足鱼池时段规则
        允许：
        - all
        - morning
        - afternoon
        - night
        - ["morning", "night"] 这种 list
        """
        if not rule:
            return True

        current_tag = cls._get_current_time_tag()

        if isinstance(rule, list):
            return current_tag in rule or "all" in rule

        if isinstance(rule, str):
            return rule == "all" or rule == current_tag

        return True

    @classmethod
    def _get_effective_king_rate(cls) -> float:
        """
        鱼王独立概率：
        - 默认 0.8%
        - 未来活动可通过 kingRate / kingRateMultiplier 调整
        例如：
            kingRate = 0.012
        或：
            kingRateMultiplier = 2
        """
        system_map = cls._get_system_map()
        base_rate = float(system_map.get("kingRate", 0.008))
        multiplier = float(system_map.get("kingRateMultiplier", 1.0))
        effective_rate = base_rate * multiplier

        if effective_rate < 0:
            effective_rate = 0.0
        if effective_rate > 1:
            effective_rate = 1.0
        return effective_rate

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
    async def _split_pool(cls, use_bait_name: str, user_level: int) -> tuple[dict | None, list[dict]]:
        """
        按当前等级与时段拆分鱼池：
        - king_entry: 鱼王条目（不受 time 限制，但可受 entry.minLevel 限制）
        - normal_pool: 普通鱼条目（受 time 过滤）
        """
        fish_map = cls._get_fish_map()
        pool_map = cls._get_pool_map()

        raw_pool = pool_map.get(use_bait_name, [])
        if not raw_pool:
            return None, []

        king_entry: dict | None = None
        normal_pool: list[dict] = []

        for entry in raw_pool:
            fish_name = entry.get("fish", "")
            fish_info = fish_map.get(fish_name)
            if not fish_info:
                logger.warning(f"fish_pool.json 中的鱼 {fish_name} 未在 fish.json 中定义")
                continue

            weight = int(entry.get("weight", 0))
            if weight <= 0:
                continue

            entry_is_king = bool(entry.get("isKing", False)) or bool(fish_info.get("isKing", False))

            if entry_is_king:
                # 鱼王：不受时段限制，但仍允许配 entry.minLevel
                required_level = int(entry.get("minLevel", 0))
                if user_level < required_level:
                    continue

                if king_entry is None:
                    king_entry = entry
                else:
                    logger.warning(f"{use_bait_name} 鱼池中存在多个鱼王条目，当前仅取第一个：{king_entry.get('fish')}")
                continue

            # 普通鱼：优先使用 entry.minLevel，否则回退到 fish.level * 20
            required_level = int(entry.get("minLevel", int(fish_info.get("level", 0)) * 20))
            if user_level < required_level:
                continue

            time_rule = entry.get("time", "all")
            if not cls._match_time_rule(time_rule):
                continue

            normal_pool.append(entry)

        return king_entry, normal_pool

    @classmethod
    async def _roll_one(cls, use_bait_name: str, bait_info: dict, user_level: int) -> dict:
        """
        单次钓鱼逻辑：
        1. 先判定逃跑
        2. 再独立判定鱼王（固定 kingRate）
        3. 没中鱼王时，再从当前时段普通池按权重抽
        4. 幸运触发则同鱼 ×5

        返回:
        {
            "ok": True/False,
            "escaped": True/False,
            "fish": fish_name or "",
            "count": 0/1/5,
            "exp": total_exp,
            "isKing": bool,
            "lucky": bool
        }
        """
        system_map = cls._get_system_map()
        fish_map = cls._get_fish_map()

        king_entry, normal_pool = await cls._split_pool(use_bait_name, user_level)

        # 如果连鱼王也没有、普通池也没有，说明当前池彻底不可用
        if king_entry is None and not normal_pool:
            return {
                "ok": False,
                "escaped": False,
                "fish": "",
                "count": 0,
                "exp": 0,
                "isKing": False,
                "lucky": False,
            }

        # 先判定逃跑
        escape_rate = float(bait_info.get("escapeRate", system_map.get("defaultEscapeRate", 0.2)))
        if random.random() < escape_rate:
            return {
                "ok": True,
                "escaped": True,
                "fish": "",
                "count": 0,
                "exp": 0,
                "isKing": False,
                "lucky": False,
            }

        result_fish_name = ""
        result_fish_info = None
        is_king = False

        # 鱼王独立判定：任何时段固定 0.8%（或未来活动倍率）
        if king_entry is not None and random.random() < cls._get_effective_king_rate():
            result_fish_name = king_entry["fish"]
            result_fish_info = fish_map.get(result_fish_name)
            is_king = True
        else:
            # 没中鱼王，则从普通池抽
            if not normal_pool:
                # 理论上很少见：当前时段没有普通鱼，但鱼王也没中
                return {
                    "ok": True,
                    "escaped": False,
                    "fish": "",
                    "count": 0,
                    "exp": 0,
                    "isKing": False,
                    "lucky": False,
                }

            population = [x["fish"] for x in normal_pool]
            weights = [int(x["weight"]) for x in normal_pool]
            result_fish_name = random.choices(population=population, weights=weights, k=1)[0]
            result_fish_info = fish_map.get(result_fish_name)

        if not result_fish_info:
            return {
                "ok": False,
                "escaped": False,
                "fish": "",
                "count": 0,
                "exp": 0,
                "isKing": False,
                "lucky": False,
            }

        lucky_rate = float(system_map.get("luckyFiveRate", 0.012))
        lucky = random.random() < lucky_rate
        fish_count = 5 if lucky else 1

        exp_per_fish = int(result_fish_info.get("exp", 0))
        total_exp = exp_per_fish * fish_count

        return {
            "ok": True,
            "escaped": False,
            "fish": result_fish_name,
            "count": fish_count,
            "exp": total_exp,
            "isKing": is_king,
            "lucky": lucky,
        }

    @classmethod
    async def fish(cls, uid: str, bait_name: str = "", num: int = 1) -> str:
        """
        批量钓鱼：
        - 普通鱼饵批量：一次消耗 num 个鱼饵，执行 num 次钓鱼
        - 每次成功若触发 luckyFiveRate，则同鱼 ×5
        - 每次钓鱼都计入 dailyCount
        - 整批钓鱼只进入一次 CD
        """
        bait_map = cls._get_bait_map()
        fish_map = cls._get_fish_map()
        system_map = cls._get_system_map()

        if not bait_map or not fish_map or not system_map:
            logger.warning("fish 失败：钓鱼配置未正确加载")
            return cls._t("fishing", "configError", "❌ 钓鱼配置加载失败，请联系管理员")

        if num <= 0:
            num = 1

        bait_data = await cls.resolve_bait(uid, bait_name)
        if not bait_data:
            return cls._t("fishing", "noBait", "🪱 你没有可用的鱼饵，先去物品商店看看吧")

        use_bait_name = bait_data["name"]
        bait_info = bait_data["info"]
        bait_item_key = bait_data["itemKey"]

        level_info = await g_pDBService.user.getUserLevelByUid(uid)
        user_level = level_info[0] if isinstance(level_info, tuple) and len(level_info) >= 1 else 0
        if user_level < 0:
            user_level = 0

        state = await g_pDBService.userFishingState.getStateByUid(uid)
        now_dt = g_pToolManager.dateTime()
        today_str = now_dt.strftime("%Y-%m-%d")
        now_ts = int(time.time())

        cooldown_seconds = int(system_map.get("cooldownSeconds", 20))
        daily_limit = int(system_map.get("dailyLimit", 30))

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

        remain_daily = daily_limit - daily_count
        if remain_daily <= 0:
            return cls._t("fishing", "dailyLimit", "📅 你今天的钓鱼次数已经用完啦，明天再来吧")

        current_bait_count = await g_pDBService.userItem.getUserItemByName(uid, bait_item_key)
        if current_bait_count is None or current_bait_count <= 0:
            return cls._t("fishing", "noBait", "🪱 你没有可用的鱼饵，先去物品商店看看吧")

        actual_num = min(num, remain_daily, current_bait_count)
        if actual_num <= 0:
            return cls._t("fishing", "noBait", "🪱 你没有可用的鱼饵，先去物品商店看看吧")

        # 先检查至少存在一种可能鱼（鱼王或普通鱼）
        king_entry, normal_pool = await cls._split_pool(use_bait_name, user_level)
        if king_entry is None and not normal_pool:
            return cls._t("fishing", "noAvailableFish", "🎣 当前鱼饵在这个时段暂无可钓鱼种，请换个时间再来试试")

        # 先扣鱼饵
        if not await g_pDBService.userItem.addUserItemByUid(uid, bait_item_key, -actual_num):
            return cls._t("fishing", "consumeError", "❌ 扣除鱼饵失败，请稍后重试")

        fish_counter: dict[str, int] = {}
        total_exp = 0
        escape_count = 0
        lucky_count = 0
        king_count = 0
        empty_count = 0  # 当前时段普通池为空且鱼王未中时的空竿次数

        for _ in range(actual_num):
            roll = await cls._roll_one(use_bait_name, bait_info, user_level)

            if not roll["ok"]:
                continue

            if roll["escaped"]:
                escape_count += 1
                continue

            fish_name = roll["fish"]
            fish_num = int(roll["count"])
            if not fish_name or fish_num <= 0:
                empty_count += 1
                continue

            total_exp += int(roll["exp"])
            fish_counter[fish_name] = fish_counter.get(fish_name, 0) + fish_num

            if roll["lucky"]:
                lucky_count += 1
            if roll["isKing"]:
                king_count += 1

        # 发放鱼获
        for fish_name, cnt in fish_counter.items():
            await g_pDBService.userItem.addUserItemByUid(uid, cls._fish_item_key(fish_name), cnt)

        # 加经验
        current_exp = await g_pDBService.user.getUserExpByUid(uid)
        if current_exp < 0:
            current_exp = 0
        await g_pDBService.user.updateUserExpByUid(uid, current_exp + total_exp)

        # 更新状态
        await g_pDBService.userFishingState.upsertStateByUid(
            uid=uid,
            lastFishTs=now_ts,
            dailyDate=today_str,
            dailyCount=daily_count + actual_num,
        )

        lines = [
            f"🎣 本次使用【{use_bait_name}】×{actual_num}",
            f"🌊 空军：{escape_count} 次",
        ]

        if empty_count > 0:
            lines.append(f"🎐 时段空竿：{empty_count} 次")

        if lucky_count > 0:
            lines.append(f"✨ 运气特别好：{lucky_count} 次（同鱼 ×5）")

        if king_count > 0:
            lines.append(f"👑 鱼王次数：{king_count}")

        lines.append(f"📈 总经验：+{total_exp}")

        if fish_counter:
            lines.append("🐟 鱼获：")
            sorted_items = sorted(
                fish_counter.items(),
                key=lambda x: (
                    -int(fish_map.get(x[0], {}).get("level", 0)),
                    -int(fish_map.get(x[0], {}).get("sellPoint", 0)),
                    x[0],
                ),
            )
            for fish_name, cnt in sorted_items:
                lines.append(f"- {fish_name} ×{cnt}")
        else:
            lines.append("🤷 本次什么也没钓到")

        if actual_num < num:
            lines.append(f"⚠️ 实际只执行了 {actual_num} 次（受鱼饵数量或每日次数限制）")

        return "\n".join(lines)

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