# VideoResolver

<p align="center">
  <a href="https://github.com/bvzrays/VideoResolver"><img src="./ICON.png" width="256" height="256" alt="VideoResolver"></a>
</p>
<h1 align="center">VideoResolver 1.2.35</h1>
<h4 align="center">🎬 面向 GsCore / 早柚核心的视频、图文与音乐分享解析插件 🎬</h4>
<div align="center">
  <a href="https://docs.sayu-bot.com/" target="_blank">GsCore 文档</a> &nbsp; · &nbsp;
  <a href="https://docs.sayu-bot.com/CodePlugins" target="_blank">插件开发指南</a> &nbsp; · &nbsp;
  <a href="https://github.com/zhiyu1998/nonebot-plugin-resolver" target="_blank">原始项目</a>
</div>

## 丨安装提醒

> [!IMPORTANT]
> 本插件是 [GsCore / 早柚核心](https://github.com/Genshin-bots/gsuid_core) 插件，链接识别、平台解析、下载、信息卡和评论渲染均在 GsCore 进程内完成。
>
> AstrBot、NoneBot、Koishi 等平台只需通过对应的 GsCore 适配器收发消息，换用其他适配器时无需修改插件。插件配置和运行数据只写入 `data/VideoResolver/`，不与其他插件共享。

## 丨安装方式

### WebConsole 安装

1. 打开 GsCore WebConsole 的插件商店。
2. 选择“通过 URL 安装”并填写：

   ```text
   https://github.com/bvzrays/VideoResolver
   ```

3. 确认核心配置中的“自动安装插件依赖”已开启。
4. 安装完成后重载插件或重启 GsCore。

### 手动安装

在 GsCore 仓库根目录执行：

```sh
cd gsuid_core/plugins
git clone https://github.com/bvzrays/VideoResolver.git VideoResolver
cd ../..
uv run core
```

若 GsCore 正在运行，可先停止进程，再执行最后一条启动命令。

## 丨功能

<details><summary><b>多平台分享解析</b></summary><p>

- 自动识别常见网页链接、短链接和 B 站 BV 号，无需额外指令前缀。
- 支持视频、图集、动态、笔记和音乐分享，按平台接口或 `yt-dlp` 获取媒体。
- 每个平台均可独立启停；国内平台默认开启，TikTok、X 和 YouTube 默认关闭。

</p></details>

<details><summary><b>信息卡与媒体发送</b></summary><p>

- 可按配置发送统一解析图，展示平台、作者、发布时间、标题、简介、封面或图集预览。
- 视频优先选择适合聊天平台播放的 H.264/AAC 格式，并限制为最高 720p。
- 图集以字节形式下载并发送；合并转发不可用时自动拆分，每条最多发送 9 张图片。

</p></details>

<details><summary><b>热门评论</b></summary><p>

- 支持哔哩哔哩和抖音热门评论，可按会话单独开启或关闭。
- 支持 HTML 图片和文字合并转发两种发送模式；图片模式每页最多渲染 5 条评论。
- 多页评论优先放入一条合并转发消息，评论接口异常只记录调试日志，不影响主媒体解析。

</p></details>

<details><summary><b>平台增强能力</b></summary><p>

- 哔哩哔哩支持动态、专栏、直播、收藏夹、分 P 信息和接口可用时的 AI 总结。
- 支持 Cookie、网络代理、视频时长上限、全局平台禁用和会话级解析控制。
- Cookie、下载文件、评论模板和会话状态均保存在插件独立运行目录。

</p></details>

## 丨支持平台

| 平台 | 默认状态 | 支持内容 |
|---|---|---|
| 哔哩哔哩 | 开启 | 视频、短链、BV 号、动态/图文、专栏、直播、收藏夹、热门评论、AI 总结 |
| 抖音 | 开启 | 视频、短链、图集、精选页、热门评论 |
| AcFun | 开启 | 视频及站内特殊页面 |
| 微博 | 开启 | 图片和视频动态 |
| 小红书 | 开启 | 视频和图文笔记 |
| 网易云音乐 | 开启 | 歌曲分享和短链接 |
| 酷狗音乐 | 开启 | 歌曲分享 |
| TikTok | 关闭 | 视频分享 |
| X / Twitter | 关闭 | 单图、多图、视频和 GIF |
| YouTube | 关闭 | 视频分享 |

平台接口可能受 Cookie、地区、版权和站点风控影响。默认关闭的平台可在 GsCore WebConsole 的 VideoResolver 配置中单独开启。

## 丨指令

插件使用 `vr` 作为管理指令前缀。分享支持平台链接时无需添加前缀；更新别名沿用 GsCore 的 `core` 前缀。

| 指令 | 权限 | 说明 |
|---|---|---|
| `vr帮助` | 所有人 | 查看插件帮助和支持平台 |
| `vr开启解析` | 群管理员 | 开启当前会话的视频解析 |
| `vr关闭解析` | 群管理员 | 关闭当前会话的视频解析 |
| `vr开启评论` | 群管理员 | 开启当前会话的评论区解析 |
| `vr关闭评论` | 群管理员 | 关闭当前会话的评论区解析 |
| `vr切换评论模式` | 群管理员 | 在 `image` 图片和 `text` 文字合并转发间切换 |
| `vr查看关闭解析` | 主人 | 查看已关闭解析的会话 |
| `vr重载评论模板` | 主人 | 从运行目录重新加载评论模板 |
| `core更新视频解析` | 主人 | 更新 VideoResolver，等效于 `core更新VideoResolver` |

## 丨配置

在 GsCore WebConsole 的 VideoResolver 配置页修改。配置项按基础设置、平台开关、平台登录态和评论区分组显示。

| 配置项 | 默认值 | 说明 |
|---|---|---|
| 解析前缀名 | 空 | 解析结果前显示的自定义名称 |
| 发送解析图 | 开启 | 发送包含作者、标题和媒体预览的信息卡；关闭不影响媒体、评论和总结 |
| 网络代理 | `http://127.0.0.1:7890` | 抖音、TikTok、YouTube 等服务使用的代理；直连时清空 |
| 海外服务器 | 关闭 | 开启后 TikTok 和 YouTube 不使用上述代理 |
| 视频最大时长 | `480` | 允许下载的视频最长秒数，最大可设为 `7200` |
| 全局禁用平台 | 空 | 以英文逗号分隔平台代号，优先于独立平台开关 |
| 各平台开关 | 国内开启、海外关闭 | 可分别控制十个平台的解析器 |
| B站 SESSDATA | 空 | B 站登录态、热门评论及需要登录的接口 |
| 抖音 Cookie | 空 | 抖音接口需要登录态时填写完整 Cookie |
| 小红书 Cookie | 空 | 小红书笔记解析通常需要填写完整 Cookie |
| 上传 YouTube Cookie | 空 | 在控制台上传 Netscape 格式 txt 文件，保存为 `data/VideoResolver/cookies/ytb_cookies.txt` |
| YouTube Cookie 自定义路径 | 空 | 高级选项；优先于控制台上传文件，可填写相对文件名或绝对路径 |
| 启用评论区 | 开启 | 解析完成后尝试获取支持平台的热门评论 |
| 评论发送模式 | `image` | `image` 为 HTML 图片，`text` 为文字合并转发 |
| 评论数量 | `20` | 每个平台最多读取的热门评论数，最大为 `50` |

### 如何获取 Cookie

Chrome 和 Edge 均可按以下方式获取：

1. 使用准备提供给机器人的账号登录目标网站。
2. 按 `F12` 打开开发者工具。
3. B站：打开“应用/Application → Cookie → `https://www.bilibili.com`”，找到 `SESSDATA`，只复制它的值，不要包含 `SESSDATA=`。
4. 抖音和小红书：打开“网络/Network”后刷新页面，选择任意发往当前网站的请求，在“请求标头/Request Headers”中找到 `Cookie`，复制冒号后的完整内容。
5. 将内容粘贴到 VideoResolver 对应的密钥输入框并保存配置；无需给内容额外添加引号。

原项目提供了[在线视频教程](https://github.com/user-attachments/assets/7ead6d62-a36c-4e8d-bb5d-6666749dfb26)。不要使用控制台中的 `document.cookie` 代替上述步骤，它通常读取不到标记为 `HttpOnly` 的关键 Cookie。

YouTube 使用的是 Netscape 格式 Cookie 文件，不是网页请求头中的整段文本。导出的文件首行通常为 `# Netscape HTTP Cookie File`；在控制台通过“上传 YouTube Cookie”提交即可，也可以手动放到 `data/VideoResolver/cookies/ytb_cookies.txt`。

> [!WARNING]
> Cookie、SESSDATA 和 Cookie 文件属于敏感登录凭据，只应保存在本机运行目录或 GsCore 配置中。请勿将其写入源码、公开日志或提交到 Git。

## 丨运行依赖

WebConsole 安装时会按照 `pyproject.toml` 自动安装 Python 依赖，系统还需提供以下程序：

- **FFmpeg（必需）**：用于音视频合并、格式转换和聊天平台兼容处理。
- **Node.js（按需）**：仅抖音备用接口执行签名脚本时需要。

Ubuntu / Debian：

```sh
sudo apt-get update
sudo apt-get install ffmpeg
```

Windows 请安装 FFmpeg 并加入 `PATH`，确认 `ffmpeg -version` 可正常返回。需要抖音备用签名时，再确认 `node --version` 可用。

## 丨模板与数据目录

插件内置模板位于 `VideoResolver/templates/`：

- `media-card.html`：平台信息卡模板。
- `bilibili-comment.html`：哔哩哔哩评论图片模板。
- `douyin-comment.html`：抖音评论图片模板。

首次使用评论图片时，评论模板会复制到 `data/VideoResolver/templates/`。修改运行目录中的模板后，发送 `vr重载评论模板` 即可应用；模板缺失或损坏时会自动恢复内置版本。

运行数据全部位于 GsCore 的 `data/VideoResolver/`：

- `downloads/`：临时下载的媒体文件。
- `cookies/`：YouTube 等平台使用的 Cookie 文件。
- `templates/`：可自定义的运行时评论模板。
- `data/disabled_scopes.json`：关闭解析的会话列表。
- `data/comments_disabled_scopes.json`：关闭评论的会话列表。
- `data/comment_modes.json`：每个会话的评论发送模式。

这些文件不应被 Git 跟踪，也不会写入其他插件目录。

## 丨使用说明

- 直接发送支持平台的网页链接、短链接或 B 站 BV 号即可触发解析。
- QQ 小程序卡片只有在当前适配器把真实 URL 转交给 GsCore 时才能识别；若消息中只有卡片标题或适配器未转发链接，请复制对应网页链接发送。
- 视频能在本地打开但无法在聊天窗口播放时，请先确认 FFmpeg 可用，并检查当前聊天平台或适配器的文件大小与编码限制。
- 平台规则发生变化时，优先更新 VideoResolver 及其 Python 依赖；单次链接解析失败不会阻塞 GsCore 主进程。

## 丨感谢

- [zhiyu1998](https://github.com/zhiyu1998) — 原始项目 [nonebot-plugin-resolver](https://github.com/zhiyu1998/nonebot-plugin-resolver) 的作者与维护者。本移植保留原项目的功能设计、许可证和原作者署名。
- [bvzrays](https://github.com/bvzrays) — VideoResolver 的 GsCore 移植与当前维护。
- [MeowAndy](https://github.com/MeowAndy) — 对本次完整 GsCore 移植的赞助支持。
- [GsCore / 早柚核心](https://github.com/Genshin-bots/gsuid_core) — 插件框架、适配器抽象、配置中心与消息发送能力。

## 丨许可证

本项目使用 [木兰宽松许可证第 2 版（MulanPSL2）](./LICENSE)。原始代码版权归原作者及贡献者所有；GsCore 移植部分由本仓库维护者提供。
