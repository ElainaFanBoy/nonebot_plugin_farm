<p align="center">
<img  alt="IRONY's Farm" src="https://gcore.jsdelivr.net/gh/ElainaFanBoy/picx-images-hosting@master/20230720/icon.png" width="200" height="200" alt="IRONY""/>
</p>

<h1 align="center">
IRONY's Farm
</h1>

<p align="center">
 🥬 IRONY的开心农场 ⛏
</p>

<p align="center">
<a href="https://github.com/ElainaFanBoy/nonebot_plugin_farm/blob/main/LICENSE" target="__blank"><img alt="GPL-3.0" src="https://img.shields.io/github/license/ElainaFanBoy/nonebot_plugin_farm?style=for-the-badge&logo=github&color=FE7D37"></a>
<a href="http://wpa.qq.com/msgrd?v=3&uin=712111161&site=qq&menu=yes"><img src="https://img.shields.io/badge/Nanako-712111161-red?style=for-the-badge&logo=tencentqq&color=FFADBC"></a>
<a href="https://qm.qq.com/q/dSUYVPcChq"><img src="https://img.shields.io/badge/重生之祭弃人打赢复活赛-973481508-red?style=for-the-badge&logo=tencentqq&color=3A8891"></a>

## 📖 介绍

IRONY的特供版农场，魔改自[真寻农场](https://github.com/Shu-Ying/nonebot_plugin_farm)

## 💿 安装

<details>
<summary>克隆至本地安装</summary>

    git clone https://github.com/ElainaFanBoy/nonebot_plugin_farm.git

</details>

## ⚙️ 配置

在 nonebot2 项目的`.env`文件中添加下表中的必填配置

| 配置项 | 必填 | 默认值 | 说明 |
| :----: | :--: | :----: | :--: |
|   farm_draw_quality   |  否  |   original   |  绘制农场清晰度，分为："low", "medium", "hight", "original"  |

## 🎉 使用

### 指令表

|  指令  |  权限  | 需要@ | 说明 |
| :----: | :----: | :---: | :--: |
| @IRONY 开通农场 | 所有人 | 是 | 首次开通农场 |
| 我的农场 | 所有人 | 否 | 展示你的农场 |
| 农场详述 | 所有人 | 否 | 农场详细信息 |
| 农场签到 | 所有人 | 否 | 农场每日签到 |
| 更改农场名 [新的农场名] | 所有人 | 否 |农场名称无法存储特殊字符 |
| 种子商店 [筛选关键字] [页数] or [页数] | 所有人 | 否 | 查看种子商店，当第一个参数为非整数时，会默认进入筛选状态。页数不填默认为1 |
| 购买种子 [种子名称] [数量] | 所有人 | 否 | 购买种子，数量不填默认为1 |
| 播种 [种子名称] [数量] | 所有人 | 否 | 播种种子，数量不填默认将最大可能播种 |
| 收获 | 所有人 | 否 | 收获成熟作物 |
| 铲除 | 所有人 | 否 | 铲除荒废作物 |
| 偷菜 @群友 | 所有人 | 否 | 偷别人的菜，每人每天只能偷5次 |
| 开垦 | 所有人 | 否 | 开垦新的土地 |
| 土地升级 [地块ID] | 所有人 | 否 | 将土地升级，带来收益提升，如果土地升级时，土地有播种作物，那么将直接成熟 |
| 我的种子 | 所有人 | 否 | 查看仓库种子 |  
| 我的作物 | 所有人 | 否 | 查看你的作物 |
| 出售作物 [作物名称] [数量] | 所有人 | 否 | 从仓库里向系统售卖作物，不填写作物名将售卖仓库种全部作物，填作物名不填数量将指定作物全部出售 |

### 效果图

<div align="left">
  
  <img src="https://raw.githubusercontent.com/ElainaFanBoy/nonebot_plugin_farm/refs/heads/main/nonebot_plugin_farm/resource/sample.png" width="800"/>

</div>