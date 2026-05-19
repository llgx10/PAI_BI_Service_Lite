import re
import requests
from bs4 import BeautifulSoup
import instaloader
import os
from urllib.parse import urlparse
from PIL import Image
import pillow_heif

import re

def extract_fb_post_id(url: str):

    match = re.search(r"facebook\.com/(\d+)/posts/(\d+)", url)
    if match:
        page_id, post_id = match.groups()
        return f"{page_id}_{post_id}"

    match = re.search(r"story_fbid=(\d+).*id=(\d+)", url)
    if match:
        post_id, page_id = match.groups()
        return f"{page_id}_{post_id}"

    return None



class downloadMedia:
    def __init__(self, fpk_access_token=None, timeout=10):
        self.fb_access_token = fpk_access_token
        self.timeout = timeout

        if instaloader:
            self.ig_loader = instaloader.Instaloader()
        else:
            self.ig_loader = None

    # =========================
    # Public method
    # =========================
    def get_thumbnail(self, url):
        try:
            # ✅ AdClarity direct image URL
            if "adclarity" in url.lower():
                return self._success(url)

            platform = self.detect_platform(url)

            if platform == "instagram":
                return self._get_instagram_thumbnail(url)

            elif platform == "facebook":
                return self._get_facebook_thumbnail(url)

            elif platform == "tiktok":
                return self._get_tiktok_thumbnail(url)

            elif platform == "youtube":
                return self._get_youtube_thumbnail(url)

            else:
                return self._error("Unsupported platform")

        except Exception as e:
            return self._error(f"Unexpected error: {str(e)}")

    # =========================
    # Platform detection
    # =========================
    def detect_platform(self, url):
        url = url.lower()

        if "instagram.com" in url:
            return "instagram"
        elif "facebook.com" in url or "fb.watch" in url:
            return "facebook"
        elif "tiktok.com" in url:
            return "tiktok"
        elif "youtube.com" in url or "youtu.be" in url:
            return "youtube"

        return "unknown"

    # =========================
    # Instagram
    # =========================
    def _get_instagram_thumbnail(self, url):
        if "reels" in url:
            url = url.replace("reels", "p")
        try:
            shortcode = self._extract_ig_shortcode(url)

            if not shortcode:
                return self._error("Invalid Instagram URL")

            if self.ig_loader:
                post = instaloader.Post.from_shortcode(
                    self.ig_loader.context, shortcode
                )
                return self._success(post.url)

            return self._scrape_og_image(url)

        except Exception as e:
            # fallback to scrape
            return self._scrape_og_image(url, fallback_error=str(e))

    def _extract_ig_shortcode(self, url):
        match = re.search(r"/p/([^/?]+)", url)
        return match.group(1) if match else None

    # =========================
    # Facebook
    # =========================
    def _get_facebook_thumbnail(self, url):
        if self.fb_access_token:
            try:
                fb_id = self._extract_fb_post_id(url)

                api_url = f"https://us-central1-fanpagekarma.cloudfunctions.net/img_fb?fb_post_id={fb_id}&access_token={self.fb_access_token}"

                res = requests.get(api_url, timeout=self.timeout)
                res.raise_for_status()
                
                data = res.json()

                if isinstance(data, str):
                    return self._success(data)

                if "thumbnail" in data:
                    return self._success(data["thumbnail"])

                return self._success(res.text)
            except Exception as e:
                return self._scrape_og_image(url, fallback_error=str(e))

        return self._scrape_og_image(url)

    def _extract_fb_post_id(self, url):
        fb_id = extract_fb_post_id(url)
        return fb_id if fb_id else url 

    # =========================
    # TikTok
    # =========================
    def _get_tiktok_thumbnail(self, url):
        try:
            if "photo" in url:
                url = url.replace("photo", "video")
                
            api = f"https://www.tiktok.com/oembed?url={url}"
            res = requests.get(api, timeout=self.timeout)
            res.raise_for_status()

            data = res.json()
            return self._success(data.get("thumbnail_url"))

        except Exception as e:
            return self._error(f"TikTok error: {str(e)}")

    # =========================
    # YouTube
    # =========================
    def _get_youtube_thumbnail(self, url):
        try:
            url = url.replace("http://", "https://")
            api = f"https://www.youtube.com/oembed?url={url}&format=json"
            res = requests.get(api, timeout=self.timeout)
            res.raise_for_status()

            data = res.json()
            return self._success(data.get("thumbnail_url"))

        except Exception as e:
            return self._error(f"YouTube error: {str(e)}")

    # =========================
    # Generic OG scraper
    # =========================
    def _scrape_og_image(self, url, fallback_error=None):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            res = requests.get(url, headers=headers, timeout=self.timeout)
            res.raise_for_status()

            soup = BeautifulSoup(res.text, "html.parser")
            tag = soup.find("meta", property="og:image")

            if tag:
                return self._success(tag["content"])

            return self._error("OG image not found")

        except Exception as e:
            return self._error(
                f"Scrape failed: {str(e)} | Original: {fallback_error}"
            )

    # =========================
    # Response format
    # =========================
    def _success(self, url):
        return {
            "success": True,
            "thumbnail": url
        }

    def _error(self, message):
        return {
            "success": False,
            "error": message
        }
    # =========================
    # Download thumbnail
    # =========================
    def _convert_heic_to_jpg(self, filepath):
        try:
            if not filepath.lower().endswith(".heic"):
                return filepath
            pillow_heif.register_heif_opener()

            img = Image.open(filepath)

            new_path = filepath.rsplit(".", 1)[0] + ".jpg"
            img.convert("RGB").save(new_path, "JPEG", quality=95)

            return new_path

        except Exception as e:
            print(f"⚠️ HEIC conversion failed: {e}")
            return filepath
    def download_thumbnail(self, url, save_folder="thumbnails"):
        result = self.get_thumbnail(url)

        if not result["success"]:
            return result

        thumb_url = result["thumbnail"]

        try:
            os.makedirs(save_folder, exist_ok=True)

            # ✅ FIX: use ORIGINAL URL, not thumbnail URL
            filename = self._generate_filename(url)

            if filename is None:
                return self._error(f"Cannot extract filename from URL: {url}")

            filepath = os.path.join(save_folder, filename)

            res = requests.get(thumb_url, timeout=self.timeout)
            res.raise_for_status()

            with open(filepath, "wb") as f:
                f.write(res.content)

            # Convert HEIC → JPG if needed
            original_path = filepath
            filepath = self._convert_heic_to_jpg(filepath)

            if original_path != filepath and os.path.exists(original_path):
                os.remove(original_path)

            return {
                "success": True,
                "thumbnail": thumb_url,
                "saved_to": filepath
            }

        except Exception as e:
            return self._error(f"Download failed: {str(e)}")

    def _generate_filename(self, url):
        import re
        import os
        from urllib.parse import urlparse

        url = url.strip()

        ig = re.search(r"instagram\.com/p/([^/?]+)/?", url)
        if ig:
            return f"{ig.group(1)}.jpg"

        fb = re.search(r"facebook\.com/(\d+)/posts/(\d+)", url)
        if fb:
            return f"{fb.group(2)}.jpg"

        fb_reel = re.search(r"facebook\.com/(?:.*/)?reel/(\d+)", url)
        if fb_reel:
            return f"{fb_reel.group(1)}.jpg"

        tt = re.search(r"tiktok\.com/.*/(?:photo|video)/(\d+)", url)
        if tt:
            return f"{tt.group(1)}.jpg"

        yt = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)", url)
        if yt:
            return f"{yt.group(1)}.jpg"

        # ✅ fallback:
        # get everything after last /
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)

        if filename:
            return filename

        return None