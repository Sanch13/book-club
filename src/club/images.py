"""Сжатие обложек книг.

Обложка — самая тяжёлая картинка на странице, а браузеру не нужно исходное
качество. Файл приводится к JPEG, уменьшается по большей стороне и
подбирается качество так, чтобы уложиться в лимит по размеру.

Принимаются только JPEG и PNG (PNG с прозрачностью заливается белым).
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

# Загружать можно только эти форматы
ALLOWED_FORMATS = {'JPEG', 'PNG'}
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

MAX_DIMENSION = 1200  # px по большей стороне
MAX_BYTES = 500 * 1024  # верхняя граница размера файла
QUALITY_START = 88
QUALITY_MIN = 55
QUALITY_STEP = 7
MIN_DIMENSION = 320  # ниже этого уменьшать бессмысленно

OUTPUT_FORMAT = 'JPEG'
OUTPUT_EXTENSION = 'jpg'


def needs_compression(field_file):
    """Уже сжатый и достаточно маленький файл трогать не нужно.

    Проверка идёт и по размеру, и по разрешению: небольшой по весу файл
    может оказаться картинкой в 4000px, которая тормозит загрузку страницы.
    """
    if not field_file:
        return False
    if not field_file.storage.exists(field_file.name):
        return False
    if field_file.size > MAX_BYTES:
        return True

    try:
        with Image.open(field_file) as image:
            if image.format != OUTPUT_FORMAT:
                return True
            return max(image.size) > MAX_DIMENSION
    except (UnidentifiedImageError, OSError):
        return False


def _flatten(image):
    """RGB-изображение: прозрачность заливается белым."""
    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGBA')
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        return background
    if image.mode != 'RGB':
        return image.convert('RGB')
    return image


def _encode(image, quality):
    buffer = BytesIO()
    image.save(
        buffer,
        format=OUTPUT_FORMAT,
        quality=quality,
        optimize=True,
        progressive=True,
    )
    return buffer.getvalue()


def compress_image(source, max_bytes=MAX_BYTES, max_dimension=MAX_DIMENSION):
    """Сжимает изображение и возвращает BytesIO с готовым JPEG."""
    try:
        image = Image.open(source)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError('Не удалось прочитать изображение.') from exc

    if image.format not in ALLOWED_FORMATS:
        raise ValidationError(
            'Поддерживаются только изображения в формате JPEG или PNG.'
        )

    image = _flatten(image)
    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    # Сначала опускаем качество — это дешевле, чем терять разрешение
    quality = QUALITY_START
    data = _encode(image, quality)
    while len(data) > max_bytes and quality > QUALITY_MIN:
        quality -= QUALITY_STEP
        data = _encode(image, quality)

    # Не влезло даже на минимальном качестве — уменьшаем картинку
    while len(data) > max_bytes and max(image.size) > MIN_DIMENSION:
        scale = 0.85
        image = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        data = _encode(image, QUALITY_MIN)

    buffer = BytesIO(data)
    buffer.seek(0)
    return buffer


def compressed_name(original_name):
    """Имя файла с расширением .jpg — после сжатия формат всегда JPEG."""
    base = (original_name or 'cover').rsplit('/', 1)[-1].rsplit('.', 1)[0]
    return f'{base}.{OUTPUT_EXTENSION}'