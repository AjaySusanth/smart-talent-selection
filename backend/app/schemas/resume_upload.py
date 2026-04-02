"""Schemas for resume upload operations."""

from pydantic import BaseModel, Field

from app.models.resume_upload import UploadStatus


class UploadResponse(BaseModel):
    """Response for a single file upload result."""

    id: str = Field("", description="Upload record UUID (empty if failed)")
    original_name: str = Field(..., description="Original filename")
    status: UploadStatus | None = Field(
        None, description="Current upload status (null if failed before DB insert)"
    )
    error_message: str | None = Field(
        None, description="Error details if upload failed"
    )

    model_config = {"from_attributes": True}


class BatchUploadResponse(BaseModel):
    """Response for batch resume uploads."""

    uploaded: list[UploadResponse] = Field(
        default_factory=list, description="Successfully uploaded files"
    )
    failed: list[UploadResponse] = Field(
        default_factory=list, description="Failed uploads with error details"
    )


class UploadStatusResponse(BaseModel):
    """Response for checking upload status."""

    id: str
    original_name: str
    status: UploadStatus
    error_message: str | None = None
    file_key: str | None = Field(None, description="Storage file key")

    model_config = {"from_attributes": True}
