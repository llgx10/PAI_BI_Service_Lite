import os
import sys
import asyncio
import aiohttp
import pandas as pd
import threading

from tqdm import tqdm
from datetime import datetime

sys.path.append("./")

from connector.pai.Pai import downloadMedia


# =====================================================
# CONFIG
# =====================================================
CSV_FILE = "UL TH Nutrition.csv"
SAVE_FOLDER = "UL TH Nutrition"

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
# LOGGING
# =====================================================
LOG_FOLDER = "logs"

os.makedirs(LOG_FOLDER, exist_ok=True)

LOG_FILE = os.path.join(
    LOG_FOLDER,
    f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
)

log_lock = threading.Lock()


# =====================================================
# THREAD SAFE LOGGER
# =====================================================
def write_log(status, url, path=None, error=None):

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_line = (
        f"[{timestamp}] "
        f"[{status.upper()}] "
        f"URL={url}"
    )

    if path:
        log_line += f" | PATH={path}"

    if error:
        log_line += f" | ERROR={error}"

    with log_lock:

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")


# =====================================================
# PROCESS SINGLE URL
# =====================================================
async def process_url(session, url, save_folder, mode):

    try:

        url = str(url).strip()

        gt = downloadMedia(fpk_access_token=None)

        # =================================================
        # DOWNLOAD
        # =================================================
        result = await asyncio.to_thread(
            gt.download_media,
            url=url,
            save_folder=save_folder,
            mode=mode
        )

        # =================================================
        # FAILED
        # =================================================
        if not result.get("success"):

            return (
                "failed",
                url,
                result.get("error"),
                None
            )

        # =================================================
        # GET SAVED PATH
        # =================================================
        saved_path = (
            result.get("filepath")
            or result.get("path")
            or result.get("output_path")
        )

        # =================================================
        # SUCCESS
        # =================================================
        return (
            "success",
            url,
            None,
            saved_path
        )

    except Exception as e:

        return (
            "failed",
            url,
            str(e),
            None
        )


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
    df=df[:100]
    if "CREATIVE_URL_SUPPLIER" not in df.columns:
        raise ValueError("Column not found")

    urls = (
        df["CREATIVE_URL_SUPPLIER"]
        .dropna()
        .astype(str)
        .unique()
    )

    os.makedirs(save_folder, exist_ok=True)

    # =================================================
    # INIT DOWNLOADER
    # =================================================
    gt = downloadMedia(fpk_access_token=None)

    # =================================================
    # GENERATE EXPECTED FILENAMES
    # =================================================
    records = []

    for url in tqdm(urls, desc="Generating filenames"):

        try:

            filename = gt.generate_filename(url)

            records.append({
                "url": url,
                "filename": filename
            })

        except Exception as e:

            records.append({
                "url": url,
                "filename": None
            })

            print(f"Filename generation failed: {url}")
            print(e)

            write_log(
                status="filename_failed",
                url=url,
                error=str(e)
            )

    url_df = pd.DataFrame(records)

    # =================================================
    # EXISTING FILES DF
    # =================================================
    existing_files = os.listdir(save_folder)

    existing_df = pd.DataFrame({
        "filename": existing_files,
        "downloaded": True
    })

    # =================================================
    # LEFT JOIN
    # =================================================
    merged_df = url_df.merge(
        existing_df,
        on="filename",
        how="left"
    )

    # =================================================
    # FILTER MISSING FILES ONLY
    # =================================================
    pending_df = merged_df[
        merged_df["downloaded"].isna()
    ]

    pending_urls = pending_df["url"].tolist()

    already_downloaded_df = merged_df[
        merged_df["downloaded"] == True
    ]

    # =================================================
    # LOG SKIPPED FILES
    # =================================================
    for _, row in already_downloaded_df.iterrows():

        existing_path = os.path.join(
            save_folder,
            row["filename"]
        )

        write_log(
            status="skipped",
            url=row["url"],
            path=existing_path
        )

    print("\n====================")
    print(f"Total URLs      : {len(urls)}")
    print(f"Already Exists  : {len(urls) - len(pending_urls)}")
    print(f"Need Download   : {len(pending_urls)}")
    print("====================\n")

    # =================================================
    # ASYNC DOWNLOAD
    # =================================================
    success = skipped = len(already_downloaded_df)
    failed = 0

    sem = asyncio.Semaphore(MAX_CONCURRENT)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers
    ) as session:

        tasks = [
            asyncio.create_task(
                limited_process(
                    sem,
                    session,
                    url,
                    save_folder,
                    mode
                )
            )
            for url in pending_urls
        ]

        pbar = tqdm(
            total=len(tasks),
            desc=f"Downloading ({mode})"
        )

        for future in asyncio.as_completed(tasks):

            status, url, error, saved_path = await future

            # =================================================
            # SUCCESS
            # =================================================
            if status == "success":

                success += 1

                write_log(
                    status="success",
                    url=url,
                    path=saved_path
                )

            # =================================================
            # SKIPPED
            # =================================================
            elif status == "skipped":

                skipped += 1

                write_log(
                    status="skipped",
                    url=url
                )

            # =================================================
            # FAILED
            # =================================================
            else:

                failed += 1

                print(f"\n❌ Failed: {url}")

                if error:
                    print(error)

                write_log(
                    status="failed",
                    url=url,
                    error=error
                )

            pbar.update(1)

        pbar.close()

    print("\n====================")
    print(f"MODE           : {mode}")
    print(f"✅ Downloaded  : {success}")
    print(f"⏭️ Skipped      : {skipped}")
    print(f"❌ Failed       : {failed}")
    print(f"📝 Log File     : {LOG_FILE}")
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