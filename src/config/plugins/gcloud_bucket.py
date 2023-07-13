import os

if os.environ.get('GCLOUD_MEDIA_BUCKET', False):
    DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
    GS_BUCKET_NAME = os.environ.get('GCLOUD_MEDIA_BUCKET')
    GS_FILE_OVERWRITE = True
    GS_CACHE_CONTROL = "max-age=2592000"
    GS_DEFAULT_ACL = "publicRead"