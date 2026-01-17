import inspect

from nonebot import logger
from nonebot.adapters import Event
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    At,
    Match,
    MultiVar,
    Option,
    Query,
    Subcommand,
    on_alconna,
    store_true,
)
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import waiter
from zhenxun_utils.message import MessageUtils

from .config import g_bSignStatus, g_sTranslation
from .dbService import g_pDBService
from .farm.farm import g_pFarmManager
from .farm.shop import g_pShopManager
from .json import g_pJsonManager
from .tool import g_pToolManager

diuse_register = on_alconna(
    Alconna("开通农场"),
    priority=5,
    rule=to_me(),
    block=True,
    use_cmd_start=True,
)


@diuse_register.handle()
async def handle_register(session: Uninfo):
    uid = str(session.user.id)
    user = await g_pDBService.user.getUserInfoByUid(uid)

    if user:
        await MessageUtils.build_message(g_sTranslation["register"]["repeat"]).send(
            reply_to=True
        )
        return

    try:
        raw_name = str(session.user.name)
        safe_name = g_pToolManager.sanitize_username(raw_name)

        # 初始化用户信息
        success = await g_pDBService.user.initUserInfoByUid(
            uid=uid, name=safe_name, exp=0, point=500
        )

        msg = (
            g_sTranslation["register"]["success"].format(point=500)
            if success
            else g_sTranslation["register"]["error"]
        )
        logger.info(f"用户注册 {'成功' if success else '失败'}：{uid}")

    except Exception as e:
        msg = g_sTranslation["register"]["error"]
        logger.error(f"注册异常 | UID:{uid} | 错误：{e}")

    await MessageUtils.build_message(msg).send(reply_to=True)


diuse_farm = on_alconna(
    Alconna(
        "我的农场",
        Option("--all", action=store_true),
        Subcommand("detail", help_text="农场详述"),
        Subcommand("my-point", help_text="我的农场币"),
        Subcommand("seed-shop", Args["res?", MultiVar(str)], help_text="种子商店"),
        Subcommand("buy-seed", Args["name?", str]["num?", int], help_text="购买种子"),
        Subcommand("my-seed", help_text="我的种子"),
        Subcommand("sowing", Args["name?", str]["num?", int], help_text="播种"),
        Subcommand("harvest", help_text="收获"),
        Subcommand("eradicate", help_text="铲除"),
        Subcommand("my-plant", help_text="我的作物"),
        Subcommand("sell-plant", Args["name?", str]["num?", int], help_text="出售作物"),
        Subcommand("stealing", Args["target?", At], help_text="偷菜"),
        Subcommand("change-name", Args["name?", str], help_text="更改农场名"),
        Subcommand("sign-in", help_text="农场签到"),
        Subcommand("admin-up", Args["num?", int], help_text="农场下阶段"),
    ),
    priority=5,
    block=True,
    use_cmd_start=True,
)


@diuse_farm.assign("$main")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    image = await g_pFarmManager.drawFarmByUid(uid)
    await MessageUtils.build_message(image).send(reply_to=True)


diuse_farm.shortcut(
    "农场详述",
    command="我的农场",
    arguments=["detail"],
    prefix=True,
)


@diuse_farm.assign("detail")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    info = await g_pFarmManager.drawDetailFarmByUid(uid)

    await MessageUtils.alc_forward_msg(
        [info], session.self_id, session.user.name
    ).send()


diuse_farm.shortcut(
    "我的农场币",
    command="我的农场",
    arguments=["my-point"],
    prefix=True,
)


@diuse_farm.assign("my-point")
async def _(session: Uninfo):
    uid = str(session.user.id)
    point = await g_pDBService.user.getUserPointByUid(uid)

    if point < 0:
        await MessageUtils.build_message(g_sTranslation["basic"]["notFarm"]).send()
        return False

    await MessageUtils.build_message(
        g_sTranslation["basic"]["point"].format(point=point)
    ).send(reply_to=True)


diuse_farm.shortcut(
    "种子商店(.*?)",
    command="我的农场",
    arguments=["seed-shop"],
    prefix=True,
)


@diuse_farm.assign("seed-shop")
async def _(session: Uninfo, res: Match[tuple[str, ...]]):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    if res.result is inspect._empty:
        raw = []
    else:
        raw = res.result

    filterKey: str | int | None = None
    page: int = 1

    if len(raw) >= 1 and raw[0] is not None:
        first = raw[0]
        if isinstance(first, str) and first.isdigit():
            page = int(first)
        else:
            filterKey = first

    if (
        len(raw) >= 2
        and raw[1] is not None
        and isinstance(raw[1], str)
        and raw[1].isdigit()
    ):
        page = int(raw[1])

    if filterKey is None:
        image = await g_pShopManager.getSeedShopImage(page)
    else:
        image = await g_pShopManager.getSeedShopImage(filterKey, page)

    await MessageUtils.build_message(image).send()


diuse_farm.shortcut(
    "购买种子(?P<name>.*?)",
    command="我的农场",
    arguments=["buy-seed", "{name}"],
    prefix=True,
)


@diuse_farm.assign("buy-seed")
async def _(
    session: Uninfo, name: Match[str], num: Query[int] = AlconnaQuery("num", 1)
):
    if not name.available:
        await MessageUtils.build_message(g_sTranslation["buySeed"]["notSeed"]).finish(
            reply_to=True
        )

    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    result = await g_pShopManager.buySeed(uid, name.result, num.result)
    await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "我的种子",
    command="我的农场",
    arguments=["my-seed"],
    prefix=True,
)


@diuse_farm.assign("my-seed")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    result = await g_pFarmManager.getUserSeedByUid(uid)
    await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "播种(?P<name>.*?)",
    command="我的农场",
    arguments=["sowing", "{name}"],
    prefix=True,
)


@diuse_farm.assign("sowing")
async def _(
    session: Uninfo, name: Match[str], num: Query[int] = AlconnaQuery("num", -1)
):
    if not name.available:
        await MessageUtils.build_message(g_sTranslation["sowing"]["notSeed"]).finish(
            reply_to=True
        )

    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    result = await g_pFarmManager.sowing(uid, name.result, num.result)
    await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "收获",
    command="我的农场",
    arguments=["harvest"],
    prefix=True,
)


@diuse_farm.assign("harvest")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    result = await g_pFarmManager.harvest(uid)
    await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "铲除",
    command="我的农场",
    arguments=["eradicate"],
    prefix=True,
)


@diuse_farm.assign("eradicate")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    # 1. 获取作物状态
    state = await g_pFarmManager.getEradicateState(uid)
    
    # 2. 判断逻辑
    # 如果有未成熟作物，需要确认
    if state["immature"] > 0:
        confirm_msg = f"您即将铲除未成熟作物，数量为{state['immature']}个，是否确认？\n回复“是”确认，否则取消。 🚜"
        
        await MessageUtils.build_message(confirm_msg).send(reply_to=True)

        @waiter(waits=["message"], keep_session=True)
        async def check(event: Event):
            return event.get_plaintext()

        resp = await check.wait(timeout=30) # 设置30秒超时
        
        if resp is None:
            await MessageUtils.build_message("等待铲除回复超时，请重试").send(reply_to=True)
            return
            
        if resp != "是":
            await MessageUtils.build_message("未铲除未成熟作物。").send(reply_to=True)
            result = await g_pFarmManager.eradicate(uid, confirm_immature=False)
            await MessageUtils.build_message(result).send(reply_to=True)
            return
            
        # 用户确认：执行铲除（参数为 True）
        result = await g_pFarmManager.eradicate(uid, confirm_immature=True)
        await MessageUtils.build_message(result).send(reply_to=True)

    else:
        # 没有未成熟作物（只有枯萎或为空），直接执行原有逻辑（参数为 False）
        result = await g_pFarmManager.eradicate(uid, confirm_immature=False)
        await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "我的作物",
    command="我的农场",
    arguments=["my-plant"],
    prefix=True,
)


@diuse_farm.assign("my-plant")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    result = await g_pFarmManager.getUserPlantByUid(uid)
    await MessageUtils.build_message(result).send(reply_to=True)


reclamation = on_alconna(
    Alconna("开垦"),
    priority=5,
    block=True,
    use_cmd_start=True,
)


@reclamation.handle()
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    condition = await g_pFarmManager.reclamationCondition(uid)
    condition += f"\n{g_sTranslation['reclamation']['confirm']}"
    await MessageUtils.build_message(condition).send(reply_to=True)

    @waiter(waits=["message"], keep_session=True)
    async def check(event: Event):
        return event.get_plaintext()

    resp = await check.wait(timeout=60)
    if resp is None:
        await MessageUtils.build_message(g_sTranslation["reclamation"]["timeOut"]).send(
            reply_to=True
        )
        return
    if not resp == "是":
        return

    res = await g_pFarmManager.reclamation(uid)
    await MessageUtils.build_message(res).send(reply_to=True)


diuse_farm.shortcut(
    "出售作物(?P<name>.*?)",
    command="我的农场",
    arguments=["sell-plant", "{name}"],
    prefix=True,
)


@diuse_farm.assign("sell-plant")
async def _(
    session: Uninfo, name: Match[str], num: Query[int] = AlconnaQuery("num", -1)
):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    result = await g_pShopManager.sellPlantByUid(uid, name.result, num.result)
    await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "偷菜",
    command="我的农场",
    arguments=["stealing"],
    prefix=True,
)


@diuse_farm.assign("stealing")
async def _(session: Uninfo, target: Match[At]):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    if not target.available:
        await MessageUtils.build_message(g_sTranslation["stealing"]["noTarget"]).finish(
            reply_to=True
        )

    tar = target.result
    result = await g_pDBService.user.isUserExist(tar.target)

    if not result:
        await MessageUtils.build_message(
            g_sTranslation["stealing"]["targetNotFarm"]
        ).send()
        return None

    result = await g_pFarmManager.stealing(uid, tar.target)
    await MessageUtils.build_message(result).send(reply_to=True)


diuse_farm.shortcut(
    "更改农场名(?P<name>)",
    command="我的农场",
    arguments=["change-name", "{name}"],
    prefix=True,
)


@diuse_farm.assign("change-name")
async def _(session: Uninfo, name: Match[str]):
    if not name.available:
        await MessageUtils.build_message(g_sTranslation["changeName"]["noName"]).finish(
            reply_to=True
        )

    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    safeName = g_pToolManager.sanitize_username(name.result)

    if safeName == "神秘农夫":
        await MessageUtils.build_message(g_sTranslation["changeName"]["error"]).send(
            reply_to=True
        )
        return

    result = await g_pDBService.user.updateUserNameByUid(uid, safeName)

    if result:
        await MessageUtils.build_message(g_sTranslation["changeName"]["success"]).send(
            reply_to=True
        )
    else:
        await MessageUtils.build_message(g_sTranslation["changeName"]["error1"]).send(
            reply_to=True
        )


diuse_farm.shortcut(
    "农场签到",
    command="我的农场",
    arguments=["sign-in"],
    prefix=True,
)


@diuse_farm.assign("sign-in")
async def _(session: Uninfo):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    # 判断签到是否正常加载
    if not g_bSignStatus:
        await MessageUtils.build_message(g_sTranslation["signIn"]["error"]).send()

        return

    toDay = g_pToolManager.dateTime().date().today()
    message = ""
    status = await g_pDBService.userSign.sign(uid, toDay.strftime("%Y-%m-%d"))

    # 如果完成签到
    if status == 1 or status == 2:
        # 获取签到总天数
        signDay = await g_pDBService.userSign.getUserSignCountByDate(
            uid, toDay.strftime("%Y-%m")
        )
        exp, point = await g_pDBService.userSign.getUserSignRewardByDate(
            uid, toDay.strftime("%Y-%m-%d")
        )
        
        if status == 1:
            message += g_sTranslation["signIn"]["success"].format(
                day=signDay, exp=exp, num=point
            )
        
        elif status == 2:
            print(g_sTranslation["signIn"])
            message += "📝 今日已签到，不需要再签到了捏 🌟"

        #reward = g_pJsonManager.m_pSign["continuou"].get(f"{signDay}", None)

        #if reward:
            #extraPoint = reward.get("point", 0)
            #extraExp = reward.get("exp", 0)

            #plant = reward.get("plant", {})

            #message += g_sTranslation["signIn"]["grandTotal"].format(
                #exp=extraExp, num=extraPoint
            #)

            #vipPoint = reward.get("vipPoint", 0)

            #if vipPoint > 0:
                #message += g_sTranslation["signIn"]["grandTotal1"].format(num=vipPoint)

            #if plant:
                #for key, value in plant.items():
                    #message += g_sTranslation["signIn"]["grandTotal2"].format(
                        #name=key, num=value
                    #)
    else:
        message = g_sTranslation["signIn"]["error1"]

    await MessageUtils.build_message(message).send()

    # await MessageUtils.alc_forward_msg([info], session.self_id, BotConfig.self_nickname).send(reply_to=True)


soil_upgrade = on_alconna(
    Alconna("土地升级", Args["index", int]),
    priority=5,
    block=True,
    use_cmd_start=True,
)


@soil_upgrade.handle()
async def _(session: Uninfo, index: Query[int] = AlconnaQuery("index", 1)):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    condition = await g_pFarmManager.soilUpgradeCondition(uid, index.result)

    await MessageUtils.build_message(condition).send(reply_to=True)

    if not condition.startswith("将土地升级至："):
        return

    @waiter(waits=["message"], keep_session=True)
    async def check(event: Event):
        return event.get_plaintext()

    resp = await check.wait(timeout=60)
    if resp is None:
        await MessageUtils.build_message(g_sTranslation["soilInfo"]["timeOut"]).send(
            reply_to=True
        )
        return
    if not resp == "是":
        return

    res = await g_pFarmManager.soilUpgrade(uid, index.result)
    await MessageUtils.build_message(res).send(reply_to=True)


diuse_farm.shortcut(
    "农场下阶段(.*?)",
    command="我的农场",
    arguments=["admin-up"],
    prefix=True,
)


@diuse_farm.assign("admin-up")
async def _(session: Uninfo, num: Query[int] = AlconnaQuery("num", 0)):
    uid = str(session.user.id)

    if not await g_pToolManager.isRegisteredByUid(uid):
        return

    await g_pDBService.userSoil.nextPhase(uid, num.result)
