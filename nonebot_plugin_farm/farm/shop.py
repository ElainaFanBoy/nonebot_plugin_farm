import math

from nonebot import logger
from zhenxun_utils.image_utils import ImageTemplate

from ..config import g_sResourcePath, g_sTranslation
from ..dbService import g_pDBService
from ..json import g_pJsonManager


class CShopManager:
    @classmethod
    async def getSeedShopImage(cls, filterKey: str | int = 1, num: int = 1) -> bytes:
        """获取商店页面

        Args:
            filterKey (str|int):
                - 字符串: 根据关键字筛选种子名称
                - 整数: 翻至对应页（无筛选）
            num (int, optional): 当 filterKey 为字符串时，用于指定页码。Defaults to 1.

        Returns:
            bytes: 返回商店图片bytes
        """
        # 解析参数：区分筛选关键字和页码
        filterStr = None
        if isinstance(filterKey, int):
            page = filterKey
        else:
            filterStr = filterKey
            page = num

        # 表头定义
        columnName = [
            "-",
            "种子名称",
            "种子单价",
            "解锁等级",
            "果实单价",
            "收获经验",
            "收获数量",
            "成熟时间（小时）",
            "收获次数",
            "是否可以上架交易行",
        ]

        # 查询所有可购买作物，并根据筛选关键字过滤
        plants = await g_pDBService.plant.listPlants()
        filteredPlants = []
        for plant in plants:
            # 跳过未解锁购买的种子
            if plant["isBuy"] == 0:
                continue
            # 字符串筛选
            if filterStr and filterStr not in plant["name"]:
                continue
            filteredPlants.append(plant)

        # 计算分页
        totalCount = len(filteredPlants)
        pageCount = math.ceil(totalCount / 15) if totalCount else 1
        startIndex = (page - 1) * 15
        pageItems = filteredPlants[startIndex : startIndex + 15]

        # 构建数据行
        dataList = []
        for plant in pageItems:
            # 图标处理
            icon = ""
            iconPath = g_sResourcePath / f"plant/{plant['name']}/icon.png"
            if iconPath.exists():
                icon = (iconPath, 33, 33)

            # 交易行标记
            sell = "可以" if plant["sell"] else "不可以"

            dataList.append(
                [
                    icon,
                    plant["name"],  # 种子名称
                    plant["buy"],  # 种子单价
                    plant["level"],  # 解锁等级
                    plant["price"],  # 果实单价
                    plant["experience"],  # 收获经验
                    plant["harvest"],  # 收获数量
                    plant["time"],  # 成熟时间（小时）
                    plant["crop"],  # 收获次数
                    sell,  # 是否可上架交易行
                ]
            )

        # 页码标题
        title = f"种子商店 页数: {page}/{pageCount}"

        # 渲染表格并返回图片bytes
        result = await ImageTemplate.table_page(
            title,
            "购买示例：@IRONY 购买种子 大白菜 5",
            columnName,
            dataList,
        )
        return result.pic2bytes()

    @classmethod
    async def buySeed(cls, uid: str, name: str, num: int = 1) -> str:
        """购买种子

        Args:
            uid (str): 用户Uid
            name (str): 植物名称
            num (int, optional): 购买数量

        Returns:
            str:
        """

        if num <= 0:
            return g_sTranslation["buySeed"]["notNum"]

        plantInfo = await g_pDBService.plant.getPlantByName(name)
        if not plantInfo:
            return g_sTranslation["buySeed"]["error"]

        level = await g_pDBService.user.getUserLevelByUid(uid)

        if level[0] < int(plantInfo["level"]):
            return g_sTranslation["buySeed"]["noLevel"]

        point = await g_pDBService.user.getUserPointByUid(uid)
        total = int(plantInfo["buy"]) * num

        logger.debug(
            f"用户：{uid}购买{name}，数量为{num}。用户农场币为{point}，购买需要{total}"
        )

        if point < total:
            return g_sTranslation["buySeed"]["noPoint"]
        else:
            await g_pDBService.user.updateUserPointByUid(uid, point - total)

            if not await g_pDBService.userSeed.addUserSeedByUid(uid, name, num):
                return g_sTranslation["buySeed"]["errorSql"]

            return g_sTranslation["buySeed"]["success"].format(
                name=name, total=total, point=point - total
            )

    @classmethod
    async def sellPlantByUid(cls, uid: str, name: str = "", num: int = 1) -> str:
        """出售作物

        Args:
            uid (str): 用户Uid

        Returns:
            str:
        """
        if not isinstance(name, str) or name.strip() == "":
            name = ""

        plant = await g_pDBService.userPlant.getUserPlantByUid(uid)
        if not plant:
            return g_sTranslation["sellPlant"]["no"]

        point = 0
        totalSold = 0
        isAll = num == -1

        if name == "":
            for plantName, count in plant.items():
                plantInfo = await g_pDBService.plant.getPlantByName(plantName)
                if not plantInfo:
                    continue

                point += plantInfo["price"] * count
                await g_pDBService.userPlant.updateUserPlantByName(uid, plantName, 0)
        else:
            if name not in plant:
                return g_sTranslation["sellPlant"]["error"].format(name=name)
            available = plant[name]
            sellAmount = available if isAll else min(available, num)
            if sellAmount <= 0:
                return g_sTranslation["sellPlant"]["error1"].format(name=name)
            await g_pDBService.userPlant.updateUserPlantByName(
                uid, name, available - sellAmount
            )
            totalSold = sellAmount

        if name == "":
            totalPoint = point
        else:
            plantInfo = await g_pDBService.plant.getPlantByName(name)
            if not plantInfo:
                price = 0
            else:
                price = plantInfo["price"]

            totalPoint = totalSold * price

        currentPoint = await g_pDBService.user.getUserPointByUid(uid)
        await g_pDBService.user.updateUserPointByUid(uid, currentPoint + totalPoint)

        if name == "":
            return g_sTranslation["sellPlant"]["success"].format(
                point=totalPoint, num=currentPoint + totalPoint
            )
        else:
            return g_sTranslation["sellPlant"]["success1"].format(
                name=name, point=totalPoint, num=currentPoint + totalPoint
            )
    
    @classmethod
    async def getItemShopImage(
        cls, filterKey: str | int | None = None, page: int = 1
    ) -> bytes:
        """
        获取物品商店图片
        支持：
        - getItemShopImage(1)
        - getItemShopImage("高级", 2)
        """
        bait_map = g_pJsonManager.m_pBait.get("bait", {})
        if not bait_map:
            result = await ImageTemplate.table_page(
                "物品商店",
                "当前没有可售卖的物品",
                ["-", "物品名称", "农场币", "点券", "解锁等级", "鱼饵等级"],
                [],
            )
            return result.pic2bytes()

        # 兼容 getItemShopImage(page) 调用方式
        if isinstance(filterKey, int):
            page = filterKey
            filterKey = None

        keyword = ""
        if isinstance(filterKey, str):
            keyword = filterKey.strip()

        all_rows: list[list] = []
        for bait_name, bait_info in bait_map.items():
            if keyword and keyword not in bait_name:
                continue

            all_rows.append(
                [
                    "",
                    bait_name,
                    int(bait_info.get("point", 0)),
                    int(bait_info.get("vipPoint", 0)),
                    int(bait_info.get("unlockLevel", 0)),
                    int(bait_info.get("baitLevel", 0)),
                ]
            )

        all_rows.sort(key=lambda x: (x[5], x[4], x[1]))

        page_size = 10
        total = len(all_rows)
        total_page = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_page))

        start = (page - 1) * page_size
        end = start + page_size
        page_rows = all_rows[start:end]

        sub_title = f"物品商店 第 {page}/{total_page} 页"
        if keyword:
            sub_title += f"｜筛选：{keyword}"

        result = await ImageTemplate.table_page(
            "物品商店",
            sub_title,
            ["-", "物品名称", "农场币", "点券", "解锁等级", "鱼饵等级"],
            page_rows,
        )
        return result.pic2bytes()

    @classmethod
    async def buyItem(cls, uid: str, name: str, num: int = 1) -> str:
        """购买物品（当前主要是鱼饵）"""
        if not isinstance(name, str) or not name.strip():
            return g_sTranslation["buyItem"]["notItem"]

        if num <= 0:
            num = 1

        bait_map = g_pJsonManager.m_pBait.get("bait", {})
        bait_info = bait_map.get(name)
        if not bait_info:
            return g_sTranslation["buyItem"]["error"]

        # 用户等级
        level_info = await g_pDBService.user.getUserLevelByUid(uid)
        user_level = level_info[0] if isinstance(level_info, tuple) and len(level_info) >= 1 else 0
        if user_level < int(bait_info.get("unlockLevel", 0)):
            return g_sTranslation["buyItem"]["noLevel"]

        need_point = int(bait_info.get("point", 0)) * num
        need_vip_point = int(bait_info.get("vipPoint", 0)) * num

        user_point = await g_pDBService.user.getUserPointByUid(uid)
        user_vip_point = await g_pDBService.user.getUserVipPointByUid(uid)

        if user_point < need_point:
            return g_sTranslation["buyItem"]["noPoint"]

        if user_vip_point < need_vip_point:
            return g_sTranslation["buyItem"]["noVipPoint"]

        # 扣钱
        if not await g_pDBService.user.updateUserPointByUid(uid, user_point - need_point):
            return g_sTranslation["buyItem"]["errorSql"]

        if not await g_pDBService.user.updateUserVipPointByUid(uid, user_vip_point - need_vip_point):
            # 这里不做回滚，先保持和现有 buySeed 的简洁风格一致
            return g_sTranslation["buyItem"]["errorSql"]

        # 入背包
        item_key = f"bait:{name}"
        if not await g_pDBService.userItem.addUserItemByUid(uid, item_key, num):
            return g_sTranslation["buyItem"]["errorSql"]

        return g_sTranslation["buyItem"]["success"].format(
            name=name,
            num=num,
            point=user_point - need_point,
            vipPoint=user_vip_point - need_vip_point,
        )


g_pShopManager = CShopManager()
