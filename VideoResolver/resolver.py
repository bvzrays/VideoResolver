from __future__ import annotations

import asyncio
import base64
import html
import json
import random
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, quote, urlencode, urlparse

import aiofiles
import httpx

from gsuid_core.logger import logger
from gsuid_core.pool import to_thread
from gsuid_core.utils.html_render import render_html_to_bytes

from .config import gsconfig
from .utils.resource.RESOURCE_PATH import ASSET_PATH, COOKIE_PATH, DOWNLOAD_PATH

MediaKind = Literal["video", "image", "audio", "file"]

_ACFUN_HEADERS = {
    "Referer": "https://www.acfun.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36"
    ),
}


@dataclass(frozen=True)
class ResolvedMedia:
    platform: str
    title: str
    kind: MediaKind
    source_url: str
    media_url: str | None = None
    media_path: Path | None = None
    image_urls: tuple[str, ...] = ()
    duration: int = 0
    aid: int | None = None
    bvid: str | None = None
    description: str = ""
    extra_text: str = ""
    file_name: str | None = None
    cid: int | None = None
    up_mid: int | None = None
    page_index: int = 0
    ai_summary: str = ""


@dataclass(frozen=True)
class ResolvedComment:
    username: str
    text: str
    like: int
    avatar: str | None = None
    image: str | None = None
    images: tuple[str, ...] = ()
    sticker: str | None = None
    location: str = ""
    time: str = ""
    level: int = 0
    is_author: bool = False
    replies: tuple["ResolvedComment", ...] = ()
    emojis: tuple[str, ...] = ()
    emote_map: tuple[tuple[str, str], ...] = ()


def _config_str(name: str) -> str:
    value = gsconfig.get_config(name).data
    if isinstance(value, str):
        return value.strip()
    raise TypeError(f"VideoResolver config {name} must be str")


def _config_bool(name: str) -> bool:
    value = gsconfig.get_config(name).data
    if isinstance(value, bool):
        return value
    raise TypeError(f"VideoResolver config {name} must be bool")


def _config_int(name: str) -> int:
    value = gsconfig.get_config(name).data
    if isinstance(value, int):
        return value
    raise TypeError(f"VideoResolver config {name} must be int")


def configured_proxy() -> str | None:
    proxy = _config_str("ResolverProxy")
    if not proxy or _config_bool("IsOversea"):
        return None
    return proxy


def extract_url(raw_text: str) -> str | None:
    normalized = raw_text.replace("\\/", "/").replace("\\u002F", "/").replace("&amp;", "&")
    match = re.search(r"https?://[^\s<>]+", normalized)
    if match is None:
        return None
    return match.group(0).rstrip("，。！？；,.;!?)】》")


def platform_from_url(url: str) -> str | None:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    platform_hosts = {
        "bilibili.com": "bilibili",
        "b23.tv": "bilibili",
        "bili2233.cn": "bilibili",
        "douyin.com": "dy",
        "v.douyin.com": "dy",
        "iesdouyin.com": "dy",
        "tiktok.com": "tiktok",
        "vt.tiktok.com": "tiktok",
        "vm.tiktok.com": "tiktok",
        "acfun.cn": "ac",
        "x.com": "twitter",
        "twitter.com": "twitter",
        "xiaohongshu.com": "xiaohongshu",
        "xhslink.com": "xiaohongshu",
        "youtube.com": "youtube",
        "youtu.be": "youtube",
        "music.163.com": "netease",
        "163cn.tv": "netease",
        "kugou.com": "kugou",
        "weibo.com": "wb",
        "m.weibo.cn": "wb",
    }
    for domain, platform in platform_hosts.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    return None


def _json_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: item for key, item in value.items()}
    return None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    return None


async def _fetch_bilibili_view(url: str) -> dict[str, object] | None:
    """读取 B 站视频详情，为分P、统计和 AI 总结提供统一元数据。"""
    parsed = urlparse(url)
    bvid_match = re.search(r"(?:^|/)((?:BV|bv)[0-9A-Za-z]{10})(?:/|$)", parsed.path)
    aid_match = re.search(r"(?:^|/)av(\d+)(?:/|$)", parsed.path, re.IGNORECASE)
    params: dict[str, str] = {}
    if bvid_match is not None:
        params["bvid"] = bvid_match.group(1).upper()
    elif aid_match is not None:
        params["aid"] = aid_match.group(1)
    else:
        return None
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
    sessdata = _config_str("BiliSessdata")
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, proxy=configured_proxy()) as client:
            response = await client.get("https://api.bilibili.com/x/web-interface/view", params=params)
        response.raise_for_status()
        payload = _json_object(json.loads(response.text))
        data = _json_object(payload["data"]) if payload is not None and "data" in payload else None
        return data
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.debug("VideoResolver B站详情读取失败：%s", exc)
        return None


def _bilibili_page_index(url: str, pages: object) -> tuple[int, dict[str, object] | None]:
    if not isinstance(pages, list) or not pages:
        return 0, None
    parsed = urlparse(url)
    raw_page = parsed.query
    page_match = re.search(r"(?:^|&)p=(\d+)(?:&|$)", raw_page)
    requested = int(page_match.group(1)) - 1 if page_match is not None else 0
    page_index = max(0, min(requested, len(pages) - 1))
    page = _json_object(pages[page_index])
    return page_index, page


def _format_bilibili_stats(data: dict[str, object]) -> str:
    stat = _json_object(data["stat"]) if "stat" in data else None
    if stat is None:
        return ""
    labels = (
        ("like", "点赞"),
        ("coin", "硬币"),
        ("favorite", "收藏"),
        ("share", "分享"),
        ("view", "总播放量"),
        ("danmaku", "弹幕数量"),
        ("reply", "评论"),
    )
    values: list[str] = []
    for key, label in labels:
        if key not in stat:
            continue
        value = stat[key]
        number = _number(value)
        if number is not None and number > 10000:
            values.append(f"{label}: {number / 10000:.1f}万")
        else:
            values.append(f"{label}: {value}")
    return " | ".join(values)


async def _fetch_bilibili_online(data: dict[str, object], cid: int | None, bvid: str | None) -> str:
    if cid is None or bvid is None:
        return ""
    aid = _number(data["aid"]) if "aid" in data else None
    params = {"bvid": bvid, "cid": str(cid)}
    if aid is not None:
        params["aid"] = str(aid)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://www.bilibili.com/video/{bvid}"}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, proxy=configured_proxy()) as client:
            response = await client.get("https://api.bilibili.com/x/player/online/total", params=params)
        response.raise_for_status()
        payload = _json_object(json.loads(response.text))
        online = _json_object(payload["data"]) if payload is not None and "data" in payload else None
        if online is None:
            return ""
        total = online["total"] if "total" in online else None
        count = online["count"] if "count" in online else None
        if total is None or count is None:
            return ""
        return f"🏄‍♂️ 总共 {total} 人在观看，{count} 人在网页端观看"
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.debug("VideoResolver B站在线人数读取失败：%s", exc)
        return ""


async def _fetch_bilibili_ai_summary(media: ResolvedMedia) -> str:
    if not media.bvid or media.cid is None or not _config_str("BiliSessdata"):
        return ""
    try:
        from bilibili_api import Credential
        from bilibili_api.video import Video

        credential = Credential(sessdata=_config_str("BiliSessdata"))
        video_client = Video(media.bvid, credential=credential)
        raw = await video_client.get_ai_conclusion(cid=media.cid, up_mid=media.up_mid)
        payload = _json_object(raw)
        model_result_payload = payload["model_result"] if payload is not None and "model_result" in payload else None
        model_result = _json_object(model_result_payload)
        summary = _string(model_result["summary"]) if model_result is not None and "summary" in model_result else None
        return summary or ""
    except (ImportError, TypeError, ValueError, RuntimeError) as exc:
        logger.debug("VideoResolver B站 AI总结读取失败：%s", exc)
        return ""


@to_thread
def _generate_a_bogus(query: str, user_agent: str) -> str:
    import execjs

    script = (ASSET_PATH / "a-bogus.js").read_text(encoding="utf-8")
    return str(execjs.compile(script).call("generate_a_bogus", query, user_agent))


@to_thread
def _extract_info(url: str, platform: str, download: bool) -> object:
    import yt_dlp

    options = yt_dlp.YoutubeDL().params
    options["quiet"] = True
    options["no_warnings"] = True
    options["noplaylist"] = True
    options["restrictfilenames"] = True
    options["outtmpl"] = str(DOWNLOAD_PATH / f"{int(time.time() * 1000)}_%(id)s.%(ext)s")
    options["merge_output_format"] = "mp4"
    proxy = configured_proxy()
    if proxy is not None:
        options["proxy"] = proxy
    cookie_file = _config_str("YoutubeCookieFile") if platform == "youtube" else ""
    if platform == "youtube":
        cookie_path = Path(cookie_file) if cookie_file else COOKIE_PATH / "ytb_cookies.txt"
        if not cookie_path.is_absolute():
            cookie_path = COOKIE_PATH / cookie_path
        if cookie_path.is_file():
            options["cookiefile"] = str(cookie_path)
        options["format"] = "bv*[height<=720]+ba/b[height<=720]/b"
    if platform == "bilibili":
        sessdata = _config_str("BiliSessdata")
        if sessdata:
            options["http_headers"] = {"Cookie": f"SESSDATA={sessdata}"}
    elif platform == "dy":
        cookie = _config_str("DouyinCookie")
        if cookie:
            options["http_headers"] = {"Cookie": cookie}
    elif platform == "ac":
        options["http_headers"] = _ACFUN_HEADERS.copy()
    elif platform == "xiaohongshu":
        cookie = _config_str("XhsCookie")
        if cookie:
            options["http_headers"] = {"Cookie": cookie}
    elif platform == "tiktok":
        options["http_headers"] = {"User-Agent": "facebookexternalhit/1.1"}
    with yt_dlp.YoutubeDL(options) as downloader:
        return downloader.extract_info(url, download=download)


def _first_entry(info: object) -> dict[str, object] | None:
    data = _json_object(info)
    if data is None:
        return None
    entries = data.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            item = _json_object(entry)
            if item is not None:
                return item
    return data


def _downloaded_file(info: dict[str, object]) -> Path | None:
    requested = info.get("requested_downloads")
    if isinstance(requested, list):
        for item in requested:
            item_data = _json_object(item)
            if item_data is not None:
                filepath = _string(item_data.get("filepath"))
                if filepath is not None and Path(filepath).is_file():
                    return Path(filepath)
    filepath = _string(info.get("filepath"))
    if filepath is not None and Path(filepath).is_file():
        return Path(filepath)
    video_id = _string(info.get("id"))
    if video_id is None:
        return None
    candidates = sorted(DOWNLOAD_PATH.glob(f"*_{video_id}.*"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


async def resolve_video(url: str, platform: str) -> ResolvedMedia:
    info = _first_entry(await _extract_info(url, platform, False))
    if info is None:
        raise ValueError("解析器未返回媒体信息")
    title = _string(info.get("title")) or "未命名视频"
    duration = _number(info.get("duration")) or 0
    maximum = _config_int("VideoDurationMaximum")
    if duration > maximum:
        raise ValueError(f"视频时长 {duration} 秒，超过管理员设置的最长时长 {maximum} 秒")
    await _extract_info(url, platform, True)
    file_path = _downloaded_file(info)
    if file_path is None:
        raise ValueError("视频下载完成后未找到本地文件")
    thumbnail = _string(info.get("thumbnail"))
    return ResolvedMedia(
        platform=platform,
        title=title,
        kind="video",
        source_url=url,
        media_path=file_path,
        media_url=thumbnail,
        duration=duration,
        bvid=_string(info.get("id")) if platform == "bilibili" else None,
    )


async def resolve_image_page(url: str, platform: str) -> ResolvedMedia:
    info = _first_entry(await _extract_info(url, platform, False))
    if info is None:
        raise ValueError("解析器未返回图集信息")
    title = _string(info.get("title")) or "未命名图集"
    thumbnails: list[str] = []
    for key in ("thumbnails", "thumbnail"):
        values = info.get(key)
        if isinstance(values, list):
            thumbnails.extend(item for item in values if isinstance(item, str))
        elif isinstance(values, str):
            thumbnails.append(values)
    if not thumbnails:
        raise ValueError("未找到可发送的图片")
    return ResolvedMedia(platform, title, "image", url, image_urls=tuple(dict.fromkeys(thumbnails)))


async def _resolve_special_music(url: str, platform: str) -> ResolvedMedia:
    source_url = url
    if platform == "netease" and "163cn.tv" in urlparse(url).netloc.lower():
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
            response = await client.get(url)
        url = str(response.url)
    match = re.search(r"(?:[?&]id=|/song/|/hash/)([A-Za-z0-9]+)", url)
    music_id = match.group(1) if match is not None else ""
    if platform == "kugou" and not music_id:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
            page = await client.get(url)
        title_match = re.search(r"<title>(.*?)_高音质在线试听", page.text, re.IGNORECASE | re.DOTALL)
        music_id = title_match.group(1).strip() if title_match is not None else ""
    if not music_id:
        raise ValueError("未能从音乐链接中找到歌曲标识")
    if platform == "netease":
        api_requests = (
            (
                "http://itapi.top/API/get_wyyid.php",
                {"id": music_id},
            ),
            (
                "https://api.bugpk.com/api/163_music",
                {"type": "json", "ids": music_id, "level": "hires"},
            ),
        )
    else:
        api_requests = (
            (
                "https://www.hhlqilongzhu.cn/api/dg_kugouSQ.php",
                {"msg": music_id, "n": "1", "type": "json"},
            ),
        )
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
        for api_url, params in api_requests:
            response = await client.get(api_url, params=params)
            if response.status_code >= 400:
                continue
            payload = _json_object(json.loads(response.text))
            if payload is None:
                continue
            data_value = payload.get("data")
            data = (
                _json_object(data_value)
                if not isinstance(data_value, list)
                else (_json_object(data_value[0]) if data_value else None)
            )
            data = data or payload
            media_url = next((_string(data.get(key)) for key in ("url", "music_url") if _string(data.get(key))), None)
            if media_url is None:
                continue
            title = _string(data.get("name")) or _string(data.get("title")) or f"歌曲_{music_id}"
            cover = _string(data.get("pic")) or _string(data.get("picurl")) or _string(data.get("cover"))
            singer = _string(data.get("singer")) or _string(data.get("ar_name"))
            if singer is None:
                singers = data.get("singers")
                if isinstance(singers, list):
                    singer_names: list[str] = []
                    for singer_data in singers:
                        if not isinstance(singer_data, dict):
                            continue
                        singer_name = singer_data.get("name")
                        if isinstance(singer_name, str) and singer_name:
                            singer_names.append(singer_name)
                    singer = " / ".join(singer_names) or None
            return ResolvedMedia(
                platform,
                title,
                "audio",
                source_url,
                media_url=media_url,
                image_urls=(cover,) if cover else (),
                extra_text=f"歌手：{singer}" if singer else "",
            )
    raise ValueError("音乐主备解析接口均未返回播放链接")


async def resolve_special_page(url: str, platform: str) -> ResolvedMedia:
    if platform in {"netease", "kugou"}:
        return await _resolve_special_music(url, platform)
    if platform == "dy":
        return await _resolve_douyin(url)
    if platform == "bilibili":
        return await _resolve_bilibili_page(url)
    if platform == "ac":
        return await _resolve_acfun(url)
    if platform == "twitter":
        return await _resolve_x(url)
    if platform == "wb":
        return await _resolve_weibo(url)
    if platform == "xiaohongshu":
        cookie = _config_str("XhsCookie")
        if not cookie:
            raise ValueError("小红书解析需要先在 VideoResolver 配置中填写 Cookie")
        return await _resolve_xiaohongshu(url, cookie)
    return await resolve_video(url, platform)


async def _resolve_bilibili_page(url: str) -> ResolvedMedia:
    final_url = url
    if any(host in urlparse(url).netloc.lower() for host in ("b23.tv", "bili2233.cn")):
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
            response = await client.get(url)
        final_url = str(response.url)
    parsed = urlparse(final_url)
    dynamic_match = re.search(r"/(?:opus/)?(\d+)(?:/|$)", parsed.path)
    if parsed.netloc.lower().startswith("t.") and dynamic_match is not None:
        return await _resolve_bilibili_dynamic(final_url, dynamic_match.group(1))
    if parsed.path.startswith("/opus/") and dynamic_match is not None:
        return await _resolve_bilibili_dynamic(final_url, dynamic_match.group(1))
    live_match = re.search(r"/live/(\d+)", parsed.path)
    if live_match is not None:
        return await _resolve_bilibili_live(final_url, live_match.group(1))
    article_match = re.search(r"/read/cv(\d+)", parsed.path)
    if article_match is not None:
        return await _resolve_bilibili_article(final_url, article_match.group(1))
    if "favlist" in parsed.path and "fid=" in parsed.query:
        favorite_id = re.search(r"(?:^|&)fid=(\d+)", parsed.query)
        if favorite_id is not None:
            return await _resolve_bilibili_favorite(final_url, favorite_id.group(1))
    view_data = await _fetch_bilibili_view(final_url)
    page_index, page_data = _bilibili_page_index(
        final_url,
        view_data["pages"] if view_data is not None and "pages" in view_data else [],
    )
    selected_duration = _number(page_data["duration"]) if page_data is not None and "duration" in page_data else None
    maximum_duration = _config_int("VideoDurationMaximum")
    if selected_duration is not None and selected_duration > maximum_duration:
        raise ValueError(f"视频时长 {selected_duration} 秒，超过管理员设置的最长时长 {maximum_duration} 秒")

    media = await resolve_video(final_url, "bilibili")
    if view_data is None:
        return media
    bvid = _string(view_data["bvid"]) if "bvid" in view_data else media.bvid
    cid = _number(page_data["cid"]) if page_data is not None and "cid" in page_data else None
    owner = _json_object(view_data["owner"]) if "owner" in view_data else None
    up_mid = _number(owner["mid"]) if owner is not None and "mid" in owner else None
    enriched = replace(
        media,
        aid=_number(view_data["aid"]) if "aid" in view_data else media.aid,
        bvid=bvid,
        cid=cid,
        up_mid=up_mid,
        page_index=page_index,
        duration=selected_duration if selected_duration is not None else media.duration,
        title=_string(view_data["title"]) if "title" in view_data else media.title,
        description=_string(view_data["desc"]) or "" if "desc" in view_data else media.description,
        media_url=_string(view_data["pic"]) or media.media_url if "pic" in view_data else media.media_url,
        extra_text=_format_bilibili_stats(view_data),
    )
    online_text = await _fetch_bilibili_online(view_data, cid, bvid)
    extra_text = " | ".join(value for value in (enriched.extra_text, online_text) if value)
    enriched = replace(enriched, extra_text=extra_text)
    ai_summary = await _fetch_bilibili_ai_summary(enriched)
    return replace(enriched, ai_summary=ai_summary)


async def _resolve_bilibili_live(url: str, room_id: str) -> ResolvedMedia:
    async with httpx.AsyncClient(timeout=15, proxy=configured_proxy()) as client:
        response = await client.get(f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}")
    payload = _json_object(json.loads(response.text))
    data = _json_object(payload.get("data")) if payload is not None else None
    if data is None:
        raise ValueError("B站直播间信息为空")
    title = _string(data.get("title")) or "B站直播间"
    covers = tuple(
        dict.fromkeys(
            cover
            for cover in (
                _string(data.get("user_cover")),
                _string(data.get("keyframe")),
                _string(data.get("cover")),
            )
            if cover is not None
        )
    )
    if not covers:
        raise ValueError("B站直播间没有封面")
    return ResolvedMedia("bilibili", title, "image", url, image_urls=covers)


async def _resolve_bilibili_article(url: str, article_id: str) -> ResolvedMedia:
    from bilibili_api import article as bilibili_article

    article_item = bilibili_article.Article(int(article_id))
    if article_item.is_note():
        article_item = article_item.turn_to_note()
    await article_item.fetch_content()
    title = f"B站专栏 {article_id}"
    markdown = article_item.markdown()
    if not markdown.strip():
        raise ValueError("B站专栏没有可下载的正文")
    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if title_match is not None:
        title = html.unescape(title_match.group(1).strip())
    text = markdown if markdown.endswith("\n") else f"{markdown}\n"
    path = DOWNLOAD_PATH / f"bilibili_article_{article_id}.md"
    await asyncio.to_thread(path.write_text, text, "utf-8")
    return ResolvedMedia("bilibili", title, "file", url, media_path=path, file_name=f"{article_id}.md")


async def _resolve_bilibili_favorite(url: str, favorite_id: str) -> ResolvedMedia:
    sessdata = _config_str("BiliSessdata")
    if not sessdata:
        raise ValueError("B站收藏夹解析需要先配置 SESSDATA")
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": f"SESSDATA={sessdata}"}
    async with httpx.AsyncClient(timeout=20, headers=headers, proxy=configured_proxy()) as client:
        response = await client.get(
            f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={favorite_id}&ps=10&pn=1"
        )
    payload = _json_object(json.loads(response.text))
    data = _json_object(payload.get("data")) if payload is not None else None
    medias = data.get("medias") if data is not None else None
    if not isinstance(medias, list):
        raise ValueError("B站收藏夹没有可用视频")
    images: list[str] = []
    details: list[str] = []
    for raw_media in medias:
        item = _json_object(raw_media)
        if item is None:
            continue
        cover = _string(item.get("cover"))
        if cover:
            images.append(cover)
        title = _string(item.get("title"))
        intro = _string(item.get("intro")) or ""
        link = _string(item.get("link")) or ""
        if title:
            details.append(f"🧉 标题：{title}\n📝 简介：{intro}\n🔗 链接：{link}")
    if not images:
        raise ValueError("B站收藏夹没有可用封面")
    return ResolvedMedia(
        "bilibili",
        "B站收藏夹",
        "image",
        url,
        image_urls=tuple(images),
        extra_text="\n\n".join(details),
    )


async def _resolve_bilibili_dynamic(url: str, dynamic_id: str) -> ResolvedMedia:
    """通过公开动态接口提取 B 站动态的文字与图片。"""
    sessdata = _config_str("BiliSessdata")
    headers = {"User-Agent": "Mozilla/5.0"}
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    async with httpx.AsyncClient(timeout=20, headers=headers, proxy=configured_proxy()) as client:
        response = await client.get(
            "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail",
            params={"id": dynamic_id},
        )
    response.raise_for_status()
    payload = _json_object(json.loads(response.text))
    data = _json_object(payload.get("data")) if payload is not None else None
    item = _json_object(data.get("item")) if data is not None else None
    if item is None:
        raise ValueError("B站动态信息为空")
    basic = _json_object(item.get("basic"))
    title = _string(basic.get("title")) if basic is not None else None
    text_parts: list[str] = []
    image_urls: list[str] = []
    modules = item.get("modules")
    if isinstance(modules, list):
        for raw_module in modules:
            module = _json_object(raw_module)
            content = _json_object(module.get("module_content")) if module is not None else None
            paragraphs = content.get("paragraphs") if content is not None else None
            if not isinstance(paragraphs, list):
                continue
            for raw_paragraph in paragraphs:
                paragraph = _json_object(raw_paragraph)
                if paragraph is None:
                    continue
                text_data = _json_object(paragraph.get("text"))
                nodes = text_data.get("nodes") if text_data is not None else None
                if isinstance(nodes, list):
                    for raw_node in nodes:
                        node = _json_object(raw_node)
                        if node is None:
                            continue
                        word_data = _json_object(node.get("word"))
                        if word_data is None:
                            continue
                        words = _string(word_data.get("words"))
                        if words:
                            text_parts.append(words)
                pictures = _json_object(paragraph.get("pic"))
                raw_pictures = pictures.get("pics") if pictures is not None else None
                if isinstance(raw_pictures, list):
                    image_urls.extend(
                        image_url
                        for raw_picture in raw_pictures
                        if (picture := _json_object(raw_picture)) is not None
                        if (image_url := _string(picture.get("url"))) is not None
                    )
    if not image_urls:
        raise ValueError("B站动态没有可发送的图片")
    return ResolvedMedia(
        "bilibili",
        title or "B站动态",
        "image",
        url,
        image_urls=tuple(dict.fromkeys(image_urls)),
        description="".join(text_parts),
    )


async def _resolve_acfun(url: str) -> ResolvedMedia:
    parsed = urlparse(url)
    if parsed.netloc.lower().startswith("m.acfun.cn"):
        ac_match = re.search(r"(?:^|&)ac=([^&]+)", parsed.query)
        if ac_match is not None:
            url = f"https://www.acfun.cn/v/ac{ac_match.group(1)}"
    separator = "&" if "?" in url else "?"
    page_url = f"{url}{separator}quickViewId=videoInfo_new&ajaxpipe=1"
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers=_ACFUN_HEADERS,
        proxy=configured_proxy(),
    ) as client:
        response = await client.get(page_url)
    marker = "window.pageInfo = window.videoInfo ="
    if marker not in response.text:
        raise ValueError("AcFun 页面未返回视频信息")
    payload_text = response.text.split(marker, 1)[1].split("</script>", 1)[0].strip().rstrip(";")
    escaped_payload = payload_text.replace('\\\\"', '\\"').replace('\\"', '"')
    payload = _json_object(json.loads(escaped_payload))
    current = _json_object(payload.get("currentVideoInfo")) if payload is not None else None
    play_json = _string(current.get("ksPlayJson")) if current is not None else None
    if play_json is None:
        raise ValueError("AcFun 页面未找到播放清单")
    play_data = _json_object(json.loads(play_json))
    adaptation = play_data.get("adaptationSet") if play_data is not None else None
    adaptation_data = _json_object(adaptation[0]) if isinstance(adaptation, list) and adaptation else None
    representations = adaptation_data.get("representation") if adaptation_data is not None else None
    if not isinstance(representations, list):
        raise ValueError("AcFun 播放清单为空")
    candidates = [item for item in representations if _json_object(item) is not None]
    selected = candidates[-1] if candidates else None
    for item in candidates:
        item_data = _json_object(item)
        height = _number(item_data.get("height")) if item_data is not None else None
        if height is not None and height <= 720:
            selected = item
    selected_data = _json_object(selected) if selected is not None else None
    m3u8_url = _string(selected_data.get("url")) if selected_data is not None else None
    if m3u8_url is None:
        raise ValueError("AcFun 播放地址为空")
    downloaded = _first_entry(await _extract_info(m3u8_url, "ac", True))
    path = _downloaded_file(downloaded) if downloaded is not None else None
    if path is None:
        raise ValueError("AcFun 视频下载后未找到文件")
    title = _string(payload.get("title")) if payload is not None else None
    return ResolvedMedia("ac", title or "AcFun 视频", "video", url, media_path=path, media_url=None)


def _base62_encode(number: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if number == 0:
        return "0"
    result = ""
    while number > 0:
        result = alphabet[number % 62] + result
        number //= 62
    return result


def _mid_to_id(mid: str) -> str:
    reversed_mid = mid[::-1]
    chunks = [reversed_mid[index : index + 7][::-1] for index in range(0, len(reversed_mid), 7)]
    encoded: list[str] = []
    for index, chunk in enumerate(chunks):
        value = _base62_encode(int(chunk))
        encoded.append(value.zfill(4) if index < len(chunks) - 1 else value)
    return "".join(reversed(encoded))


async def _resolve_weibo(url: str) -> ResolvedMedia:
    parsed = urlparse(url)
    id_match = re.search(r"/detail/([A-Za-z0-9]+)", parsed.path)
    if id_match is None:
        id_match = re.search(r"/(\d+)/([A-Za-z0-9]+)", parsed.path)
    if id_match is None:
        id_match = re.search(r"(?:^|[?&])mid=([A-Za-z0-9]+)", parsed.query)
    if id_match is None and "/tv/show/" in parsed.path:
        mid = parse_qs(parsed.query).get("mid", [""])[0]
        if mid:
            id_match = re.match(r"(.+)", _mid_to_id(mid))
    if id_match is None:
        raise ValueError("微博链接中没有动态 ID")
    weibo_id = id_match.group(2) if id_match.lastindex == 2 else id_match.group(1)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
        response = await client.get(f"https://m.weibo.cn/statuses/show?id={weibo_id}")
    payload = _json_object(json.loads(response.text))
    data = _json_object(payload.get("data")) if payload is not None else None
    if data is None:
        raise ValueError("微博接口没有返回动态信息")
    title = _string(data.get("status_title")) or "微博动态"
    text = _string(data.get("text")) or ""
    clean_text = re.sub(r"<[^>]+>", "", text)
    page_info = _json_object(data.get("page_info"))
    page_urls = _json_object(page_info.get("urls")) if page_info is not None else None
    video_url = None
    if page_urls is not None:
        video_url = _string(page_urls.get("mp4_720p_mp4")) or _string(page_urls.get("mp4_hd_mp4"))
    if video_url is not None:
        return await _download_direct_video(video_url, title, "wb")
    raw_pics = data.get("pics")
    image_urls: list[str] = []
    if isinstance(raw_pics, list):
        for raw_pic in raw_pics:
            pic = _json_object(raw_pic)
            if pic is not None and (pic_url := _string(pic.get("url"))) is not None:
                image_urls.append(pic_url)
    if image_urls:
        return ResolvedMedia("wb", title, "image", url, image_urls=tuple(image_urls), description=clean_text)
    raise ValueError("微博动态没有可发送的图片或视频")


async def _resolve_douyin(url: str) -> ResolvedMedia:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
        resolved = await client.get(url)
        final_url = str(resolved.url)
        if "share/slides" in final_url:
            fallback = await client.get("https://api.xingzhige.com/API/douyin/", params={"url": url})
            payload = _json_object(json.loads(fallback.text))
            data = _json_object(payload.get("data")) if payload is not None else None
            jump = _json_object(data.get("jx")) if data is not None else None
            if jump is not None and _string(jump.get("type")) == "图集":
                item = _json_object(data.get("item")) if data is not None else None
                image_values = item.get("images") if item is not None else None
                images = (
                    tuple(image for image in image_values if isinstance(image, str))
                    if isinstance(image_values, list)
                    else ()
                )
                title = _string(item.get("title")) if item is not None else None
                cover = _string(item.get("cover")) if item is not None else None
                if images:
                    return ResolvedMedia(
                        "dy",
                        title or "抖音图集",
                        "image",
                        url,
                        image_urls=((cover,) if cover else ()) + images,
                    )
        video_match = re.search(r"/(?:video|note)/(\d+)", final_url)
        cookie = _config_str("DouyinCookie")
        if video_match is not None and cookie:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36"
            params = {
                "device_platform": "webapp",
                "aid": "6383",
                "channel": "channel_pc_web",
                "aweme_id": video_match.group(1),
                "pc_client_type": "1",
                "version_code": "190500",
                "version_name": "19.5.0",
                "cookie_enabled": "true",
                "screen_width": "1536",
                "screen_height": "864",
                "browser_language": "zh-CN",
                "browser_platform": "Win32",
                "browser_name": "Chrome",
                "browser_version": "123.0.0.0",
                "browser_online": "true",
                "engine_name": "Blink",
                "engine_version": "123.0.0.0",
                "os_name": "Windows",
                "os_version": "10",
                "cpu_core_num": "16",
                "device_memory": "8",
                "platform": "PC",
                "msToken": "".join(
                    random.choices(
                        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789=_",
                        k=107,
                    )
                ),
            }
            query = urlencode(params)
            signed_url = (
                "https://www.douyin.com/aweme/v1/web/aweme/detail/?"
                f"{query}&a_bogus={await _generate_a_bogus(query, user_agent)}"
            )
            response = await client.get(
                signed_url,
                headers={"User-Agent": user_agent, "Referer": final_url, "Cookie": cookie},
            )
            payload = _json_object(json.loads(response.text))
            detail = _json_object(payload.get("aweme_detail")) if payload is not None else None
            if detail is not None:
                aweme_type = _number(detail.get("aweme_type"))
                raw_images = detail.get("images")
                image_urls: list[str] = []
                if isinstance(raw_images, list):
                    for raw_image in raw_images:
                        image_data = _json_object(raw_image)
                        if image_data is None:
                            continue
                        url_values = image_data.get("url_list") or image_data.get("download_url_list")
                        if isinstance(url_values, list):
                            image_urls.extend(item for item in url_values if isinstance(item, str) and item)
                if aweme_type in {2, 68} or image_urls:
                    title = _string(detail.get("desc"))
                    if image_urls:
                        return ResolvedMedia(
                            "dy",
                            title or "抖音图集",
                            "image",
                            final_url,
                            image_urls=tuple(dict.fromkeys(image_urls)),
                        )
            video = _json_object(detail.get("video")) if detail is not None else None
            play_addr = _json_object(video.get("play_addr")) if video is not None else None
            video_uri = _string(play_addr.get("uri")) if play_addr is not None else None
            if video_uri:
                player_url = f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_uri}&ratio=1080p&line=0"
                title = _string(detail.get("desc")) if detail is not None else None
                return await _download_direct_video(
                    player_url,
                    title or "抖音视频",
                    "dy",
                    source_url=final_url,
                )
    return await resolve_video(final_url, "dy")


async def _resolve_x(url: str) -> ResolvedMedia:
    api_url = f"http://47.99.158.118/video-crack/v2/parse?content={quote(url, safe='')}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxy=configured_proxy()) as client:
        response = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
        payload = _json_object(json.loads(response.text))
        data = _json_object(payload["data"]) if payload is not None and "data" in payload else None
        if data is None:
            fallback = await client.get(f"{api_url}/photo/1", headers={"User-Agent": "Mozilla/5.0"})
            fallback_payload = _json_object(json.loads(fallback.text))
            data = (
                _json_object(fallback_payload["data"])
                if fallback_payload is not None and "data" in fallback_payload
                else None
            )
    media_url = _string(data.get("url")) if data is not None else None
    if media_url is None:
        raise ValueError("X 备用解析接口未返回媒体地址")
    if re.search(r"\.(?:jpg|jpeg|png|gif|webp)(?:\?|$)", media_url, re.IGNORECASE):
        return ResolvedMedia("twitter", "X 动态媒体", "image", url, image_urls=(media_url,))
    return await _download_direct_video(media_url, "X 动态媒体", "twitter")


async def _resolve_xiaohongshu(url: str, cookie: str) -> ResolvedMedia:
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": cookie}
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers=headers, proxy=configured_proxy()
    ) as client:
        response = await client.get(url)
    final_url = str(response.url)
    note_match = re.search(r"/(?:explore|discovery/item)/([A-Za-z0-9_-]+)", final_url)
    if note_match is None:
        note_match = re.search(r"noteId=([A-Za-z0-9_-]+)", final_url)
    state_match = re.search(r"window\.__INITIAL_STATE__=(.*?)</script>", response.text, re.DOTALL)
    if note_match is None or state_match is None:
        raise ValueError("小红书页面未返回有效笔记数据，请检查 Cookie")
    note_id = note_match.group(1)
    state = _json_object(json.loads(state_match.group(1).replace("undefined", "null").rstrip(";")))
    state_note = state["note"] if state is not None and "note" in state else None
    state_note_data = _json_object(state_note)
    note_map = (
        _json_object(state_note_data["noteDetailMap"])
        if state_note_data is not None and "noteDetailMap" in state_note_data
        else None
    )
    note_entry = _json_object(note_map.get(note_id)) if note_map is not None else None
    note = _json_object(note_entry.get("note")) if note_entry is not None else None
    if note is None:
        raise ValueError("小红书笔记数据为空，请检查 Cookie 是否有效")
    title = _string(note.get("title")) or "小红书笔记"
    note_type = _string(note.get("type"))
    if note_type == "video":
        video_data = _json_object(note.get("video"))
        media = _json_object(video_data.get("media")) if video_data is not None else None
        streams = _json_object(media.get("stream")) if media is not None else None
        h264 = streams.get("h264") if streams is not None else None
        first_stream = _json_object(h264[0]) if isinstance(h264, list) and h264 else None
        video_url = _string(first_stream.get("masterUrl")) if first_stream is not None else None
        if video_url is None:
            raise ValueError("小红书视频地址为空")
        return await _download_direct_video(video_url, title)
    image_list = note.get("imageList")
    if not isinstance(image_list, list):
        raise ValueError("小红书笔记未找到图片")
    images = tuple(
        image_url
        for item in image_list
        if (image_data := _json_object(item)) is not None
        for image_url in [_string(image_data.get("urlDefault"))]
        if image_url is not None
    )
    if not images:
        raise ValueError("小红书笔记未找到图片")
    description = _string(note["desc"]) if "desc" in note else ""
    return ResolvedMedia("xiaohongshu", title, "image", url, image_urls=images, description=description or "")


async def _download_direct_video(
    url: str,
    title: str,
    platform: str = "xiaohongshu",
    source_url: str | None = None,
) -> ResolvedMedia:
    path = DOWNLOAD_PATH / f"direct_{int(time.time() * 1000000)}.mp4"
    async with httpx.AsyncClient(timeout=90, follow_redirects=True, proxy=configured_proxy()) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async with aiofiles.open(path, "wb") as output:
                async for chunk in response.aiter_bytes():
                    await output.write(chunk)
    return ResolvedMedia(
        platform,
        title,
        "video",
        source_url or url,
        media_path=path,
    )


async def download_image(url: str, suffix: str = ".jpg") -> Path:
    path = DOWNLOAD_PATH / f"image_{int(time.time() * 1000000)}{suffix}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, proxy=configured_proxy()) as client:
        response = await client.get(url)
        response.raise_for_status()
        await asyncio.to_thread(path.write_bytes, response.content)
    return path


async def download_audio(url: str) -> Path:
    path = DOWNLOAD_PATH / f"audio_{int(time.time() * 1000000)}.mp3"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, proxy=configured_proxy()) as client:
        response = await client.get(url)
        response.raise_for_status()
        await asyncio.to_thread(path.write_bytes, response.content)
    return path


def _format_comment_time(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    elapsed = max(0, int(time.time()) - timestamp)
    if elapsed < 60:
        return "刚刚"
    if elapsed < 3600:
        return f"{elapsed // 60}分钟前"
    if elapsed < 86400:
        return f"{elapsed // 3600}小时前"
    if elapsed < 2592000:
        return f"{elapsed // 86400}天前"
    return time.strftime("%m-%d", time.localtime(timestamp))


def _bilibili_emotes(content: dict[str, object]) -> tuple[tuple[str, str], ...]:
    raw_emotes = content["emote"] if "emote" in content else None
    emotes = _json_object(raw_emotes)
    if emotes is None:
        return ()
    result: list[tuple[str, str]] = []
    for key, raw_value in emotes.items():
        value = _json_object(raw_value)
        if value is None:
            continue
        url = _string(value["url"]) if "url" in value else None
        if url is None and "gif_url" in value:
            url = _string(value["gif_url"])
        if url is not None:
            label = _string(value["text"]) if "text" in value else key
            if label is not None:
                result.append((label, url.replace("http:", "https:")))
    return tuple(result)


def _parse_bilibili_comment(value: object, up_mid: int | None, include_replies: bool = True) -> ResolvedComment | None:
    item = _json_object(value)
    if item is None:
        return None
    member = _json_object(item["member"]) if "member" in item else None
    content = _json_object(item["content"]) if "content" in item else None
    username = _string(member["uname"]) if member is not None and "uname" in member else None
    text = _string(content["message"]) if content is not None and "message" in content else None
    if username is None or text is None:
        return None
    member_mid = _number(member["mid"]) if member is not None and "mid" in member else None
    pictures = content["pictures"] if content is not None and "pictures" in content else None
    images: list[str] = []
    if isinstance(pictures, list):
        for raw_picture in pictures:
            picture = _json_object(raw_picture)
            if picture is None:
                continue
            image_url = _string(picture["img_src"]) if "img_src" in picture else None
            if image_url is None and "url" in picture:
                image_url = _string(picture["url"])
            if image_url is not None:
                images.append(image_url.replace("http:", "https:"))
    level_info = _json_object(member["level_info"]) if member is not None and "level_info" in member else None
    level = _number(level_info["current_level"]) if level_info is not None and "current_level" in level_info else 0
    replies: list[ResolvedComment] = []
    raw_replies = item["replies"] if "replies" in item else None
    if include_replies and isinstance(raw_replies, list):
        for raw_reply in raw_replies[:3]:
            parsed_reply = _parse_bilibili_comment(raw_reply, up_mid, False)
            if parsed_reply is not None:
                replies.append(parsed_reply)
    avatar = _string(member["avatar"]) if member is not None and "avatar" in member else None
    return ResolvedComment(
        username=username,
        text=text,
        like=_number(item["like"]) or 0,
        avatar=avatar.replace("http:", "https:") if avatar is not None else None,
        images=tuple(images),
        image=images[0] if images else None,
        time=_format_comment_time(_number(item["ctime"]) if "ctime" in item else None),
        level=level or 0,
        is_author=member_mid is not None and up_mid is not None and member_mid == up_mid,
        replies=tuple(replies),
        emojis=tuple(url for _, url in _bilibili_emotes(content or {})),
        emote_map=_bilibili_emotes(content or {}),
    )


async def fetch_bilibili_comments(media: ResolvedMedia) -> list[ResolvedComment]:
    if not _config_bool("EnableComments") or media.platform != "bilibili" or not media.bvid:
        if media.platform == "dy" and _config_bool("EnableComments"):
            return await fetch_douyin_comments(media)
        return []
    aid = media.aid
    up_mid = media.up_mid
    if aid is None:
        detail = await _fetch_bilibili_view(media.source_url)
        if detail is not None:
            aid = _number(detail["aid"]) if "aid" in detail else None
            owner = _json_object(detail["owner"]) if "owner" in detail else None
            up_mid = _number(owner["mid"]) if owner is not None and "mid" in owner else up_mid
    if aid is None:
        return []
    headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://www.bilibili.com/video/{media.bvid}"}
    sessdata = _config_str("BiliSessdata")
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    async with httpx.AsyncClient(timeout=15, headers=headers, proxy=configured_proxy()) as client:
        response = await client.get(
            "https://api.bilibili.com/x/v2/reply/main",
            params={
                "oid": str(aid),
                "type": "1",
                "mode": "3",
                "ps": str(_config_int("CommentCount")),
                "pn": "1",
            },
        )
    response.raise_for_status()
    payload = _json_object(json.loads(response.text))
    if payload is None or payload.get("code") != 0:
        return []
    body = _json_object(payload["data"]) if "data" in payload else None
    replies = body["replies"] if body is not None and "replies" in body else None
    if not isinstance(replies, list):
        return []
    return [parsed for raw in replies if (parsed := _parse_bilibili_comment(raw, up_mid)) is not None]


async def fetch_douyin_comments(media: ResolvedMedia) -> list[ResolvedComment]:
    match = re.search(r"/(?:video|note)/(\d+)", media.source_url)
    if match is None:
        return []
    cookie = _config_str("DouyinCookie")
    if not cookie:
        return []
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36"
    params: dict[str, str] = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "aweme_id": match.group(1),
        "cursor": "0",
        "count": str(_config_int("CommentCount")),
        "item_type": "0",
        "pc_client_type": "1",
        "version_code": "170400",
        "version_name": "17.4.0",
        "msToken": "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789=_", k=107)),
    }
    query = urlencode(params)
    try:
        signed_url = (
            "https://www.douyin.com/aweme/v1/web/comment/list/?"
            f"{query}&a_bogus={await _generate_a_bogus(query, user_agent)}"
        )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.debug("VideoResolver 抖音评论签名失败：%s", exc)
        return []
    headers = {"User-Agent": user_agent, "Referer": "https://www.douyin.com/", "Cookie": cookie}
    async with httpx.AsyncClient(timeout=20, headers=headers, proxy=configured_proxy()) as client:
        response = await client.get(signed_url)
    response.raise_for_status()
    payload = _json_object(json.loads(response.text))
    raw_comments = payload["comments"] if payload is not None and "comments" in payload else None
    if not isinstance(raw_comments, list):
        return []

    def url_from_object(value: object) -> str | None:
        data = _json_object(value)
        if data is None or "url_list" not in data or not isinstance(data["url_list"], list):
            return None
        return next((item for item in data["url_list"] if isinstance(item, str) and item), None)

    def parse_douyin_comment(value: object) -> ResolvedComment | None:
        comment = _json_object(value)
        if comment is None:
            return None
        user = _json_object(comment["user"]) if "user" in comment else None
        username = _string(user["nickname"]) if user is not None and "nickname" in user else None
        text = _string(comment["text"]) if "text" in comment else None
        if username is None or text is None:
            return None
        avatar_data = user["avatar_thumb"] if user is not None and "avatar_thumb" in user else None
        avatar = url_from_object(avatar_data)
        images: list[str] = []
        raw_images = comment["image_list"] if "image_list" in comment else None
        if isinstance(raw_images, list):
            for raw_image in raw_images:
                image_data = _json_object(raw_image)
                if image_data is None:
                    continue
                for key in ("origin_url", "url"):
                    if key not in image_data:
                        continue
                    image_url = url_from_object(image_data[key])
                    if image_url is not None:
                        images.append(image_url)
                        break
        sticker_data = _json_object(comment["sticker"]) if "sticker" in comment else None
        sticker = (
            url_from_object(sticker_data["animate_url"])
            if sticker_data is not None and "animate_url" in sticker_data
            else None
        )
        replies: list[ResolvedComment] = []
        raw_replies = comment["reply_comment"] if "reply_comment" in comment else None
        if isinstance(raw_replies, list):
            for raw_reply in raw_replies[:3]:
                parsed_reply = parse_douyin_comment(raw_reply)
                if parsed_reply is not None:
                    replies.append(parsed_reply)
        return ResolvedComment(
            username=username,
            text=text,
            like=_number(comment["digg_count"]) or 0,
            avatar=avatar,
            image=images[0] if images else None,
            images=tuple(images),
            sticker=sticker,
            location=_string(comment["ip_label"]) or "" if "ip_label" in comment else "",
            time=_format_comment_time(_number(comment["create_time"]) if "create_time" in comment else None),
            replies=tuple(replies),
        )

    comments: list[ResolvedComment] = []
    for raw_comment in raw_comments:
        parsed_comment = parse_douyin_comment(raw_comment)
        if parsed_comment is not None:
            comments.append(parsed_comment)
    return comments


async def render_comments(media: ResolvedMedia, comments: list[ResolvedComment]) -> bytes:
    asset_urls: set[str] = set()

    def collect_assets(comment: ResolvedComment) -> None:
        comment_assets = (comment.avatar, comment.sticker, *comment.images, *comment.emojis)
        asset_urls.update(asset for asset in comment_assets if asset is not None)
        for reply in comment.replies:
            collect_assets(reply)

    for comment in comments:
        collect_assets(comment)
    asset_results = await asyncio.gather(*(_inline_asset(url) for url in sorted(asset_urls)))
    assets = {url: result for url, result in zip(sorted(asset_urls), asset_results) if result is not None}

    def image_tag(class_name: str, url: str | None) -> str:
        if url is None or url not in assets:
            return ""
        return f'<img class="{class_name}" src="{html.escape(assets[url], quote=True)}" />'

    def text_html(comment: ResolvedComment) -> str:
        content = html.escape(comment.text).replace("\n", "<br>")
        for placeholder, url in comment.emote_map:
            if url in assets:
                content = content.replace(html.escape(placeholder), image_tag("comment-emoji-inline", url))
        return content

    def render_reply(reply: ResolvedComment) -> str:
        reply_images = "".join(image_tag("comment-image", image) for image in reply.images)
        reply_emojis = "".join(image_tag("comment-emoji", emoji) for emoji in reply.emojis)
        badge = ' <span class="author-badge">UP</span>' if reply.is_author else ""
        return (
            '<div class="reply-item">'
            f"{image_tag('reply-avatar', reply.avatar)}"
            '<div class="reply-body">'
            f'<div class="reply-username">{html.escape(reply.username)}{badge}</div>'
            f'<div class="reply-text">{text_html(reply)}</div>'
            f'<div class="reply-media">{reply_images}{reply_emojis}</div>'
            f'<div class="reply-footer">{html.escape(reply.time)}　🤍 {reply.like}</div>'
            "</div></div>"
        )

    item_parts: list[str] = []
    for comment in comments:
        images = "".join(image_tag("comment-image", image) for image in comment.images)
        if not images and comment.image is not None:
            images = image_tag("comment-image", comment.image)
        sticker = image_tag("sticker", comment.sticker)
        emojis = "".join(image_tag("comment-emoji", emoji) for emoji in comment.emojis)
        replies = "".join(render_reply(reply) for reply in comment.replies)
        replies_html = f'<div class="replies">{replies}</div>' if replies else ""
        badge = ' <span class="author-badge">UP</span>' if comment.is_author else ""
        meta = "　".join(value for value in (comment.time, comment.location) if value)
        item_parts.append(
            "<article>"
            f"{image_tag('avatar', comment.avatar)}"
            '<section><div class="username">'
            f"{html.escape(comment.username)}{badge}"
            f"</div><p>{text_html(comment)}</p>"
            f'<div class="media">{images}{sticker}{emojis}</div>'
            f"<small>{html.escape(meta)}　♥ {comment.like}</small>"
            f"{replies_html}</section></article>"
        )
    items = "".join(item_parts)
    document = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:28px;background:#f6f7fb;color:#20242b;font-family:Arial,sans-serif;width:720px}}
h1{{font-size:24px;margin:0 0 22px}}article{{display:flex;gap:12px;background:#fff;border-radius:12px;padding:14px 18px;
margin:12px 0}}
section{{flex:1;min-width:0}}.avatar{{width:42px;height:42px;border-radius:50%;object-fit:cover}}
.username,.reply-username{{font-weight:700;color:#3d4652}}.author-badge{{color:#ff2c55;font-size:12px}}
p{{font-size:16px;line-height:1.6;margin:8px 0;overflow-wrap:anywhere}}small{{color:#8a93a3}}
.media,.reply-media{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}.comment-image{{max-width:240px;max-height:240px;object-fit:contain;border-radius:8px}}
.sticker{{max-width:120px;max-height:120px;object-fit:contain}}.comment-emoji{{width:32px;height:32px;object-fit:contain}}
.comment-emoji-inline{{width:22px;height:22px;vertical-align:middle;margin:0 3px;display:inline-block}}
.replies{{margin-top:12px;background:#f1f3f6;border-radius:8px;padding:10px}}
.reply-item{{display:flex;gap:8px;margin:8px 0}}
.reply-avatar{{width:26px;height:26px;border-radius:50%;object-fit:cover}}.reply-body{{flex:1;min-width:0}}
.reply-text{{font-size:14px;line-height:1.5;overflow-wrap:anywhere}}.reply-footer{{font-size:11px;color:#8a93a3;margin-top:4px}}
</style></head><body><h1>💬《{html.escape(media.title)}》热门评论（{len(comments)}条）</h1>{items}</body></html>"""
    return await render_html_to_bytes(document, max_width=780, image_format="png", lang="zh")


async def _inline_asset(url: str) -> str | None:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, proxy=configured_proxy()) as client:
        response = await client.get(url)
    if response.status_code >= 400 or not response.content:
        return None
    mime = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
    return f"data:{mime};base64,{base64.b64encode(response.content).decode('ascii')}"


def format_comment_text(comments: list[ResolvedComment]) -> str:
    lines: list[str] = []
    for index, comment in enumerate(comments, 1):
        meta = " | ".join(value for value in (comment.time, comment.location) if value)
        suffix = f"（{meta}）" if meta else ""
        author = " [UP]" if comment.is_author else ""
        lines.append(f"{index}. {comment.username}{author}：{comment.text}（♥ {comment.like}）{suffix}")
        for reply in comment.replies:
            reply_author = " [UP]" if reply.is_author else ""
            lines.append(f"   ↳ {reply.username}{reply_author}：{reply.text}（♥ {reply.like}）")
    return "\n".join(lines)
