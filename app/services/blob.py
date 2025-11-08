from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import os

ACCOUNT_URL = os.environ["AZURE_BLOB_ACCOUNT_URL"]
CONNECTION_STRING = os.environ["AZURE_BLOB_CONNECTION_STRING"]
CONTAINER = os.environ.get("AZURE_BLOB_CONTAINER", "event-media")

blob_service: BlobServiceClient = BlobServiceClient.from_connection_string(CONNECTION_STRING)

def blob_url(blob_name: str) -> str:
    return blob_service.get_blob_client(CONTAINER, blob_name).url

def make_read_sas(blob_name: str, minutes: int = 45) -> str:
    sas = generate_blob_sas(
        account_name=blob_service.account_name,
        container_name=CONTAINER,
        blob_name=blob_name,
        account_key=blob_service.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=minutes)
    )
    return f"{blob_url(blob_name)}?{sas}"

def make_write_sas(blob_name: str, minutes: int = 15, content_type: str | None = None) -> str:
    sas = generate_blob_sas(
        account_name=blob_service.account_name,
        container_name=CONTAINER,
        blob_name=blob_name,
        account_key=blob_service.credential.account_key,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.utcnow() + timedelta(minutes=minutes),
        content_type=content_type
    )
    return f"{blob_url(blob_name)}?{sas}"