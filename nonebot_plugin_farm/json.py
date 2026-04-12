import json

from nonebot import logger

from . import config
from .request import g_pRequestManager


class CJsonManager:
    def __init__(self):
        self.m_pItem = {}
        self.m_pLevel = {}
        self.m_pSoil = {}
        self.m_pSign = {}

        # 钓鱼系统
        self.m_pBait = {}
        self.m_pFish = {}
        self.m_pFishPool = {}
        self.m_pFishingSystem = {}

    async def init(self) -> bool:
        if not await self.initItem():
            return False

        if not await self.initLevel():
            return False

        if not await self.initSoil():
            return False

        if not await self.initBait():
            return False

        if not await self.initFish():
            return False

        if not await self.initFishPool():
            return False

        if not await self.initFishingSystem():
            return False

        return await self.initSignInFile()

    async def initItem(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "item.json",
                encoding="utf-8",
            ) as file:
                self.m_pItem = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("item.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"item.json JSON格式错误: {e}")
            return False

    async def initLevel(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "level.json",
                encoding="utf-8",
            ) as file:
                self.m_pLevel = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("level.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"level.json JSON格式错误: {e}")
            return False

    async def initSoil(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "soil.json",
                encoding="utf-8",
            ) as file:
                self.m_pSoil = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("soil.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"soil.json JSON格式错误: {e}")
            return False

    async def initBait(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "bait.json",
                encoding="utf-8",
            ) as file:
                self.m_pBait = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("bait.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"bait.json JSON格式错误: {e}")
            return False

    async def initFish(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "fish.json",
                encoding="utf-8",
            ) as file:
                self.m_pFish = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("fish.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"fish.json JSON格式错误: {e}")
            return False

    async def initFishPool(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "fish_pool.json",
                encoding="utf-8",
            ) as file:
                self.m_pFishPool = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("fish_pool.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"fish_pool.json JSON格式错误: {e}")
            return False

    async def initFishingSystem(self) -> bool:
        try:
            with open(
                config.g_sConfigPath / "fishing_system.json",
                encoding="utf-8",
            ) as file:
                self.m_pFishingSystem = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("fishing_system.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"fishing_system.json JSON格式错误: {e}")
            return False

    async def initSignInFile(self) -> bool:
        if not await g_pRequestManager.initSignInFile():
            config.g_bSignStatus = False
            return False
        else:
            result = await self.initSign()
            config.g_bSignStatus = result
            return result

    async def initSign(self) -> bool:
        try:
            with open(
                config.g_sSignInPath,
                encoding="utf-8",
            ) as file:
                self.m_pSign = json.load(file)
                return True
        except FileNotFoundError:
            logger.warning("sign_in.json 打开失败")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"sign_in.json JSON格式错误: {e}")
            return False


g_pJsonManager = CJsonManager()