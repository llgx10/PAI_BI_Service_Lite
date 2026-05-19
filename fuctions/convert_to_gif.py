import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed

from moviepy import VideoFileClip
from tqdm import tqdm


# =========================================
# CONFIG
# =========================================
INPUT_FOLDER = "UL PH nutrition"
OUTPUT_FOLDER = "UL PH nutrition_converted"

GIF_FPS = 10
GIF_WIDTH = 480

# Number of parallel workers
MAX_WORKERS = 4


# =========================================
# CREATE OUTPUT FOLDER
# =========================================
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# =========================================
# PROCESS SINGLE FILE
# =========================================
def process_file(file_name):

    input_path = os.path.join(INPUT_FOLDER, file_name)

    # Skip folders
    if not os.path.isfile(input_path):
        return "skipped", file_name

    ext = os.path.splitext(file_name)[1].lower()

    try:

        # =================================
        # MP4 → GIF
        # =================================
        if ext == ".mp4":

            output_name = (
                os.path.splitext(file_name)[0] + ".gif"
            )

            output_path = os.path.join(
                OUTPUT_FOLDER,
                output_name
            )

            # Skip existing
            if os.path.exists(output_path):
                return "skipped", file_name

            clip = VideoFileClip(input_path)

            # Resize
            clip = clip.resized(width=GIF_WIDTH)

            # Export GIF
            clip.write_gif(
                output_path,
                fps=GIF_FPS,
                logger=None
            )

            clip.close()

            return "converted", file_name

        # =================================
        # COPY IMAGES
        # =================================
        elif ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif"
        ]:

            output_path = os.path.join(
                OUTPUT_FOLDER,
                file_name
            )

            # Skip existing
            if os.path.exists(output_path):
                return "skipped", file_name

            shutil.copy2(
                input_path,
                output_path
            )

            return "copied", file_name

        return "ignored", file_name

    except Exception as e:

        return "failed", f"{file_name} | {e}"


# =========================================
# MAIN
# =========================================
if __name__ == "__main__":

    files = os.listdir(INPUT_FOLDER)

    converted = 0
    copied = 0
    skipped = 0
    failed = 0

    with ProcessPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = [
            executor.submit(process_file, file_name)
            for file_name in files
        ]

        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Processing media"
        ):

            status, result = future.result()

            if status == "converted":
                converted += 1

            elif status == "copied":
                copied += 1

            elif status == "skipped":
                skipped += 1

            elif status == "failed":
                failed += 1
                print(f"\n❌ {result}")

    # =====================================
    # SUMMARY
    # =====================================
    print("\n====================")
    print(f"🎬 Converted : {converted}")
    print(f"🖼️ Copied     : {copied}")
    print(f"⏭️ Skipped    : {skipped}")
    print(f"❌ Failed     : {failed}")
    print("====================")