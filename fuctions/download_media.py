import os
import sys
import asyncio
import aiohttp
import pandas as pd

from tqdm import tqdm

sys.path.append("./")

from config.pai.Pai import downloadMedia


# =====================================================
# CONFIG
# =====================================================
CSV_FILE = "UL TH Nutrition.csv"

SAVE_FOLDER = "UL PH nutrition2"

TIMEOUT = 30

# =====================================================
# MODE
# =====================================================
# thumbnail -> download thumbnails
# media     -> download actual videos/media
MODE = "media"

# =====================================================
# CONCURRENCY
# =====================================================
# IMPORTANT:
# yt_dlp is blocking.
# Too high = 429 / CPU overload / ffmpeg overload
#
# Recommended:
# 4-8 for media
# 20-50 for thumbnails
# =====================================================
if MODE == "media":
    MAX_CONCURRENT = 6
else:
    MAX_CONCURRENT = 30


# =====================================================
# ASYNC FILE DOWNLOAD
# =====================================================
async def download_file(
    session,
    url,
    filepath
):

    try:

        async with session.get(
            url,
            timeout=TIMEOUT
        ) as response:

            if response.status != 200:
                return False, f"HTTP {response.status}"

            content = await response.read()

            # write in thread to avoid blocking
            await asyncio.to_thread(
                write_file,
                filepath,
                content
            )

            return True, None

    except Exception as e:

        return False, str(e)


# =====================================================
# SYNC FILE WRITE
# =====================================================
def write_file(
    filepath,
    content
):

    with open(filepath, "wb") as f:
        f.write(content)


# =====================================================
# PROCESS SINGLE URL
# =====================================================
async def process_url(
    session,
    url,
    save_folder,
    mode="thumbnail"
):

    try:

        url = str(url).strip()

        # create independent downloader
        # avoids shared-state bottlenecks
        gt = downloadMedia(
            fpk_access_token=None
        )

        # =================================================
        # THUMBNAIL MODE
        # =================================================
        if mode == "thumbnail":

            filename = gt._generate_filename(url)

            if filename is None:
                return "failed", url, "Cannot generate filename"

            filepath = os.path.join(
                save_folder,
                filename
            )

            # skip existing
            if os.path.exists(filepath):
                return "skipped", url, None

            # blocking function -> thread
            result = await asyncio.to_thread(
                gt.get_thumbnail,
                url
            )

            if not result["success"]:
                return "failed", url, result["error"]

            thumb_url = result["thumbnail"]

            success, error = await download_file(
                session=session,
                url=thumb_url,
                filepath=filepath
            )

            if not success:
                return "failed", url, error

            return "success", url, None

        # =================================================
        # MEDIA MODE
        # =================================================
        else:

            # IMPORTANT:
            # yt_dlp is BLOCKING
            # run inside thread
            result = await asyncio.to_thread(
                gt.download_media,
                url=url,
                save_folder=save_folder,
                mode="media"
            )

            if not result["success"]:
                return "failed", url, result["error"]

            return "success", url, None

    except Exception as e:

        return "failed", url, str(e)


# =====================================================
# LIMITED CONCURRENCY WRAPPER
# =====================================================
async def limited_process(
    sem,
    session,
    url,
    save_folder,
    mode
):

    async with sem:

        return await process_url(
            session=session,
            url=url,
            save_folder=save_folder,
            mode=mode
        )


# =====================================================
# MAIN FUNCTION
# =====================================================
async def download_csv_media_async(
    csv_file,
    save_folder="downloads",
    mode="thumbnail"
):

    # =================================================
    # READ CSV
    # =================================================
    df = pd.read_csv(csv_file)

    df = df.sort_values(
        by="CREATIVE_URL_SUPPLIER"
    )

    #===========TURN ON FOR AD CLARITY DOWNLOAD ONLY
    df = df[~df["CREATIVE_URL_SUPPLIER"].str.contains("tiktok|youtube", case=False, na=False)]

    if "CREATIVE_URL_SUPPLIER" not in df.columns:
        raise ValueError(
            "Column 'CREATIVE_URL_SUPPLIER' not found"
        )

    urls = (
        df["CREATIVE_URL_SUPPLIER"]
        .dropna()
        .astype(str)
        .tolist()
    )

    # remove duplicates
    urls = list(dict.fromkeys(urls))

    # =================================================
    # CREATE FOLDER
    # =================================================
    os.makedirs(
        save_folder,
        exist_ok=True
    )

    # =================================================
    # STATS
    # =================================================
    success = 0
    skipped = 0
    failed = 0

    # =================================================
    # CONCURRENCY CONTROL
    # =================================================
    sem = asyncio.Semaphore(
        MAX_CONCURRENT
    )

    # =================================================
    # AIOHTTP SESSION
    # =================================================
    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT
    )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers
    ) as session:

        # =================================================
        # CREATE TASKS
        # =================================================
        tasks = [

            asyncio.create_task(

                limited_process(
                    sem=sem,
                    session=session,
                    url=url,
                    save_folder=save_folder,
                    mode=mode
                )

            )

            for url in urls

        ]

        # =================================================
        # PROCESS AS COMPLETED
        # =================================================
        pbar = tqdm(
            total=len(tasks),
            desc=f"Downloading ({mode})"
        )

        for future in asyncio.as_completed(tasks):

            status, url, error = await future

            if status == "success":

                success += 1

            elif status == "skipped":

                skipped += 1

            else:

                failed += 1

                print(f"\n❌ Failed: {url}")

                if error:
                    print(error)

            pbar.update(1)

        pbar.close()

    # =================================================
    # SUMMARY
    # =================================================
    print("\n====================")
    print(f"MODE           : {mode}")
    print(f"✅ Downloaded  : {success}")
    print(f"⏭️ Skipped      : {skipped}")
    print(f"❌ Failed       : {failed}")
    print("====================")


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":

    asyncio.run(

        download_csv_media_async(
            csv_file=CSV_FILE,
            save_folder=SAVE_FOLDER,
            mode=MODE
        )

    )