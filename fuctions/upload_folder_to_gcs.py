import sys
sys.path.append ('./')
from config.gcs.gcs import GCS

pai_gcs=GCS()
bucket_name='pai-social-posts-data'
local_folder='UL PH nutrition_converted'
gcs_path='test'
pai_gcs.upload_folder(bucket_name,local_folder,gcs_path)