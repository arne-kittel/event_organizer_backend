# uploads.py
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

bp = Blueprint("uploads", __name__, url_prefix="/api/uploads")

@bp.post("/azure/sas")
def presign_azure():
    # Auth prüfen (Admin!)
    data = request.get_json() or {}
    content_type: str = data.get("contentType", "")
    file_name: str = data.get("fileName", "upload")
    event_id: int = int(data["eventId"])
    # einfache Whitelist
    allowed = ("image/jpeg","image/png","image/webp","image/gif",
               "video/mp4","video/webm","video/quicktime")
    if content_type not in allowed:
        return jsonify({"error":"contentType not allowed"}), 400

    import uuid, re
    safe = re.sub(r"[^\w.\-]", "_", file_name)
    uid = uuid.uuid4().hex
    ext = safe.split(".")[-1] if "." in safe else ""
    blob_name = f"events/{event_id}/{uid}.{ext}" if ext else f"events/{event_id}/{uid}"

    expiry = datetime.utcnow() + timedelta(minutes=10)
    sas = generate_blob_sas(
        account_name=current_app.config["AZURE_STORAGE_ACCOUNT"],
        container_name=current_app.config["AZURE_STORAGE_CONTAINER"],
        blob_name=blob_name,
        account_key=current_app.config["AZURE_STORAGE_KEY"],
        permission=BlobSasPermissions(write=True, create=True),
        expiry=expiry,
        content_type=content_type,
    )
    upload_url = (
        f"https://{current_app.config['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net/"
        f"{current_app.config['AZURE_STORAGE_CONTAINER']}/{blob_name}?{sas}"
    )
    # public URL nur setzen, wenn Container public (Access Level: Blob)
    public_url = (
        f"{current_app.config['PUBLIC_BASE_URL']}/{blob_name}"
        if current_app.config.get("PUBLIC_BASE_URL")
        else None
    )
    return jsonify({"uploadUrl": upload_url, "blobName": blob_name, "publicUrl": public_url})
