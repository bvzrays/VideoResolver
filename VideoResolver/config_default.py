from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsDivider,
    GsIntConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: dict[str, GSC] = {
    "Basic": GsDivider("基础配置", "解析器的通用行为和网络设置"),
    "GlobalNickname": GsStrConfig(
        "解析前缀名",
        "发送解析结果前显示的自定义名称，可留空",
        "",
    ),
    "ResolverProxy": GsStrConfig(
        "网络代理",
        "抖音、TikTok、YouTube 等服务使用的代理地址；直连请留空",
        "http://127.0.0.1:7890",
    ),
    "IsOversea": GsBoolConfig(
        "海外服务器",
        "服务器位于海外时开启，TikTok 和 YouTube 将不使用代理",
        False,
    ),
    "VideoDurationMaximum": GsIntConfig(
        "视频最大时长",
        "允许下载的视频最长时长，单位为秒；默认 480 秒",
        480,
        max_value=7200,
    ),
    "GlobalResolveController": GsStrConfig(
        "全局禁用平台",
        "用英文逗号分隔：bilibili,dy,tiktok,ac,twitter,xiaohongshu,youtube,netease,kugou,wb",
        "",
    ),
    "Bilibili": GsDivider("哔哩哔哩配置", "用于动态、收藏夹和 AI 总结等需要登录态的功能"),
    "BiliSessdata": GsStrConfig(
        "B站 SESSDATA",
        "可选；填写后启用 B站登录态功能和热门评论读取",
        "",
        secret=True,
    ),
    "Douyin": GsDivider("抖音配置", "抖音视频和图集解析所需的登录态"),
    "DouyinCookie": GsStrConfig(
        "抖音 Cookie",
        "可选；抖音接口需要登录态时填写完整 Cookie",
        "",
        secret=True,
    ),
    "Xiaohongshu": GsDivider("小红书配置", "小红书笔记解析所需的登录态"),
    "XhsCookie": GsStrConfig(
        "小红书 Cookie",
        "可选；小红书笔记解析通常需要填写完整 Cookie",
        "",
        secret=True,
    ),
    "YouTube": GsDivider("YouTube 配置", "YouTube 使用 yt-dlp，可选使用 Netscape Cookie 文件"),
    "YoutubeCookieFile": GsStrConfig(
        "YouTube Cookie 文件",
        "留空使用默认 cookies/ytb_cookies.txt；填写相对文件名或绝对路径",
        "",
    ),
    "Comments": GsDivider("评论区配置", "解析视频后异步读取可用的热门评论"),
    "EnableComments": GsBoolConfig(
        "启用评论区",
        "开启后在 B站等支持的平台尝试发送热门评论；失败不影响视频发送",
        True,
    ),
    "CommentMode": GsStrConfig(
        "评论发送模式",
        "image 为 HTML 图片，text 为合并转发文字",
        "image",
        ["image", "text"],
    ),
    "CommentCount": GsIntConfig(
        "评论数量",
        "每个平台最多读取的热门评论数",
        20,
        max_value=50,
    ),
}
