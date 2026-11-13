"""03.5 — Safe worker photo ingestion and owner/public access policy.

Images are decoded then rebuilt as metadata-free JPEGs. Filenames never derive
from user input. No original upload is persisted; files live outside MEDIA_ROOT.
"""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import re
import warnings

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import User, WorkerPortfolioPhoto, WorkerProfile
from .public_text import contains_public_contact


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PHOTOS = 10
MAX_IMAGE_PIXELS = 12_000_000
MAX_OUTPUT_SIDE = 1600
_KEY_PATTERN = re.compile(r'^worker-portfolio/[0-9a-f]{32}\.jpg$')
_IMAGE_TYPES = {
    '.jpg': ('JPEG', 'image/jpeg'),
    '.jpeg': ('JPEG', 'image/jpeg'),
    '.png': ('PNG', 'image/png'),
    '.webp': ('WEBP', 'image/webp'),
}


class PortfolioError(ValueError):
    """User-safe error; never include input bytes, paths or secret data."""


def private_portfolio_storage():
    """Never let a deployment accidentally serve private files via /media/."""
    private_root = Path(settings.ZEMIPRO_PRIVATE_MEDIA_ROOT).resolve()
    served_roots = (
        Path(settings.MEDIA_ROOT).resolve(),
        Path(settings.STATIC_ROOT).resolve(),
    )
    if any(private_root == root or private_root.is_relative_to(root)
           for root in served_roots):
        raise ImproperlyConfigured(
            'ZEMIPRO_PRIVATE_MEDIA_ROOT must be outside public media/static roots.',
        )
    return FileSystemStorage(
        location=str(private_root), base_url=None,
        file_permissions_mode=0o600, directory_permissions_mode=0o700,
    )


def sanitize_portfolio_image(uploaded):
    """Validate actual decoded content, then remove ALL original metadata."""
    if uploaded is None or not getattr(uploaded, 'name', ''):
        raise PortfolioError(_('Выберите фотографию.'))
    ext = Path(uploaded.name).suffix.lower()
    expected = _IMAGE_TYPES.get(ext)
    if expected is None or getattr(uploaded, 'content_type', '') != expected[1]:
        raise PortfolioError(_('Разрешены только фотографии JPEG, PNG и WebP.'))
    if uploaded.size <= 0 or uploaded.size > MAX_UPLOAD_BYTES:
        raise PortfolioError(_('Размер фотографии не должен превышать 5 МБ.'))
    try:
        uploaded.seek(0)
        raw = uploaded.read(MAX_UPLOAD_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise PortfolioError(_('Не удалось прочитать фотографию.')) from exc
    if len(raw) < 16 or len(raw) > MAX_UPLOAD_BYTES:
        raise PortfolioError(_('Размер фотографии не должен превышать 5 МБ.'))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as opened:
                if opened.format != expected[0]:
                    raise PortfolioError(_('Тип файла не соответствует его содержимому.'))
                if getattr(opened, 'n_frames', 1) != 1:
                    raise PortfolioError(_('Анимированные изображения не поддерживаются.'))
                if (opened.width <= 0 or opened.height <= 0
                        or opened.width * opened.height > MAX_IMAGE_PIXELS):
                    raise PortfolioError(_('Слишком большое разрешение фотографии.'))
                opened.verify()
            with Image.open(BytesIO(raw)) as opened:
                opened.load()
                oriented = ImageOps.exif_transpose(opened)
                if oriented.mode in ('RGBA', 'LA') or 'transparency' in oriented.info:
                    rgba = oriented.convert('RGBA')
                    normalized = Image.new('RGB', rgba.size, (255, 255, 255))
                    normalized.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    normalized = oriented.convert('RGB')
                normalized.thumbnail(
                    (MAX_OUTPUT_SIDE, MAX_OUTPUT_SIDE), Image.Resampling.LANCZOS,
                )
                output = BytesIO()
                # No exif, icc_profile, XMP, comment or original chunks passed.
                normalized.save(output, format='JPEG', quality=84, optimize=True)
                clean = output.getvalue()
                if len(clean) > MAX_UPLOAD_BYTES:
                    raise PortfolioError(_('Размер фотографии не должен превышать 5 МБ.'))
                return clean
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, PortfolioError):
            raise
        raise PortfolioError(_('Файл не является безопасной фотографией.')) from exc


def _active_worker(user):
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied
    owner = User.objects.select_for_update().get(pk=user.pk)
    if owner.is_blocked or not owner.is_active:
        raise PermissionDenied
    profile = WorkerProfile.objects.select_for_update().filter(user=owner).first()
    if profile is None:
        raise PortfolioError(_('Сначала создайте профиль мастера.'))
    return profile


def _check_sort_order(value):
    if type(value) is not int or not 0 <= value <= 999:
        raise PortfolioError(_('Недопустимый порядок фотографии.'))


@transaction.atomic
def add_own_portfolio_photo(user, uploaded, *, caption='', sort_order=0,
                            is_public=False, rights_confirmed=False):
    if rights_confirmed is not True:
        raise PortfolioError(_('Подтвердите право на использование фотографии.'))
    if type(is_public) is not bool:
        raise PortfolioError(_('Недопустимое значение публикации.'))
    _check_sort_order(sort_order)
    if len(caption) > 300:
        raise PortfolioError(_('Описание слишком длинное.'))
    if contains_public_contact(caption):
        raise PortfolioError(_('Контакты и внешние ссылки нельзя указывать в подписи.'))
    image_data = sanitize_portfolio_image(uploaded)
    worker = _active_worker(user)
    if WorkerPortfolioPhoto.objects.filter(worker=worker).count() >= MAX_PHOTOS:
        raise PortfolioError(_('Можно загрузить не более 10 фотографий.'))
    storage = private_portfolio_storage()
    key = f'worker-portfolio/{uuid4().hex}.jpg'
    saved_key = storage.save(key, ContentFile(image_data))
    try:
        photo = WorkerPortfolioPhoto.objects.create(
            worker=worker, file_key=saved_key, caption=caption.strip(),
            sort_order=sort_order, is_public=is_public,
            rights_confirmed_at=timezone.now(),
        )
    except Exception:
        storage.delete(saved_key)
        raise
    return photo


@transaction.atomic
def update_own_portfolio_photo(user, photo_id, *, caption, sort_order, is_public):
    worker = _active_worker(user)
    photo = WorkerPortfolioPhoto.objects.select_for_update().filter(
        pk=photo_id, worker=worker,
    ).first()
    if photo is None:
        raise PermissionDenied
    _check_sort_order(sort_order)
    if type(is_public) is not bool or len(caption) > 300:
        raise PortfolioError(_('Недопустимые данные фотографии.'))
    if contains_public_contact(caption):
        raise PortfolioError(_('Контакты и внешние ссылки нельзя указывать в подписи.'))
    photo.caption = caption.strip()
    photo.sort_order = sort_order
    photo.is_public = is_public
    photo.save(update_fields=['caption', 'sort_order', 'is_public'])
    return photo


@transaction.atomic
def delete_own_portfolio_photo(user, photo_id):
    worker = _active_worker(user)
    photo = WorkerPortfolioPhoto.objects.select_for_update().filter(
        pk=photo_id, worker=worker,
    ).first()
    if photo is None:
        raise PermissionDenied
    storage = private_portfolio_storage()
    key = photo.file_key
    if not _KEY_PATTERN.fullmatch(key):
        raise PortfolioError(_('Некорректный путь к фотографии.'))
    photo.delete()
    # Do not erase the file until the DB transaction commits. This prevents a
    # rolled-back DELETE from leaving a live row pointing at a missing file.
    transaction.on_commit(lambda: storage.delete(key))


def owner_portfolio(user):
    if not user.is_authenticated or user.pk is None or user.is_blocked or not user.is_active:
        raise PermissionDenied
    return WorkerPortfolioPhoto.objects.filter(
        worker__user_id=user.pk,
    ).order_by('sort_order', 'pk')


def portfolio_storage_key(photo):
    """Fail closed if a legacy/admin-edited DB key violates our private format."""
    if not _KEY_PATTERN.fullmatch(photo.file_key):
        raise PortfolioError(_('Некорректный путь к фотографии.'))
    return photo.file_key
