from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsDivider,
    GsFileUploadConfig,
    GsIntConfig,
    GsStrConfig,
)

from .utils.resource.RESOURCE_PATH import COOKIE_PATH

CONFIG_DEFAULT: dict[str, GSC] = {
    "Basic": GsDivider("基础配置", "解析器的通用行为和网络设置"),
    "GlobalNickname": GsStrConfig(
        "解析前缀名",
        "发送解析结果前显示的自定义名称，可留空",
        "",
    ),
    "EnableMediaCard": GsBoolConfig(
        "发送解析图",
        "解析完成后发送包含作者、标题和媒体预览的信息卡；关闭不影响媒体、评论和总结",
        True,
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
    "Platforms": GsDivider("平台开关", "每个平台可独立启停；海外平台默认关闭"),
    "EnableBilibili": GsBoolConfig("启用哔哩哔哩", "解析哔哩哔哩链接和 BV 号", True),
    "EnableDouyin": GsBoolConfig("启用抖音", "解析抖音视频和图集", True),
    "EnableTikTok": GsBoolConfig("启用 TikTok", "解析 TikTok 视频；默认关闭", False),
    "EnableAcFun": GsBoolConfig("启用 AcFun", "解析 AcFun 视频", True),
    "EnableTwitter": GsBoolConfig("启用 X", "解析 X/Twitter 媒体；默认关闭", False),
    "EnableWeibo": GsBoolConfig("启用微博", "解析微博动态", True),
    "EnableXiaohongshu": GsBoolConfig("启用小红书", "解析小红书视频和图集", True),
    "EnableYouTube": GsBoolConfig("启用 YouTube", "解析 YouTube 视频；默认关闭", False),
    "EnableNetease": GsBoolConfig("启用网易云音乐", "解析网易云音乐歌曲", True),
    "EnableKugou": GsBoolConfig("启用酷狗音乐", "解析酷狗音乐歌曲", True),
    "CookieGuide": GsDivider(
        "如何获取 Cookie",
        (
            "先在 Chrome 或 Edge 登录目标网站，再按 F12 打开开发者工具。B站在“应用/Application → Cookie”中"
            "复制 SESSDATA 的值；抖音和小红书在“网络/Network → 刷新页面 → 选择同域请求 → 请求标头/"
            "Request Headers”中复制完整 Cookie。原项目视频教程：https://github.com/user-attachments/assets/"
            "7ead6d62-a36c-4e8d-bb5d-6666749dfb26。Cookie 等同账号凭据，请勿公开分享。"
        ),
    ),
    "Bilibili": GsDivider("哔哩哔哩配置", "B站只需填写 SESSDATA 的值，不要包含 SESSDATA= 前缀"),
    "BiliSessdata": GsStrConfig(
        "B站 SESSDATA",
        "登录 bilibili.com 后，在 F12 → 应用/Application → Cookie 中找到 SESSDATA，只粘贴该项的值",
        "",
        secret=True,
    ),
    "Douyin": GsDivider("抖音配置", "抖音需要完整 Cookie，格式为 key=value; key2=value2"),
    "DouyinCookie": GsStrConfig(
        "抖音 Cookie",
        "登录 douyin.com 后，在 F12 网络请求的 Request Headers 中复制 Cookie 后面的完整内容",
        "",
        secret=True,
    ),
    "Xiaohongshu": GsDivider("小红书配置", "小红书需要完整 Cookie，格式为 key=value; key2=value2"),
    "XhsCookie": GsStrConfig(
        "小红书 Cookie",
        "登录 xiaohongshu.com 后，在 F12 网络请求的 Request Headers 中复制 Cookie 后面的完整内容",
        "",
        secret=True,
    ),
    "YouTube": GsDivider(
        "YouTube 配置",
        "导出 Netscape 格式 cookies.txt 后可直接上传；文件首行通常为 # Netscape HTTP Cookie File",
    ),
    "YoutubeCookieUpload": GsFileUploadConfig(
        "上传 YouTube Cookie",
        "上传 Netscape 格式 txt 文件，控制台会保存为 data/VideoResolver/cookies/ytb_cookies.txt",
        "",
        str(COOKIE_PATH),
        "ytb_cookies",
        "txt",
    ),
    "YoutubeCookieFile": GsStrConfig(
        "YouTube Cookie 自定义路径",
        "高级选项；留空使用上方上传的文件，也可填写 cookies 目录内的相对文件名或绝对路径",
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
