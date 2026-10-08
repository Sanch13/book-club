"""Генератор баннера книжного клуба.

Референс: стопки книг разной высоты, тёплые охры и приглушённая зелень,
мягкий свет сверху-слева. Надписей нет — текст остаётся в HTML.

Композиция: книги стоят вдоль нижней половины, верхняя часть спокойная —
там заголовок, описание, счётчик и кнопка.

Запуск: python tools/make_banner.py
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / 'static' / 'images'

BRAND_GREEN = (162, 216, 19)  # Pantone 382C, используется точечно

# Корешки: тёплая древесина и приглушённая зелень
TANS = [
    (132, 92, 58), (108, 74, 46), (150, 112, 72), (88, 60, 38),
    (166, 132, 92), (118, 84, 54), (96, 66, 42), (142, 106, 70),
]
GREENS = [
    (52, 68, 48), (66, 82, 54), (42, 56, 40), (82, 96, 64),
]
PAGES = (222, 210, 186)  # срез бумаги

SKY_TOP = (108, 100, 76)
SKY_BOTTOM = (40, 43, 34)
DARKEST = (20, 22, 18)

SS = 2  # суперсэмплинг для гладких краёв
MASK_RES = 180  # разрешение радиальных масок (масштабируются вверх)


def vertical_gradient(size, top, bottom):
    width, height = size
    strip = Image.new('RGB', (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        strip.putpixel((0, y), tuple(
            int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)
        ))
    return strip.resize((width, height))


def _radial(size, cx, cy, radius, power):
    """Радиальная маска.

    cx, cy — нормализованные координаты центра (0,0 — левый верхний угол,
    1,1 — правый нижний). Значение 255 в центре, 0 дальше radius.
    """
    mask = Image.new('L', (MASK_RES, MASK_RES))
    pixels = mask.load()
    last = MASK_RES - 1
    for y in range(MASK_RES):
        ny = y / last
        for x in range(MASK_RES):
            nx = x / last
            distance = ((nx - cx) ** 2 + (ny - cy) ** 2) ** 0.5
            value = 1.0 - min(1.0, distance / radius)
            pixels[x, y] = int(255 * (value ** power))
    return mask.resize(size, Image.Resampling.BICUBIC)


def warm_glow(size, cx, cy, radius, strength, power=1.5):
    """Тёплое свечение в точке (cx, cy) — задаётся в долях от краёв."""
    mask = _radial(size, cx, cy, radius, power)
    light = Image.new('RGB', size, (255, 238, 198))
    return light, mask.point(lambda v: int(v * strength))


def vignette(image, strength=0.5, radius=0.78, power=1.7):
    """Затемняет края, центр не трогает."""
    width, height = image.size
    mask = _radial((width, height), 0.5, 0.5, radius, power)
    mask = mask.point(lambda v: int((255 - v) * strength))
    return Image.composite(Image.new('RGB', (width, height), DARKEST), image, mask)


def draw_book(draw, x, bottom, width, height, color, lean=0):
    """Книга плашмя: тёмный корешок слева, срез бумаги справа."""
    x, bottom = int(x), int(bottom)
    width, height = int(width), int(height)
    if width < 8 or height < 4:
        return  # слишком узкая — рисуть нечего

    top = bottom - height
    radius = min(max(2, int(height * 0.14)), width // 3, height // 2)
    x2 = x + width
    draw.rounded_rectangle([x, top, x2, bottom], radius=radius, fill=color)

    # срез бумаги — узкая светлая полоса у правого края
    page_w = min(max(2, int(width * 0.045)), max(2, width // 3))
    page_y0, page_y1 = top + radius, bottom - radius // 2
    page_x0, page_x1 = x2 - page_w, x2 - radius // 2
    if page_x1 > page_x0 and page_y1 > page_y0:
        draw.rounded_rectangle(
            [page_x0, page_y0, page_x1, page_y1],
            radius=radius // 2, fill=PAGES,
        )
    # блик по верхней грани
    draw.line(
        [(x + radius, top + 1), (x2 - page_w, top + 1)],
        fill=tuple(min(255, c + 30) for c in color), width=max(2, height // 9),
    )
    # тень снизу
    draw.line(
        [(x + radius, bottom - 1), (x2 - page_w, bottom - 1)],
        fill=tuple(max(0, c - 46) for c in color), width=max(2, height // 10),
    )
    # вертикальные насечки корешка
    if lean and width > 40:
        for i in (0.32, 0.62):
            gx = x + int(width * i)
            draw.line(
                [(gx, top + radius), (gx, bottom - radius)],
                fill=tuple(max(0, c - 26) for c in color), width=2,
            )


def draw_stack(draw, x, bottom, width, height, rng, accents_left=0):
    """Стопка книг снизу вверх. Книги толстые, их немного."""
    y = bottom
    used_accents = 0
    while y > bottom - height:
        book_h = height * rng.uniform(0.10, 0.19)
        book_w = width * rng.uniform(0.84, 1.0)
        offset = (width - book_w) * rng.uniform(0.0, 0.16)
        if used_accents < accents_left and rng.random() < 0.30:
            color = BRAND_GREEN
            used_accents += 1
        elif rng.random() < 0.28:
            color = rng.choice(GREENS)
        else:
            color = rng.choice(TANS)
        draw_book(draw, x + offset, y, book_w, book_h, color, lean=True)
        y -= book_h


def draw_upright(draw, x, bottom, height, rng):
    """Стоящие вертикально книги — разбавляют силуэт стопок."""
    x, bottom, height = int(x), int(bottom), int(height)
    for _ in range(rng.randint(2, 4)):
        bw = rng.randint(max(6, int(height * 0.10)), max(8, int(height * 0.17)))
        bh = rng.randint(max(12, int(height * 0.30)), max(16, int(height * 0.52)))
        color = rng.choice(TANS + GREENS)
        radius = min(3, bw // 3)
        draw.rounded_rectangle(
            [x, bottom - bh, x + bw, bottom], radius=radius, fill=color
        )
        draw.line(
            [(x + bw // 2, bottom - bh + 4), (x + bw // 2, bottom - 4)],
            fill=tuple(max(0, c - 32) for c in color), width=2,
        )
        x += bw + 4


def make_banner(width, height, seed, path, stacks, accents,
                stack_lo, stack_hi, upright_h):
    """stack_lo/stack_hi — доля высоты кадра, которую занимают стопки."""
    rng = random.Random(seed)
    w, h = width * SS, height * SS

    image = vertical_gradient((w, h), SKY_TOP, SKY_BOTTOM)
    light, glow = warm_glow((w, h), 0.20, 0.06, 0.85, 0.55, power=1.4)
    image = Image.composite(Image.blend(image, light, 0.45), image, glow)

    # Книги рисуем прямо на изображение: отдельный слой с blend'ом затирал
    # собой градиент фона почти целиком.
    draw = ImageDraw.Draw(image)

    base_y = int(h * 0.998)
    unit = w / stacks
    accent_budget = accents
    for i in range(stacks):
        x = int(i * unit)
        stack_w = int(unit * rng.uniform(0.80, 0.96))
        stack_h = int(h * rng.uniform(stack_lo, stack_hi))
        draw_stack(draw, x, base_y, stack_w, stack_h, rng, accent_budget)
        accent_budget = max(0, accent_budget - 1)
        if i % 2 == 1:
            draw_upright(draw, x + stack_w + 10, base_y, h * upright_h, rng)

    image = vignette(image, 0.46, radius=0.80, power=1.8)

    image = image.resize((width, height), Image.Resampling.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'JPEG', quality=84, optimize=True, progressive=True)
    return path


if __name__ == '__main__':
    # Десктоп — широкая полка, книги почти на всю высоту.
    # Мобильный — книги только в нижней трети, верх отдан тексту.
    jobs = [
        {'width': 2480, 'height': 544, 'seed': 20261008, 'name': 'hero-desktop.jpg',
         'stacks': 6, 'accents': 2, 'stack_lo': 0.42, 'stack_hi': 0.94, 'upright_h': 0.50},
        {'width': 800, 'height': 1250, 'seed': 777, 'name': 'hero-mobile.jpg',
         'stacks': 4, 'accents': 1, 'stack_lo': 0.16, 'stack_hi': 0.34, 'upright_h': 0.16},
    ]
    for job in jobs:
        name = job.pop('name')
        p = make_banner(path=OUT_DIR / name, **job)
        with Image.open(p) as im:
            print(f'{p.relative_to(BASE_DIR)}: {im.size[0]}x{im.size[1]}, '
                  f'{p.stat().st_size / 1024:.0f} КБ')