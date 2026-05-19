import os
import sys
import asyncio
import aiohttp
import pandas as pd

from tqdm import tqdm

sys.path.append('./')

from config.pai.Pai import downloadMedia


# =========================================
# CONFIG
# =========================================
csv_file = 'UL TH Nutrition.csv'
folder = 'UL PH nutrition'

BATCH_SIZE = 20
TIMEOUT = 30


# =========================================
# ASYNC DOWNLOAD
# =========================================
async def download_file(session, url, filepath):
    try:
        async with session.get(url, timeout=TIMEOUT) as response:

            if response.status != 200:
                return False, f"HTTP {response.status}"

            content = await response.read()

            with open(filepath, "wb") as f:
                f.write(content)

            return True, None

    except Exception as e:
        return False, str(e)


# =========================================
# PROCESS SINGLE URL
# =========================================
async def process_url(session, gt, url, save_folder):

    try:
        url = str(url).strip()

        # -------------------------
        # Generate filename
        # -------------------------
        filename = gt._generate_filename(url)

        if filename is None:
            return "failed", url, "Cannot generate filename"

        filepath = os.path.join(save_folder, filename)

        # -------------------------
        # Skip existing
        # -------------------------
        if os.path.exists(filepath):
            return "skipped", url, None

        # -------------------------
        # Get thumbnail URL
        # -------------------------
        result = gt.get_thumbnail(url)

        if not result["success"]:
            return "failed", url, result["error"]

        thumb_url = result["thumbnail"]

        # -------------------------
        # Download image/video
        # -------------------------
        success, error = await download_file(
            session,
            thumb_url,
            filepath
        )

        if not success:
            return "failed", url, error

        return "success", url, None

    except Exception as e:
        return "failed", url, str(e)


# =========================================
# MAIN FUNCTION
# =========================================
async def download_csv_thumbnails_async(
    csv_file,
    save_folder="thumbnails",
    access_token=None
):

    # -------------------------
    # Create downloader instance
    # -------------------------
    gt = downloadMedia(
        fpk_access_token=access_token
    )

    # -------------------------
    # Read CSV
    # -------------------------
    df = pd.read_csv(csv_file)

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

    # -------------------------
    # Create folder
    # -------------------------
    os.makedirs(save_folder, exist_ok=True)

    # -------------------------
    # Stats
    # -------------------------
    success = 0
    skipped = 0
    failed = 0

    # -------------------------
    # Async session
    # -------------------------
    connector = aiohttp.TCPConnector(limit=50)

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers
    ) as session:

        # -------------------------
        # Process in batches
        # -------------------------
        for i in tqdm(
            range(0, len(urls), BATCH_SIZE),
            desc="Downloading thumbnails"
        ):

            batch = urls[i:i + BATCH_SIZE]

            tasks = [
                process_url(
                    session,
                    gt,
                    url,
                    save_folder
                )
                for url in batch
            ]

            results = await asyncio.gather(*tasks)

            # -------------------------
            # Handle results
            # -------------------------
            for status, url, error in results:

                if status == "success":
                    success += 1

                elif status == "skipped":
                    skipped += 1

                else:
                    failed += 1

                    print(f"\n❌ Failed: {url}")

                    if error:
                        print(error)

    # -------------------------
    # Final summary
    # -------------------------
    print("\n====================")
    print(f"✅ Downloaded : {success}")
    print(f"⏭️ Skipped     : {skipped}")
    print(f"❌ Failed      : {failed}")
    print("====================")


# =========================================
# RUN
# =========================================
if __name__ == "__main__":

    asyncio.run(
        download_csv_thumbnails_async(
            csv_file=csv_file,
            save_folder=folder,
            access_token=None
        )
    )