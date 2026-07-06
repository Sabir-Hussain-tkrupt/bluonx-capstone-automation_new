"""Project endpoints — /api/v1/projects"""

from uuid import UUID

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)

from app.core.auth import get_current_active_user
from app.services.geocoding import geocode_address
from app.core.file_validation import sanitize_filename, validate_upload
from app.core.storage import delete_file, get_signed_url, upload_file
from app.core.supabase_client import get_supabase
from app.models.common import SignedUrlResponse
from app.models.projects import (
    ProjectCreate,
    ProjectDocumentResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter()


# ── Helper: verify project exists and is not soft-deleted ────────────────


def _get_project_or_404(db: Client, project_id: UUID) -> dict:
    """Fetch a project by ID, raise 404 if not found or soft-deleted."""
    response = (
        db.table("projects")
        .select("*")
        .eq("id", str(project_id))
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return response.data


# ── Projects CRUD ────────────────────────────────────────────────────────


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    search: str | None = Query(default=None, description="Search by project name"),
    project_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    sort_by: str = Query(default="name", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all active projects with search, filter, sort, and pagination."""

    query = db.table("projects").select("*", count="exact").is_("deleted_at", "null")

    if search:
        query = query.ilike("name", f"%{search}%")

    if project_status:
        query = query.eq("status", project_status)

    # Sorting
    allowed_sort_columns = {
        "name", "city", "status", "budget", "start_date", "created_at",
    }
    if sort_by not in allowed_sort_columns:
        sort_by = "name"

    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    response = query.execute()

    return ProjectListResponse(
        items=response.data or [],
        total=response.count or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single project by ID."""
    return _get_project_or_404(db, project_id)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new project. created_by is set from the authenticated user."""
    project_data = project.model_dump()
    project_data["created_by"] = user["user_id"]

    # Convert Decimal fields to string for JSON serialization
    for key in ("budget", "latitude", "longitude"):
        if project_data.get(key) is not None:
            project_data[key] = str(project_data[key])

    # Convert date fields to string
    for key in ("start_date", "estimated_end_date"):
        if project_data.get(key) is not None:
            project_data[key] = project_data[key].isoformat()

    # Auto-geocode if address fields are provided
    address_fields = (project.address, project.city, project.state, project.zip_code)
    if any(f for f in address_fields):
        try:
            lat, lng = await geocode_address(
                project.address, project.city, project.state, project.zip_code,
            )
            if lat is not None and lng is not None:
                project_data["latitude"] = str(lat)
                project_data["longitude"] = str(lng)
        except Exception as exc:
            logger.warning("Geocoding failed for project %s: %s", project.name, exc)

    try:
        response = db.table("projects").insert(project_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for projects: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create project",
        )

    return response.data[0]


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project: ProjectUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a project."""
    existing = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(existing, resource="this project")

    update_data = project.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # Re-geocode if any address field changed
    _ADDRESS_FIELDS = {"address", "city", "state", "zip_code"}
    if _ADDRESS_FIELDS & set(update_data.keys()):
        try:
            merged_address = update_data.get("address", existing.get("address"))
            merged_city = update_data.get("city", existing.get("city"))
            merged_state = update_data.get("state", existing.get("state"))
            merged_zip = update_data.get("zip_code", existing.get("zip_code"))
            lat, lng = await geocode_address(merged_address, merged_city, merged_state, merged_zip)
            if lat is not None and lng is not None:
                update_data["latitude"] = lat
                update_data["longitude"] = lng
        except Exception as exc:
            logger.warning("Geocoding failed for project %s: %s", project_id, exc)

    # Convert Decimal fields to string for JSON serialization
    for key in ("budget", "latitude", "longitude"):
        if key in update_data and update_data[key] is not None:
            update_data[key] = str(update_data[key])

    # Convert date fields to string
    for key in ("start_date", "estimated_end_date"):
        if key in update_data and update_data[key] is not None:
            update_data[key] = update_data[key].isoformat()

    try:
        response = (
            db.table("projects")
            .update(update_data)
            .eq("id", str(project_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase update failed for projects/%s: %s", project_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return response.data[0]


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Soft-delete a project (sets deleted_at)."""
    _get_project_or_404(db, project_id)

    response = (
        db.table("projects")
        .update({"deleted_at": "now()"})
        .eq("id", str(project_id))
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )


# ── Archive / Unarchive ──────────────────────────────────────────────────


_BLOCKING_TASK_STATUSES = ("bidding", "evaluating", "awarded", "in_progress")


def _ensure_project_not_archived(project: dict, resource: str = "project") -> None:
    """Block write operations on archived projects."""
    if project.get("archived_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify {resource} on an archived project. Unarchive it first.",
        )


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Archive a project (hide from default view; preserves status)."""
    existing = _get_project_or_404(db, project_id)

    if existing.get("archived_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is already archived.",
        )

    if existing.get("status") == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active projects cannot be archived.",
        )

    blocking = (
        db.table("tasks")
        .select("id, name, status")
        .eq("project_id", str(project_id))
        .in_("status", list(_BLOCKING_TASK_STATUSES))
        .is_("deleted_at", "null")
        .execute()
    )

    if blocking.data:
        names = ", ".join(
            f"\"{t['name']}\" ({t['status']})" for t in blocking.data
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot archive: the following tasks are still in progress: "
                f"{names}. Complete or cancel them first."
            ),
        )

    try:
        response = (
            db.table("projects")
            .update({"archived_at": "now()", "archived_by": user["user_id"]})
            .eq("id", str(project_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase archive failed for projects/%s: %s", project_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return response.data[0]


@router.post("/projects/{project_id}/unarchive", response_model=ProjectResponse)
async def unarchive_project(
    project_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Unarchive a project (restores visibility; status untouched)."""
    existing = _get_project_or_404(db, project_id)

    if existing.get("archived_at") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project is not archived.",
        )

    try:
        response = (
            db.table("projects")
            .update({"archived_at": None, "archived_by": None})
            .eq("id", str(project_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase unarchive failed for projects/%s: %s", project_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Database rejected the data: {exc.message}",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return response.data[0]


PROJECT_BUCKET = "project-documents"

# Documents are either general reference material (selectable into bid packages)
# or a per-package Scope of Work (reached via the package, not the reference pool).
_DOCUMENT_KINDS = {"reference", "scope_of_work"}


# ── Project Documents ────────────────────────────────────────────────────


@router.get("/projects/{project_id}/documents", response_model=list[ProjectDocumentResponse])
async def list_project_documents(
    project_id: UUID,
    kind: str = Query(
        "reference",
        description="Filter by document_kind. Defaults to 'reference' so SoW "
        "documents stay out of the selectable reference pool.",
    ),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List documents for a project, filtered by document_kind (default reference)."""
    if kind not in _DOCUMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"document_kind must be one of {sorted(_DOCUMENT_KINDS)}",
        )

    _get_project_or_404(db, project_id)

    response = (
        db.table("project_documents")
        .select("*")
        .eq("project_id", str(project_id))
        .eq("document_kind", kind)
        .order("uploaded_at", desc=True)
        .execute()
    )

    return response.data or []


@router.post(
    "/projects/{project_id}/documents",
    response_model=ProjectDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_document(
    project_id: UUID,
    file: UploadFile = File(...),
    document_kind: str = Form("reference"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Upload a document for a project.

    Accepts multipart/form-data with:
    - file: the document file (PDF, JPEG, PNG, TIFF; max 50MB)
    - document_kind: 'reference' (default) or 'scope_of_work'. SoW documents
      are uploaded here during bid-package creation and referenced by
      bid_packages.scope_of_work_document_id.
    """
    if document_kind not in _DOCUMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"document_kind must be one of {sorted(_DOCUMENT_KINDS)}",
        )

    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project, resource="documents")

    # Read file bytes
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )

    # Validate file
    content_type = file.content_type or "application/octet-stream"
    filename = sanitize_filename(file.filename or "document")
    validate_upload(file_bytes, filename, content_type, PROJECT_BUCKET)

    # Upload to storage: {project_id}/{filename}, or {project_id}/sow/{filename} for SoW.
    prefix = f"{project_id}/sow" if document_kind == "scope_of_work" else str(project_id)
    storage_path = f"{prefix}/{filename}"
    upload_file(db, PROJECT_BUCKET, storage_path, file_bytes, content_type)

    # Insert project_documents row
    doc_data: dict = {
        "project_id": str(project_id),
        "file_name": filename,
        "file_path": storage_path,
        "file_type": content_type,
        "file_size": len(file_bytes),
        "document_kind": document_kind,
        "uploaded_by": user["user_id"],
    }

    response = db.table("project_documents").insert(doc_data).execute()

    if not response.data:
        delete_file(db, PROJECT_BUCKET, storage_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to save document record.",
        )

    return response.data[0]


@router.get(
    "/projects/{project_id}/documents/{document_id}/url",
    response_model=SignedUrlResponse,
)
async def get_project_document_url(
    project_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Generate a signed download URL for a project document (1hr expiry)."""
    _get_project_or_404(db, project_id)

    doc_resp = (
        db.table("project_documents")
        .select("file_path")
        .eq("id", str(document_id))
        .eq("project_id", str(project_id))
        .single()
        .execute()
    )
    if not doc_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    url = get_signed_url(db, PROJECT_BUCKET, doc_resp.data["file_path"])
    return SignedUrlResponse(url=url)


@router.delete(
    "/projects/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_document(
    project_id: UUID,
    document_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a project document from storage and database."""
    project = _get_project_or_404(db, project_id)
    _ensure_project_not_archived(project, resource="documents")

    # Fetch doc to get file_path
    doc_resp = (
        db.table("project_documents")
        .select("file_path")
        .eq("id", str(document_id))
        .eq("project_id", str(project_id))
        .single()
        .execute()
    )
    if not doc_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Delete from storage first
    delete_file(db, PROJECT_BUCKET, doc_resp.data["file_path"])

    # Delete DB row
    db.table("project_documents").delete().eq("id", str(document_id)).execute()
