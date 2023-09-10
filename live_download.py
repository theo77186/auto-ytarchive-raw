import subprocess
import const
import utils


def download(video_id, live_status):
    setDownloaded = True
    # If download location is not set then don't download
    if not const.DOWNLOAD and utils.PlayabilityStatus.ON_LIVE:
        return setDownloaded
    if not const.MEMBER_DOWNLOAD and utils.PlayabilityStatus.MEMBERS_ONLY:
        return setDownloaded
    if not const.PREMIUM_DOWNLOAD and utils.PlayabilityStatus.PREMIUM:
        return setDownloaded
    if not const.PREMIERE_DOWNLOAD and utils.PlayabilityStatus.PREMIERE:
        return setDownloaded

    command_list = ['start', f'ytarchive {video_id}', '/min', 'cmd', '/c']
    command_list += ['ytarchive.exe', '-v']
    if live_status == utils.PlayabilityStatus.LOGIN_REQUIRED and const.COOKIE is not None:
        command_list += ['-c', const.COOKIE]
    if live_status == utils.PlayabilityStatus.MEMBERS_ONLY and const.MEMBER_DOWNLOAD is not None:
        command_list += ['-c', const.COOKIE]
        command_list += ['-o', const.MEMBER_DOWNLOAD]
    elif live_status == utils.PlayabilityStatus.PREMIUM:
        command_list += ['-c', const.COOKIE]
        command_list += ['-o', const.PREMIUM_DOWNLOAD]
    elif live_status == utils.PlayabilityStatus.PREMIERE:
        command_list += ['-o', const.PREMIERE_DOWNLOAD]
    else:
        command_list += ['-o', const.DOWNLOAD]
    command_list += ['--add-metadata', '-t', '--vp9', '--mkv', '--write-description', '--write-thumbnail', '--threads', '2',
                     '-w']
    command_list += [f'https://www.youtube.com/watch?v={video_id}', 'best']

    try:
        print(f"[INFO] Downloading Live Stream {video_id}")
        output = subprocess.run(command_list, check=True, shell=True)
        # If theres an error then this ensures a redownload, but only works if the program crashes by itself immediately
        # print("[Debug]Output: ", output)
        # print("[Debug]Return Code:", output.returncode)
        if output.returncode != 0:
            setDownloaded = False
        setDownloaded = True
    except Exception as e:
        print(e)
        setDownloaded = False

    return setDownloaded