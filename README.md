# VideoResolver

面向 GsCore / 早柚核心的链接分享解析插件，项目地址：[bvzrays/VideoResolver](https://github.com/bvzrays/VideoResolver)，移植自
[nonebot-plugin-resolver](https://github.com/zhiyu1998/nonebot-plugin-resolver)。
插件不依赖 NoneBot 或 AstrBot，安装在 `gsuid_core/plugins/VideoResolver/` 后由 GsCore 自动加载。

本插件是独立的 GsCore 项目，与其他插件的代码、配置和运行数据互不共享；运行数据只写入
`data/VideoResolver/`，不会写入群分析插件目录。

## 支持平台

- 哔哩哔哩：视频、短链、BV 号，以及可选的热门评论。
- 抖音、TikTok：视频、图集和可选的抖音热门评论；平台接口受 Cookie、地区和站点风控影响。
- AcFun、X/Twitter、微博：视频或媒体链接，使用 `yt-dlp` 或站点接口解析。
- 小红书：笔记链接；需要在配置中填写 Cookie。
- YouTube：视频链接，支持代理和 Netscape Cookie 文件。
- 网易云音乐、酷狗音乐：歌曲链接，发送音频并同时发送文件。

## 安装依赖

GsCore WebConsole 安装插件时会自动安装 `pyproject.toml` 中的依赖。视频合并需要系统安装
FFmpeg 并加入 PATH；抖音备用接口签名还需要 Node.js（`PyExecJS` 会调用系统 Node）：

```sh
# Ubuntu / Debian
sudo apt-get install ffmpeg
```

Windows 请安装 FFmpeg，并确认在 PowerShell 中执行 `ffmpeg -version` 能正常返回。
如需抖音备用签名，请同时确认 `node --version` 可用。

## 指令

插件命令前缀为 `vr`，例如 `vr帮助`。分享支持平台链接时，解析器默认无需前缀即可触发。

| 指令 | 权限 | 作用 |
| --- | --- | --- |
| `vr开启解析` | 群管理员 | 开启当前群解析 |
| `vr关闭解析` | 群管理员 | 关闭当前群解析 |
| `vr开启评论` | 群管理员 | 开启当前群评论区处理 |
| `vr关闭评论` | 群管理员 | 关闭当前群评论区处理 |
| `vr切换评论模式` | 群管理员 | 在 HTML 图片和文字合并转发间切换 |
| `vr查看关闭解析` | 主人 | 查看已关闭解析的会话 |
| `vr重载评论模板` | 主人 | 确认使用内置评论模板 |

## 配置

在 GsCore WebConsole 的插件配置中修改，配置项已按基础、平台和评论区分栏显示：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| 解析前缀名 | 空 | 解析结果前的自定义名称 |
| 网络代理 | `http://127.0.0.1:7890` | 抖音、TikTok、YouTube 等服务的代理地址；直连请清空 |
| 海外服务器 | 关闭 | 开启后不为海外平台使用配置的代理 |
| 视频最大时长 | `480` | 下载视频的最大秒数 |
| 全局禁用平台 | 空 | 逗号分隔的平台代号 |
| B站 SESSDATA | 空 | B站登录态、评论和需要登录的接口 |
| 抖音 Cookie | 空 | 抖音接口登录态 |
| 小红书 Cookie | 空 | 小红书笔记登录态 |
| YouTube Cookie 文件 | 空 | 默认读取 `data/VideoResolver/cookies/ytb_cookies.txt` |
| 启用评论区 | 开启 | 是否尝试获取支持平台的热门评论 |
| 评论发送模式 | `image` | `image` 图片或 `text` 合并转发 |
| 评论数量 | `20` | 单次最多读取数量 |

Cookie 和 Cookie 文件只保存在 GsCore 的 `data/VideoResolver/` 运行目录，不要提交到 Git。

## 说明

解析器使用 `yt-dlp` 统一处理视频下载，站点规则变化时请先更新插件依赖。受平台登录态、
地区限制、视频版权和接口可用性影响，某些链接可能无法解析；解析失败只影响当前消息，
不会阻塞 GsCore 主进程。

## 来源

原项目：[zhiyu1998/nonebot-plugin-resolver](https://github.com/zhiyu1998/nonebot-plugin-resolver)
