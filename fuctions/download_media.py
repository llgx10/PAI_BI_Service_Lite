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
SAVE_FOLDER = "UL PH nutrition thumbnail"

TIMEOUT = 30

# =====================================================
# MODE
# =====================================================
MODE = "thumbnail"   # "thumbnail" | "media"

# =====================================================
# CONCURRENCY
# =====================================================
MAX_CONCURRENT = 6 if MODE == "media" else 30


# =====================================================
# PROCESS SINGLE URL
# =====================================================
async def process_url(session, url, save_folder, mode):

    try:

        url = str(url).strip()

        gt = downloadMedia(fpk_access_token=None)

        # =================================================
        # SINGLE ENTRY POINT (CLASS HANDLES EVERYTHING)
        # =================================================
        result = await asyncio.to_thread(
            gt.download_media,
            url=url,
            save_folder=save_folder,
            mode=mode
        )

        # =================================================
        # HANDLE RESULT ONLY (NO RE-DOWNLOAD LOGIC)
        # =================================================
        if not result.get("success"):
            return "failed", url, result.get("error")

        # optional skip tracking
        if result.get("direct_download") is False:
            return "success", url, None

        return "success", url, None

    except Exception as e:
        return "failed", url, str(e)


# =====================================================
# LIMITED CONCURRENCY WRAPPER
# =====================================================
async def limited_process(sem, session, url, save_folder, mode):

    async with sem:
        return await process_url(session, url, save_folder, mode)


# =====================================================
# MAIN FUNCTION
# =====================================================
async def download_csv_media_async(csv_file, save_folder, mode):

    df = pd.read_csv(csv_file)
    df = df.sort_values(by="CREATIVE_URL_SUPPLIER")

    if "CREATIVE_URL_SUPPLIER" not in df.columns:
        raise ValueError("Column not found")

    urls = (
        df["CREATIVE_URL_SUPPLIER"]
        .dropna()
        .astype(str)
        .tolist()
    )

    urls = list(dict.fromkeys(urls))

    os.makedirs(save_folder, exist_ok=True)

    success = skipped = failed = 0

    sem = asyncio.Semaphore(MAX_CONCURRENT)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers
    ) as session:

        tasks = [
            asyncio.create_task(
                limited_process(sem, session, url, save_folder, mode)
            )
            for url in urls
        ]

        pbar = tqdm(total=len(tasks), desc=f"Downloading ({mode})")

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
            CSV_FILE,
            SAVE_FOLDER,
            MODE
        )
    )