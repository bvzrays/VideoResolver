from __future__ import annotations

import asyncio
import json
from pathlib import Path

from PIL import Image

from gsuid_core.bot import Bot
from gsuid_core.help.utils import register_help
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.sv import SV

from .config import gsconfig
from .resolver import (
    ResolvedMedia,
    download_audio,
    extract_url,
    fetch_bilibili_comments,
    format_comment_text,
    platform_from_url,
    render_comments,
    resolve_special_page,
)
from .utils.resource.RESOURCE_PATH import DATA_PATH

sv_resolver = SV("视频链接解析", priority=3)
sv_control = SV("视频解析管理", pm=3)
sv_owner_control = SV("视频解析主人管理", pm=1)

_DISABLED_PATH = DATA_PATH / "disabled_scopes.json"
_COMMENTS_DISABLED_PATH = DATA_PATH / "comments_disabled_scopes.json"
_COMMENT_MODE_PATH = DATA_PATH / "comment_modes.json"
_ICON_PATH = Path(__file__).resolve().parents[1] / "ICON.png"


async def _load_json_list(path: Path) -> list[str]:
    if not path.is_file():
        return []
    value = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path.name} must contain a JSON list")
    return [item for item in value if isinstance(item, str)]


def _scope_id(ev: Event) -> str:
    return f"group:{ev.group_id}" if ev.group_id is not None else f"user:{ev.user_id}"


def _nickname() -> str:
    value = gsconfig.get_config("GlobalNickname").data
    if not isinstance(value, str):
        raise TypeError("GlobalNickname must be str")
    return value.strip()


def _platform_label(platform: str) -> str:
    labels = {
        "bilibili": "哔哩哔哩",
        "dy": "抖音",
        "tiktok": "TikTok",
        "ac": "AcFun",
        "twitter": "X",
        "xiaohongshu": "小红书",
        "youtube": "YouTube",
        "netease": "网易云音乐",
        "kugou": "酷狗音乐",
        "wb": "微博",
    }
    return labels[platform]


def _disabled_platforms() -> set[str]:
    raw = gsconfig.get_config("GlobalResolveController").data
    if not isinstance(raw, str):
        raise TypeError("GlobalResolveController must be str")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


async def _save_json(path: Path, value: list[str] | dict[str, str]) -> None:
    await asyncio.to_thread(path.write_text, json.dumps(value, ensure_ascii=False, indent=2), "utf-8")


async def _remove_path(path: Path) -> None:
    await asyncio.to_thread(path.unlink, missing_ok=True)


async def _send_media(bot: Bot, ev: Event, media: ResolvedMedia) -> None:
    nickname = _nickname()
    prefix = f"{nickname} " if nickname else ""
    label = _platform_label(media.platform)
    details = f"{prefix}识别：{label}\n标题：{media.title}"
    if media.description:
        details += f"\n简介：{media.description}"
    if media.extra_text:
        details += f"\n{media.extra_text}"
    await bot.send(details)
    if media.kind == "video" and media.media_url:
        await bot.send(MessageSegment.image(media.media_url))
    if media.kind == "video" and media.media_path is not None:
        try:
            file_size = (await asyncio.to_thread(media.media_path.stat)).st_size
            if file_size > 100 * 1024 * 1024:
                await bot.send(MessageSegment.file(media.media_path, media.media_path.name))
            else:
                await bot.send(MessageSegment.video(media.media_path))
        finally:
            await _remove_path(media.media_path)
    elif media.kind == "image":
        await bot.send(MessageSegment.node([MessageSegment.image(url) for url in media.image_urls]))
    elif media.kind == "audio" and media.media_url is not None:
        if media.image_urls:
            await bot.send(MessageSegment.node([MessageSegment.image(url) for url in media.image_urls]))
        audio_path = await download_audio(media.media_url)
        try:
            await bot.send(MessageSegment.record(audio_path))
            await bot.send(MessageSegment.file(audio_path, f"{media.title}.mp3"))
        finally:
            await _remove_path(audio_path)
    elif media.kind == "file" and media.media_path is not None:
        try:
            await bot.send(MessageSegment.file(media.media_path, media.file_name or media.media_path.name))
        finally:
            await _remove_path(media.media_path)

    if media.ai_summary:
        await bot.send(MessageSegment.node([MessageSegment.text(f"B站 AI总结\n{media.ai_summary}")]))


async def _send_comments(bot: Bot, ev: Event, media: ResolvedMedia) -> None:
    if _scope_id(ev) in await _load_json_list(_COMMENTS_DISABLED_PATH):
        return
    comments = await fetch_bilibili_comments(media)
    if not comments:
        return
    raw_modes = (
        json.loads(await asyncio.to_thread(_COMMENT_MODE_PATH.read_text, encoding="utf-8"))
        if _COMMENT_MODE_PATH.is_file()
        else {}
    )
    modes = raw_modes if isinstance(raw_modes, dict) else {}
    configured_mode = gsconfig.get_config("CommentMode").data
    if not isinstance(configured_mode, str):
        raise TypeError("CommentMode must be str")
    mode = modes.get(_scope_id(ev), configured_mode)
    if not isinstance(mode, str):
        mode = configured_mode
    if mode == "image":
        try:
            await bot.send(MessageSegment.image(await render_comments(media, comments)))
            return
        except Exception as error:
            logger.warning(f"VideoResolver comment image fallback: {error}")
    text = format_comment_text(comments)
    await bot.send(MessageSegment.node([MessageSegment.text(text)]))


async def _handle_link(bot: Bot, ev: Event) -> None:
    url = extract_url(ev.raw_text)
    if url is None and len(ev.raw_text.strip()) == 12 and ev.raw_text.strip().startswith("BV"):
        url = f"https://www.bilibili.com/video/{ev.raw_text.strip()}"
    if url is None:
        return
    platform = platform_from_url(url)
    if platform is None or platform in _disabled_platforms() or _scope_id(ev) in await _load_json_list(_DISABLED_PATH):
        return
    try:
        media = await resolve_special_page(url, platform)
        await _send_media(bot, ev, media)
        if media.kind == "video" or (media.platform == "dy" and media.kind == "image"):
            await _send_comments(bot, ev, media)
    except Exception as error:
        logger.warning(f"VideoResolver {platform} resolve failed: {error}")
        await bot.send(f"❌ {_platform_label(platform)}解析失败：{error}")


@sv_resolver.on_regex(
    r"https?://(?:[^\s/]+\.)?(?:bilibili\.com|b23\.tv|bili2233\.cn|douyin\.com|v\.douyin\.com|"
    r"iesdouyin\.com|tiktok\.com|vt\.tiktok\.com|vm\.tiktok\.com|acfun\.cn|x\.com|twitter\.com|"
    r"xiaohongshu\.com|xhslink\.com|youtube\.com|youtu\.be|music\.163\.com|163cn\.tv|kugou\.com|"
    r"weibo\.com|m\.weibo\.cn)[^\s<>]+|\bBV[0-9A-Za-z]{10}\b",
    prefix=False,
    block=True,
)
async def resolve_shared_link(bot: Bot, ev: Event) -> None:
    await _handle_link(bot, ev)


@sv_control.on_fullmatch(("开启解析", "打开解析"))
async def enable_resolve(bot: Bot, ev: Event) -> None:
    disabled = await _load_json_list(_DISABLED_PATH)
    scope = _scope_id(ev)
    if scope in disabled:
        disabled.remove(scope)
        await _save_json(_DISABLED_PATH, disabled)
    await bot.send("✅ 当前会话已开启视频解析")


@sv_control.on_fullmatch(("关闭解析", "停用解析"))
async def disable_resolve(bot: Bot, ev: Event) -> None:
    disabled = await _load_json_list(_DISABLED_PATH)
    scope = _scope_id(ev)
    if scope not in disabled:
        disabled.append(scope)
        await _save_json(_DISABLED_PATH, disabled)
    await bot.send("✅ 当前会话已关闭视频解析")


@sv_owner_control.on_fullmatch("查看关闭解析")
async def list_disabled_resolve(bot: Bot, ev: Event) -> None:
    disabled = await _load_json_list(_DISABLED_PATH)
    await bot.send("当前关闭解析的会话：\n" + ("\n".join(disabled) if disabled else "无"))


@sv_control.on_fullmatch("开启评论")
async def enable_comments(bot: Bot, ev: Event) -> None:
    disabled = await _load_json_list(_COMMENTS_DISABLED_PATH)
    scope = _scope_id(ev)
    if scope in disabled:
        disabled.remove(scope)
        await _save_json(_COMMENTS_DISABLED_PATH, disabled)
    await bot.send("✅ 当前会话已开启评论区解析")


@sv_control.on_fullmatch("关闭评论")
async def disable_comments(bot: Bot, ev: Event) -> None:
    disabled = await _load_json_list(_COMMENTS_DISABLED_PATH)
    scope = _scope_id(ev)
    if scope not in disabled:
        disabled.append(scope)
        await _save_json(_COMMENTS_DISABLED_PATH, disabled)
    await bot.send("✅ 当前会话已关闭评论区解析")


@sv_control.on_fullmatch("切换评论模式")
async def switch_comment_mode(bot: Bot, ev: Event) -> None:
    raw_modes = (
        json.loads(await asyncio.to_thread(_COMMENT_MODE_PATH.read_text, encoding="utf-8"))
        if _COMMENT_MODE_PATH.is_file()
        else {}
    )
    if not isinstance(raw_modes, dict):
        raise ValueError("comment mode data is invalid")
    modes: dict[str, str] = {
        key: value for key, value in raw_modes.items() if isinstance(key, str) and isinstance(value, str)
    }
    scope = _scope_id(ev)
    current = modes.get(scope, "image")
    if not isinstance(current, str):
        current = "image"
    modes[scope] = "text" if current == "image" else "image"
    await _save_json(_COMMENT_MODE_PATH, modes)
    await bot.send(f"✅ 当前会话评论模式：{modes[scope]}")


@sv_owner_control.on_fullmatch("重载评论模板")
async def reload_comment_template(bot: Bot, ev: Event) -> None:
    await bot.send("✅ VideoResolver 评论模板使用内置模板，无需手动重载")


register_help(
    "VideoResolver",
    "vr帮助",
    Image.open(_ICON_PATH),
)


@sv_resolver.on_fullmatch("帮助")
async def video_resolver_help(bot: Bot, ev: Event) -> None:
    await bot.send(
        "VideoResolver 帮助\n"
        "直接分享支持平台链接即可解析。\n"
        "vr开启解析 / vr关闭解析\n"
        "vr开启评论 / vr关闭评论\n"
        "vr切换评论模式\n"
        "支持：哔哩哔哩、抖音、TikTok、AcFun、X、微博、小红书、YouTube、网易云音乐、酷狗音乐"
    )
