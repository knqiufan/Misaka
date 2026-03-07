"""Image storage and processing service.

Handles saving images from file picker and clipboard, generating thumbnails,
and managing the lifecycle of image attachments (cleanup when sessions are deleted).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from misaka.config import ATTACHMENTS_DIR, get_session_attachments_dir
from misaka.db.models import ImageAttachment, PendingImage

if TYPE_CHECKING:
    pass  # Avoid circular imports

logger = logging.getLogger(__name__)

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {"jpg", "jpeg", "png", "gif", "webp"}
THUMBNAIL_SIZE = (80, 80)


class ImageService:
    """Service for managing image attachments.

    Images are stored in ~/.misaka/attachments/{session_id}/ with thumbnails
    stored alongside originals with a "_thumb" suffix.
    """

    def __init__(self) -> None:
        self._ensure_attachments_dir()

    def _ensure_attachments_dir(self) -> None:
        """Ensure the attachments directory exists."""
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

    def _ensure_session_dir(self, session_id: str) -> Path:
        """Ensure the session attachments directory exists and return its path."""
        session_dir = get_session_attachments_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique ID for an image attachment."""
        return uuid.uuid4().hex[:12]

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _get_mime_type(file_path: str) -> str:
        """Detect MIME type from file path."""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith("image/"):
            return mime_type
        # Default to png if detection fails
        return "image/png"

    @staticmethod
    def _is_supported_image(file_path: str) -> bool:
        """Check if a file is a supported image format."""
        ext = Path(file_path).suffix.lower().lstrip(".")
        return ext in SUPPORTED_IMAGE_FORMATS

    def save_from_file(
        self,
        file_path: str,
        session_id: str,
    ) -> ImageAttachment | None:
        """Save an image from a file path to the session attachments directory.

        Args:
            file_path: Path to the source image file.
            session_id: ID of the session to associate the image with.

        Returns:
            ImageAttachment metadata, or None if the file is not a valid image.
        """
        if not os.path.exists(file_path):
            logger.warning("Image file not found: %s", file_path)
            return None

        if not self._is_supported_image(file_path):
            logger.warning("Unsupported image format: %s", file_path)
            return None

        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow not installed, cannot process images")
            return None

        session_dir = self._ensure_session_dir(session_id)
        image_id = self._generate_id()
        original_name = Path(file_path).name
        mime_type = self._get_mime_type(file_path)

        # Determine target extension
        ext = Path(file_path).suffix.lower()
        if not ext:
            ext = mimetypes.guess_extension(mime_type) or ".png"

        # Generate unique filename
        dest_filename = f"{image_id}{ext}"
        dest_path = session_dir / dest_filename

        # Copy and process the image
        try:
            with Image.open(file_path) as img:
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ("RGBA", "P"):
                    # Keep original mode for PNG/GIF to preserve transparency
                    if mime_type == "image/png":
                        pass
                    elif mime_type == "image/gif":
                        pass
                    else:
                        img = img.convert("RGB")

                width, height = img.size
                size_bytes = os.path.getsize(file_path)

                # Copy original file
                shutil.copy2(file_path, dest_path)

                # Generate thumbnail
                thumbnail_path = self.generate_thumbnail(dest_path, THUMBNAIL_SIZE)

            return ImageAttachment(
                id=image_id,
                file_path=str(dest_path),
                original_name=original_name,
                mime_type=mime_type,
                size_bytes=size_bytes,
                width=width,
                height=height,
                thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
                created_at=self._get_timestamp(),
            )

        except Exception as exc:
            logger.error("Failed to save image %s: %s", file_path, exc)
            return None

    def save_from_clipboard(
        self,
        image_data: bytes,
        session_id: str,
        format_hint: str = "png",
    ) -> ImageAttachment | None:
        """Save an image from clipboard data to the session attachments directory.

        Args:
            image_data: Raw image bytes (e.g., from clipboard).
            session_id: ID of the session to associate the image with.
            format_hint: Suggested format (default: png for screenshots).

        Returns:
            ImageAttachment metadata, or None if the data is not valid.
        """
        if not image_data:
            logger.warning("Empty clipboard image data")
            return None

        try:
            from PIL import Image
            import io
        except ImportError:
            logger.error("Pillow not installed, cannot process images")
            return None

        session_dir = self._ensure_session_dir(session_id)
        image_id = self._generate_id()

        # Determine format and extension
        format_lower = format_hint.lower()
        if format_lower == "jpeg":
            ext = ".jpg"
            mime_type = "image/jpeg"
        elif format_lower == "gif":
            ext = ".gif"
            mime_type = "image/gif"
        elif format_lower == "webp":
            ext = ".webp"
            mime_type = "image/webp"
        else:
            ext = ".png"
            mime_type = "image/png"
            format_lower = "png"

        dest_filename = f"{image_id}{ext}"
        dest_path = session_dir / dest_filename

        try:
            # Load image from bytes
            with Image.open(io.BytesIO(image_data)) as img:
                # Convert mode if necessary
                if img.mode == "RGBA" and format_lower == "jpeg":
                    img = img.convert("RGB")

                width, height = img.size

                # Save to destination
                img.save(dest_path, format=format_lower.upper())
                size_bytes = os.path.getsize(dest_path)

                # Generate thumbnail
                thumbnail_path = self.generate_thumbnail(dest_path, THUMBNAIL_SIZE)

            return ImageAttachment(
                id=image_id,
                file_path=str(dest_path),
                original_name=f"clipboard.{format_lower}",
                mime_type=mime_type,
                size_bytes=size_bytes,
                width=width,
                height=height,
                thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
                created_at=self._get_timestamp(),
            )

        except Exception as exc:
            logger.error("Failed to save clipboard image: %s", exc)
            return None

    def save_from_base64(
        self,
        base64_data: str,
        session_id: str,
        media_type: str = "image/png",
    ) -> ImageAttachment | None:
        """Save an image from base64-encoded data.

        Args:
            base64_data: Base64-encoded image data.
            session_id: ID of the session to associate the image with.
            media_type: MIME type of the image.

        Returns:
            ImageAttachment metadata, or None if the data is not valid.
        """
        try:
            image_data = base64.b64decode(base64_data)
        except Exception as exc:
            logger.error("Failed to decode base64 image: %s", exc)
            return None

        # Determine format from media type
        format_hint = media_type.split("/")[-1] if "/" in media_type else "png"
        return self.save_from_clipboard(image_data, session_id, format_hint=format_hint)

    def generate_thumbnail(
        self,
        image_path: Path | str,
        size: tuple[int, int] = THUMBNAIL_SIZE,
    ) -> Path | None:
        """Generate a thumbnail for an image.

        Args:
            image_path: Path to the source image.
            size: Target thumbnail size (width, height).

        Returns:
            Path to the generated thumbnail, or None if generation failed.
        """
        try:
            from PIL import Image
        except ImportError:
            logger.error("Pillow not installed, cannot generate thumbnails")
            return None

        image_path = Path(image_path)
        if not image_path.exists():
            logger.warning("Image not found for thumbnail: %s", image_path)
            return None

        # Generate thumbnail filename
        thumb_filename = f"{image_path.stem}_thumb{image_path.suffix}"
        thumb_path = image_path.parent / thumb_filename

        try:
            with Image.open(image_path) as img:
                # Create thumbnail maintaining aspect ratio
                img.thumbnail(size, Image.Resampling.LANCZOS)

                # Handle transparency for PNG/GIF
                if img.mode in ("RGBA", "P"):
                    img.save(thumb_path, format=image_path.suffix.lstrip(".").upper())
                else:
                    img.save(thumb_path, format=image_path.suffix.lstrip(".").upper())

            return thumb_path

        except Exception as exc:
            logger.error("Failed to generate thumbnail for %s: %s", image_path, exc)
            return None

    def get_thumbnail_bytes(self, thumbnail_path: str | Path) -> bytes | None:
        """Read thumbnail file and return its bytes.

        Args:
            thumbnail_path: Path to the thumbnail file.

        Returns:
            Thumbnail bytes, or None if the file cannot be read.
        """
        try:
            with open(thumbnail_path, "rb") as f:
                return f.read()
        except Exception as exc:
            logger.error("Failed to read thumbnail %s: %s", thumbnail_path, exc)
            return None

    def get_image_bytes(self, image_path: str | Path) -> bytes | None:
        """Read image file and return its bytes.

        Args:
            image_path: Path to the image file.

        Returns:
            Image bytes, or None if the file cannot be read.
        """
        try:
            with open(image_path, "rb") as f:
                return f.read()
        except Exception as exc:
            logger.error("Failed to read image %s: %s", image_path, exc)
            return None

    def get_image_base64(self, image_path: str | Path) -> str | None:
        """Read image file and return base64-encoded data.

        Args:
            image_path: Path to the image file.

        Returns:
            Base64-encoded string, or None if the file cannot be read.
        """
        data = self.get_image_bytes(image_path)
        if data:
            return base64.b64encode(data).decode("utf-8")
        return None

    def delete_image(self, image_path: str | Path) -> bool:
        """Delete an image and its thumbnail.

        Args:
            image_path: Path to the image file.

        Returns:
            True if deletion was successful, False otherwise.
        """
        image_path = Path(image_path)
        deleted = False

        try:
            if image_path.exists():
                image_path.unlink()
                deleted = True
        except Exception as exc:
            logger.error("Failed to delete image %s: %s", image_path, exc)

        # Try to delete thumbnail
        thumb_path = image_path.parent / f"{image_path.stem}_thumb{image_path.suffix}"
        try:
            if thumb_path.exists():
                thumb_path.unlink()
        except Exception as exc:
            logger.warning("Failed to delete thumbnail %s: %s", thumb_path, exc)

        return deleted

    def cleanup_session_images(self, session_id: str) -> int:
        """Delete all images for a session.

        Called when a session is deleted to clean up attachments.

        Args:
            session_id: ID of the session to clean up.

        Returns:
            Number of files deleted.
        """
        session_dir = get_session_attachments_dir(session_id)
        if not session_dir.exists():
            return 0

        count = 0
        try:
            for file_path in session_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        count += 1
                    except Exception as exc:
                        logger.warning("Failed to delete %s: %s", file_path, exc)

            # Remove the directory itself
            try:
                session_dir.rmdir()
            except Exception:
                pass  # Directory not empty or other error

        except Exception as exc:
            logger.error("Failed to cleanup session images for %s: %s", session_id, exc)

        logger.info("Cleaned up %d image files for session %s", count, session_id)
        return count

    def create_pending_image(
        self,
        file_path: str,
    ) -> PendingImage | None:
        """Create a PendingImage from a file path (for preview before sending).

        The image is copied to a temporary location and a thumbnail is generated
        for the preview bar.

        Args:
            file_path: Path to the source image file.

        Returns:
            PendingImage with thumbnail, or None if the file is not valid.
        """
        if not os.path.exists(file_path):
            logger.warning("Image file not found: %s", file_path)
            return None

        if not self._is_supported_image(file_path):
            logger.warning("Unsupported image format: %s", file_path)
            return None

        try:
            from PIL import Image
            import io
        except ImportError:
            logger.error("Pillow not installed, cannot process images")
            return None

        try:
            with Image.open(file_path) as img:
                width, height = img.size
                mime_type = self._get_mime_type(file_path)

                # Generate thumbnail in memory
                thumb_img = img.copy()
                thumb_img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

                # Convert thumbnail to bytes
                thumb_buffer = io.BytesIO()
                save_format = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
                thumb_img.save(thumb_buffer, format=save_format)
                thumbnail_bytes = thumb_buffer.getvalue()

                # Copy original to temp location
                temp_dir = ATTACHMENTS_DIR / "temp"
                temp_dir.mkdir(parents=True, exist_ok=True)

                temp_filename = f"{self._generate_id()}{Path(file_path).suffix}"
                temp_path = temp_dir / temp_filename
                shutil.copy2(file_path, temp_path)

                return PendingImage(
                    id=self._generate_id(),
                    temp_path=str(temp_path),
                    thumbnail=thumbnail_bytes,
                    original_name=Path(file_path).name,
                    mime_type=mime_type,
                    size_bytes=os.path.getsize(file_path),
                    width=width,
                    height=height,
                )

        except Exception as exc:
            logger.error("Failed to create pending image from %s: %s", file_path, exc)
            return None

    def create_pending_from_clipboard(
        self,
        image_data: bytes,
        format_hint: str = "png",
    ) -> PendingImage | None:
        """Create a PendingImage from clipboard data.

        Args:
            image_data: Raw image bytes.
            format_hint: Suggested format (default: png).

        Returns:
            PendingImage with thumbnail, or None if the data is not valid.
        """
        if not image_data:
            return None

        try:
            from PIL import Image
            import io
        except ImportError:
            logger.error("Pillow not installed, cannot process images")
            return None

        try:
            with Image.open(io.BytesIO(image_data)) as img:
                width, height = img.size

                # Determine format
                format_lower = format_hint.lower()
                if format_lower == "jpeg":
                    ext = ".jpg"
                    mime_type = "image/jpeg"
                elif format_lower == "gif":
                    ext = ".gif"
                    mime_type = "image/gif"
                elif format_lower == "webp":
                    ext = ".webp"
                    mime_type = "image/webp"
                else:
                    ext = ".png"
                    mime_type = "image/png"
                    format_lower = "png"

                # Generate thumbnail in memory
                thumb_img = img.copy()
                thumb_img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

                thumb_buffer = io.BytesIO()
                save_format = "PNG" if img.mode in ("RGBA", "P") else "JPEG"
                thumb_img.save(thumb_buffer, format=save_format)
                thumbnail_bytes = thumb_buffer.getvalue()

                # Save original to temp location
                temp_dir = ATTACHMENTS_DIR / "temp"
                temp_dir.mkdir(parents=True, exist_ok=True)

                temp_filename = f"{self._generate_id()}{ext}"
                temp_path = temp_dir / temp_filename

                # Convert and save
                save_img = img
                if img.mode == "RGBA" and format_lower == "jpeg":
                    save_img = img.convert("RGB")
                save_img.save(temp_path, format=format_lower.upper())

                return PendingImage(
                    id=self._generate_id(),
                    temp_path=str(temp_path),
                    thumbnail=thumbnail_bytes,
                    original_name=f"clipboard.{format_lower}",
                    mime_type=mime_type,
                    size_bytes=os.path.getsize(temp_path),
                    width=width,
                    height=height,
                )

        except Exception as exc:
            logger.error("Failed to create pending image from clipboard: %s", exc)
            return None

    def delete_pending_image(self, pending: PendingImage) -> bool:
        """Delete a pending image's temporary file.

        Args:
            pending: The PendingImage to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        try:
            temp_path = Path(pending.temp_path)
            if temp_path.exists():
                temp_path.unlink()
                return True
        except Exception as exc:
            logger.error("Failed to delete pending image %s: %s", pending.temp_path, exc)
        return False

    def finalize_pending_image(
        self,
        pending: PendingImage,
        session_id: str,
    ) -> ImageAttachment | None:
        """Move a pending image to the session attachments directory.

        Called when the user sends the message with attached images.

        Args:
            pending: The PendingImage to finalize.
            session_id: ID of the session to associate the image with.

        Returns:
            ImageAttachment metadata, or None if finalization failed.
        """
        temp_path = Path(pending.temp_path)
        if not temp_path.exists():
            logger.warning("Pending image temp file not found: %s", pending.temp_path)
            return None

        session_dir = self._ensure_session_dir(session_id)
        image_id = self._generate_id()

        # Determine destination filename
        ext = temp_path.suffix
        dest_filename = f"{image_id}{ext}"
        dest_path = session_dir / dest_filename

        try:
            # Move file from temp to session directory
            shutil.move(str(temp_path), dest_path)

            # Generate thumbnail in session directory
            thumbnail_path = self.generate_thumbnail(dest_path, THUMBNAIL_SIZE)

            return ImageAttachment(
                id=image_id,
                file_path=str(dest_path),
                original_name=pending.original_name,
                mime_type=pending.mime_type,
                size_bytes=pending.size_bytes,
                width=pending.width,
                height=pending.height,
                thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
                created_at=self._get_timestamp(),
            )

        except Exception as exc:
            logger.error("Failed to finalize pending image: %s", exc)
            return None

    def cleanup_temp_files(self) -> int:
        """Clean up all temporary files in the temp directory.

        Returns:
            Number of files deleted.
        """
        temp_dir = ATTACHMENTS_DIR / "temp"
        if not temp_dir.exists():
            return 0

        count = 0
        try:
            for file_path in temp_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        count += 1
                    except Exception as exc:
                        logger.warning("Failed to delete temp file %s: %s", file_path, exc)
        except Exception as exc:
            logger.error("Failed to cleanup temp files: %s", exc)

        return count
