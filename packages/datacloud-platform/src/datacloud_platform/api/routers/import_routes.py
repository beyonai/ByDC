"""OWL import route (factory pattern).

Prefix: ``/api/v1/ontologyBases``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform


def create_import_routes(platform: DatacloudPlatform) -> APIRouter:
    """Create a fresh APIRouter for OWL import.

    Args:
        platform: A fully configured DatacloudPlatform instance.

    Returns:
        APIRouter with prefix ``/api/v1/ontologyBases``, tags ``["import"]``.
    """
    router = APIRouter(prefix="/api/v1/ontologyBases", tags=["Import"])

    @router.post("/{base_id}/scenes/{scene_id}/import-owl")
    async def import_owl_to_scene(
        base_id: str,
        scene_id: str,
        file: UploadFile = File(...),  # noqa: B008
    ) -> Any:
        """Import OWL definitions from a ZIP file into a specific scene (LOCAL only).

        Expects multipart upload with Content-Type: application/zip.
        """
        try:
            zip_bytes = await file.read()
            result = platform.import_owl(base_id, scene_id, zip_bytes)
            return ok(data=result, message="imported")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.post("/{base_id}/import-owl")
    async def import_owl_default(
        base_id: str,
        file: UploadFile = File(...),  # noqa: B008
    ) -> Any:
        """Import OWL definitions from a ZIP file into the default scene (LOCAL only).

        If no default scene exists under the base, one is auto-created with
        scene_code=scene_name=\"default\".  The operation is idempotent — repeated
        calls with the same ZIP are safe.

        Expects multipart upload with Content-Type: application/zip.
        """
        try:
            zip_bytes = await file.read()
            # scene_id="" triggers auto-resolve of the default scene in import_owl
            result = platform.import_owl(base_id, "", zip_bytes)
            return ok(data=result, message="imported")
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    return router
