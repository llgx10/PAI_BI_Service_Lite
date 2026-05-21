from google.cloud import storage
from google.oauth2 import service_account
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import io
import time
import os
from io import BytesIO
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import os
import json
import pickle

from google.cloud import storage
from google_auth_oauthlib.flow import InstalledAppFlow


class GCS:
    def __init__(self):
        oauth2_json_path = (
            "service_account\\client_secret_519276815665-"
            "evh54k3ouujjir7f7a4b9s43mc4pkcfu.apps.googleusercontent.com.json"
        )

        creds_path = "token.pickle"

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]

        # Load project ID
        with open(oauth2_json_path, "r") as file:
            oauth_data = json.load(file)
            self.project_id = oauth_data["installed"]["project_id"]

        # Load or create credentials
        if os.path.exists(creds_path):
            with open(creds_path, "rb") as token_file:
                credentials = pickle.load(token_file)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                oauth2_json_path,
                scopes=scopes
            )

            credentials = flow.run_local_server(port=0)

            with open(creds_path, "wb") as token_file:
                pickle.dump(credentials, token_file)

        # Create GCS client
        self.client = storage.Client(
            credentials=credentials,
            project=self.project_id
        )

    def upload_file(self, bucket_name, source_file_path, destination_blob_name):
        """
        Upload a file to GCS
        """
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        blob.upload_from_filename(source_file_path)

        print(
            f"Uploaded {source_file_path} "
            f"to gs://{bucket_name}/{destination_blob_name}"
        )

    def download_file(self, bucket_name, source_blob_name, destination_file_path):
        """
        Download a file from GCS
        """
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)

        blob.download_to_filename(destination_file_path)

        print(
            f"Downloaded gs://{bucket_name}/{source_blob_name} "
            f"to {destination_file_path}"
        )

    def list_files(self, bucket_name, prefix=None):
        """
        List files in a bucket
        """
        bucket = self.client.bucket(bucket_name)

        blobs = self.client.list_blobs(bucket, prefix=prefix)

        files = [blob.name for blob in blobs]

        return files

    def delete_file(self, bucket_name, blob_name):
        """
        Delete a file from GCS
        """
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        blob.delete()

        print(f"Deleted gs://{bucket_name}/{blob_name}")
    def upload_folder(
        self,
        bucket_name,
        local_folder_path,
        gcs_folder_path="",
        allowed_extensions=None,
        max_workers=16,
        skip_existing=False
    ):

        bucket = self.client.bucket(bucket_name)

        # =========================================
        # COLLECT FILES
        # =========================================
        upload_jobs = []

        for root, _, files in os.walk(local_folder_path):

            for file_name in files:

                local_file_path = os.path.join(root, file_name)

                # Extension filter
                if allowed_extensions:
                    ext = os.path.splitext(file_name)[1].lower()

                    if ext not in allowed_extensions:
                        continue

                # Preserve structure
                relative_path = os.path.relpath(
                    local_file_path,
                    local_folder_path
                ).replace("\\", "/")

                blob_path = f"{gcs_folder_path}/{relative_path}".strip("/")

                upload_jobs.append((local_file_path, blob_path))

        print(f"Found {len(upload_jobs)} files.")

        # =========================================
        # UPLOAD FUNCTION
        # =========================================
        def upload_single(job):

            local_file_path, blob_path = job

            blob = bucket.blob(blob_path)

            if skip_existing and blob.exists():
                return f"Skipped: {blob_path}"

            blob.chunk_size = 8 * 1024 * 1024  # 8MB

            blob.upload_from_filename(local_file_path)

            return f"Uploaded: {blob_path}"

        # =========================================
        # MULTITHREADED UPLOAD
        # =========================================
        with ThreadPoolExecutor(max_workers=max_workers) as executor:

            futures = [
                executor.submit(upload_single, job)
                for job in upload_jobs
            ]

            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Uploading"
            ):
                try:
                    result = future.result()

                except Exception as e:
                    print(f"ERROR: {e}")

        print("Upload complete.")