import urllib.request
import urllib.parse
import http.cookiejar
import re
import time
from enum import Enum, auto
import os
import json
import functools
import http.client
import ipaddress
import random
import threading
from addons import discord
from addons import telegram
import const
import socket


socket.setdefaulttimeout(5)


def log(msg):
    print(f"[INFO]{msg}")


def warn(msg):
    print(f"[WARN]{msg}")


class PlayabilityStatus(Enum):
    PRIVATED = auto()
    COPYRIGHTED = auto()
    REMOVED = auto()
    MEMBERS_ONLY = auto()
    OFFLINE = auto()
    OK = auto()
    ON_LIVE = auto()
    UNKNOWN = auto()
    LOGIN_REQUIRED = auto()
    UNLISTED = auto()
    PREMIERE = auto()
    PREMIUM = auto()


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = threading.Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


class BoundHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, *args, source_address=None, **kwargs):
        urllib.request.HTTPHandler.__init__(self, *args, **kwargs)
        self.http_class = functools.partial(http.client.HTTPConnection,
                                            source_address=source_address,
                                            timeout=5)

    def http_open(self, req):
        return self.do_open(self.http_class, req)


class BoundHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, *args, source_address=None, **kwargs):
        urllib.request.HTTPSHandler.__init__(self, *args, **kwargs)
        self.https_class = functools.partial(http.client.HTTPSConnection,
                                             source_address=source_address,
                                             timeout=5)

    def https_open(self, req):
        return self.do_open(self.https_class, req,
                            context=self._context, check_hostname=self._check_hostname)


def get_random_line(filepath: str) -> str:
    file_size = os.path.getsize(filepath)
    with open(filepath, 'rb') as f:
        while True:
            pos = random.randint(0, file_size)
            if not pos:  # the first line is chosen
                return f.readline().decode()  # return str
            f.seek(pos)  # seek to random position
            f.readline()  # skip possibly incomplete line
            line = f.readline()  # read next (full) line
            if line:
                return line.decode()
            # else: line is empty -> EOF -> try another position in next iteration


def is_ip(ip):
    try:
        ip = ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def get_pool_ip():
    if const.IP_POOL:
        if os.path.isfile(const.IP_POOL):
            for _ in range(3):  # Retry for 3 times.
                ip = get_random_line(const.IP_POOL).rstrip().lstrip()
                if is_ip(ip):
                    return ip
    return None


def urlopen(url, retry=0, source_address="random", use_cookie=False):
    try:
        handlers = []

        if source_address == "random":
            source_address = get_pool_ip()
        if not is_ip(source_address):
            source_address = None

        if use_cookie:
            if hasattr(const, "COOKIE") and const.COOKIE and os.path.isfile(const.COOKIE):
                cj = http.cookiejar.MozillaCookieJar()
                cj.load(const.COOKIE)
                cookie_handler = urllib.request.HTTPCookieProcessor(cj)
                handlers.append(cookie_handler)

        if source_address:
            log(f" Using IP: {source_address}")
            scheme = "https"
            if type(url) == str:
                scheme = urllib.parse.urlsplit(url).scheme
            elif isinstance(url, urllib.request.Request):
                scheme = urllib.parse.urlsplit(url.full_url).scheme

            handler = (BoundHTTPHandler if scheme == "http" else BoundHTTPSHandler)(source_address=(source_address, 0))
            handlers.append(handler)

        if handlers:
            return urllib.request.build_opener(*handlers).open(url)
        else:
            return urllib.request.urlopen(url)
    except (http.client.IncompleteRead, socket.timeout) as e:
        if retry < const.HTTP_RETRY:
            warn(f" Get IncompleteRead/Timeout Error. Trying {retry+1}/{const.HTTP_RETRY}...")
            return urlopen(url, retry+1, get_pool_ip() if source_address else None, use_cookie)
        else:
            raise e
    except urllib.error.HTTPError as e:
        if e.code == 503:
            if retry < const.HTTP_RETRY:
                warn(f" Get {e.code} Error. Trying {retry+1}/{const.HTTP_RETRY}...")
                time.sleep(1)
                return urlopen(url, retry+1, get_pool_ip() if source_address else None, use_cookie)
            else:
                raise e
        else:
            raise e
    except urllib.error.URLError as e:
        if retry < const.HTTP_RETRY:
            warn(f" Get urllib.error.URLError Error. Trying {retry+1}/{const.HTTP_RETRY}...")
            return urlopen(url, retry+1, get_pool_ip() if source_address else None, use_cookie)
        else:
            raise e


def is_live(channel_id, use_cookie=False, retry=0):
    # Use /streams instead of embed playlist
    if const.COOKIE:
        use_cookie = True
    url = f"https://www.youtube.com/channel/{channel_id}/streams"
    # url_1 = f"https://www.youtube.com/embed?list=UU{channel_id[2:]}"
    with urlopen(url, use_cookie=use_cookie) as response:
        video_type = PlayabilityStatus.OFFLINE
        html = response.read().decode()
        try:
            re_live = r'\"[a-zA-Z]+\":\"LIVE\"'
            re_member = r'\"[a-zA-Z]+\":\"Members only\"'
            re_premium = r'\"[a-zA-Z]+\":\"Premium\"'
            re_id = r'\"videoId\":\"([^"]+)'

            fragments = re.split('videoRenderer', html)
            video_url = False
            for fragment in fragments:
                # is_live = re.search(re_live, fragment)
                is_live_text = True if re.search(re_live, fragment) else False
                if not is_live_text:
                    continue

                video_id = re.search(re_id, fragment)
                video_url = f"https://www.youtube.com/watch?v={video_id[1]}"
                video_type = PlayabilityStatus.ON_LIVE

                if re.search(re_member, fragment):
                    video_type = PlayabilityStatus.MEMBERS_ONLY
                elif re.search(re_premium, fragment):
                    video_type = PlayabilityStatus.PREMIUM

            return video_url, video_type
        except AttributeError:
            return False, video_type
        except Exception as e:
            print(e)
            if retry < const.HTTP_RETRY:
                return is_live(channel_id, use_cookie=use_cookie, retry=retry + 1)  # Try again, sth weird happened
            else:
                warn(
                    f" Something weird happened on checking Live for {channel_id}...")
                return False, video_type


def is_premiere(channel_id, use_cookie=False, retry=0):
    # Use /videos instead of embed playlist
    # As of 2023.07.25 premieres can not be set to member's only
    # if const.COOKIE:
    #     use_cookie = True
    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    with urlopen(url, use_cookie=use_cookie) as response:
        video_type = PlayabilityStatus.OFFLINE
        html = response.read().decode()
        try:
            re_live = r'\"[a-zA-Z]+\":\"LIVE\"'
            re_premiere = r'\"[a-zA-Z]+\":\"Premiere\"'
            re_id = r'\"videoId\":\"([^"]+)'

            fragments = re.split('videoRenderer', html)
            video_url = False
            for fragment in fragments:
                is_live_text = True if re.search(re_live, fragment) else False
                if not is_live_text:
                    continue

                video_id = re.search(re_id, fragment)
                video_url = f"https://www.youtube.com/watch?v={video_id[1]}"
                video_type = PlayabilityStatus.ON_LIVE
                if re.search(re_premiere, fragment):
                    video_type = PlayabilityStatus.PREMIERE
            return video_url, video_type
        except AttributeError:
            return False, video_type
        except Exception as e:
            print(e)
            if retry < const.HTTP_RETRY:
                return is_live(channel_id, use_cookie=use_cookie, retry=retry + 1)  # Try again, sth weird happened
            else:
                warn(
                    f" Something weird happened on checking Live for {channel_id}...")
                return False, video_type


# 2021.5.7 Youtube chokes for PlayabilityStatus.REMOVED
# if PlayabilityStatus.REMOVED, we now check 3 times for accuracy.

def get_video_status(video_id):
    def _get_video_status(video_id):
        url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(url)
        req.add_header('Accept-Language', 'en-US,en;q=0.5')

        with urlopen(req) as response:
            html = response.read().decode()
            # "label":"Premium"
            if '"offerId":"sponsors_only_video"' in html:
                return PlayabilityStatus.MEMBERS_ONLY
            elif '"status":"UNPLAYABLE"' in html and '"label":"Premium"' in html:
                return PlayabilityStatus.PREMIUM
            elif '"status":"UNPLAYABLE"' in html:
                return PlayabilityStatus.COPYRIGHTED
            elif '"status":"LOGIN_REQUIRED"' in html and '"reason":"Sign in to confirm your age"' in html:
                return PlayabilityStatus.LOGIN_REQUIRED
            elif '"status":"LOGIN_REQUIRED"' in html:
                return PlayabilityStatus.PRIVATED
            elif '"status":"ERROR"' in html:
                return PlayabilityStatus.REMOVED
            elif '"simpleText":"Premiere' in html:
                return PlayabilityStatus.PREMIERE
            elif '"status":"OK"' in html:
                if '"isUnlisted":true' in html:
                    return PlayabilityStatus.UNLISTED
                if 'hlsManifestUrl' in html:
                    return PlayabilityStatus.ON_LIVE
                return PlayabilityStatus.OK
            elif '"status":"LIVE_STREAM_OFFLINE"' in html:
                return PlayabilityStatus.OFFLINE
            else:
                with open(os.path.join(const.LOGS_DIR, f"{video_id}.html"), "w", encoding="utf8") as f:
                    f.write(html)
                return PlayabilityStatus.UNKNOWN

    status = _get_video_status(video_id)
    if status is PlayabilityStatus.REMOVED:
        for _ in range(3):
            tmp = _get_video_status(video_id)
            if tmp is not PlayabilityStatus.REMOVED:
                return tmp
    return status


def notify(message, files=None):
    if const.ENABLED_MODULES["discord"]:
        threading.Thread(target=discord.send, args=(const.DISCORD_WEBHOOK_URL, message), kwargs={
            "version": const.VERSION,
            "files": files if const.DISCORD_SEND_FILES else None
        }, daemon=True).start()
    if const.ENABLED_MODULES["telegram"]:
        if const.TELEGRAM_SEND_FILES:
            threading.Thread(target=telegram.send_files, args=(const.TELEGRAM_BOT_TOKEN, const.TELEGRAM_CHAT_ID, message, files), daemon=True).start()
        else:
            threading.Thread(target=telegram.send, args=(const.TELEGRAM_BOT_TOKEN, const.TELEGRAM_CHAT_ID, message), daemon=True).start()


def get_avatar(url):
    regex = r'"avatar":{"thumbnails":(\[{[^\]]+?\])}'
    with urlopen(url) as resp:
        html = resp.read().decode()
        result = re.findall(regex, html)

    result = [json.loads(x) for x in result]
    result = [item for sublist in result for item in sublist]
    result = max(result, key=lambda x: x['width'])
    result = result['url']
    return result
