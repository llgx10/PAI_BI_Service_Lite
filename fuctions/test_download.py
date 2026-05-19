from yt_dlp import YoutubeDL

URLS = ['https://www.tiktok.com/@surf.philippines/video/7620383168176065813']
with YoutubeDL() as ydl:
    ydl.download(URLS)