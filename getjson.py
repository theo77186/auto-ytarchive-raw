import urllib.request
import urllib.parse
import re
import html
import base64
import datetime
import json
import utils
import yt_dlp
import const

VERSION = "1.5"

PRIORITY = {
    "VIDEO": [
        337, 315, 266, 138, # 2160p60
        313, 336, # 2160p
        308, # 1440p60
        271, 264, # 1440p
        335, 303, 299, # 1080p60
        312, 311, # Premium 1080p and 720p
        248, 169, 137, # 1080p
        334, 302, 298, # 720p60
        247, 136 # 720p
    ],
    "AUDIO": [
        251, 141, 171, 140, 250, 249, 139, 234, 233
    ]
}


def parse(regex, html_raw):
    match = re.search(regex, html_raw).group(1) or re.search(regex, html_raw).group(2)
    return html.unescape(match)


def get_youtube_id(url):
    try:
        return re.search(r'^.*(?:(?:youtu\.be\/|v\/|vi\/|u\/\w\/|embed\/)|(?:(?:watch)?\?v(?:i)?=|\&v(?:i)?=))([^#\&\?]*).*', url).group(1)
    except:
        with utils.urlopen(url) as response:
            html_raw = response.read().decode()
            regex = r'<meta itemprop="videoId" content="(.+?)">'
            result = re.search(regex, html_raw).group(1)
            return result


def get_youtube_video_info(video_id, channel_id, channel_name, html_raw):
    thumbnail_url = parse(r'<link rel="image_src" href="(.+?)">', html_raw) if '<link rel="image_src" href="' in html_raw else f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
    return {
        "title": parse(r'<meta name="title" content="(.+?)">', html_raw),
        "id": video_id,
        "channelName": channel_name,
        "channelURL": f"https://www.youtube.com/channel/{channel_id}",
        "description": parse(r'"description":{"simpleText":"(.+?)"},', html_raw).replace("\\n", "\n") if '"description":{"simpleText":"' in html_raw else "",
        "thumbnail": get_image(thumbnail_url),
        "thumbnailUrl": thumbnail_url,
        "startTimestamp": parse(r'"startTimestamp":"(.+?)"', html_raw)
    }


def get_image(url):
    with utils.urlopen(url) as response:
        data = response.read()
        b64 = base64.b64encode(data).decode()

        return f"data:image/jpeg;base64,{b64}"


def build_req(video_id, use_cookie=False):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    info_req = urllib.request.Request(
        video_url, 
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
        }
    )
    return utils.urlopen(info_req, use_cookie=use_cookie)

def yt_dlp_get_urls(video_id, use_cookie=False):
    config = {
        'extractor_args': {'youtube': {'player_client': ['web'], 'skip': ['dash']}},
        'format': 'bv+ba',
        'noprogress': True,
        'quiet': True
    }
    if use_cookie and const.COOKIE is not None:
        config |= { 'cookiefile': const.COOKIE }

    def get_url_format(info, fmt):
        return [ f['url'] for f in info['formats'] if f['format_id'] == fmt ][0]

    ydl = yt_dlp.YoutubeDL(config)
    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    format_id_list = info["format_id"].split('+')
    if len(format_id_list) != 2:
        utils.warn(f"yt-dlp: Expected 2 formats but found {len(format_id_list)} formats")
        return None
    video_fmt, audio_fmt = format_id_list
    video_url = get_url_format(info, video_fmt)
    audio_url = get_url_format(info, audio_fmt)

    return {video_fmt: video_url}, {audio_fmt: audio_url}


def get_json(video_url, channel_id, channel_name, file=None, require_cookie=False):
    video_id = get_youtube_id(video_url)

    with build_req(video_id, require_cookie) as response:
        data = response.read().decode()
        match = re.findall(r'"itag":(\d+),"url":"([^"]+)"', data)
        if match is None:
            # TODO: Decide whether to grab url and signature cipher or just leave it as None
            # For premium videos grab the entire url and signatureCipher
            # Unsure of how to decipher signature
            match = re.findall(r'"itag":(\d+),.*"signatureCipher":"([^"]+)"', data)
        match = dict(x for x in match)

        best = {
            "video": None,
            "audio": None,
            "metadata": get_youtube_video_info(video_id, channel_id, channel_name, data),
            "version": VERSION,
            "createTime": datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        }
        for itag in PRIORITY["VIDEO"]:
            itag = str(itag)
            if itag in match and "noclen" in match[itag]: # With `noclen` param, the video can be downloaded by fregments.
                best["video"] = {
                    itag: match[itag].replace("\\u0026", "\u0026")
                }
                break
        for itag in PRIORITY["AUDIO"]:
            itag = str(itag)
            if itag in match and "noclen" in match[itag]:
                best["audio"] = {
                    itag: match[itag].replace("\\u0026", "\u0026")
                }
                break

        try:
            best["video"], best["audio"] = yt_dlp_get_urls(video_id, require_cookie)
        except:
            pass

        if best["video"] is None or best["audio"] is None:
            if best["video"] is None:
                utils.warn(f" {video_id} got empty video sources.")
            if best["audio"] is None:
                utils.warn(f" {video_id} got empty audio sources.")

            utils.warn("Failed to get json with cookies")
            print(match)
            
        if file is not None:
            with open(file, "w", encoding="utf8") as f:
                json.dump(best, f, indent=4, ensure_ascii=False)
        return best
