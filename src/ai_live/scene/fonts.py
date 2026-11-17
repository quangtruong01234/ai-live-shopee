"""Fonts for the scene's cards and subtitles (research R3).

Vietnamese needs a font with every diacritic; Pillow's built-in bitmap font has none, so a missing font is a startup
error rather than a scene full of boxes.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# Bold first: the cards are read on a phone, thin strokes vanish after video compression.
_BOLD_CANDIDATES = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf")
_REGULAR_CANDIDATES = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "NotoSans-Regular.ttf")
# A sample with stacked diacritics: a font that cannot draw these is useless for Vietnamese.
_PROBE = "Ắ ẳ ỗ ự đ Đ"


class SceneFontError(RuntimeError):
    pass


def _font_dirs() -> list[Path]:
    dirs: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        dirs.append(windir / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
        dirs += [Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    return [d for d in dirs if d.is_dir()]


def _find(names: tuple[str, ...]) -> Path | None:
    dirs = _font_dirs()
    for name in names:
        for d in dirs:
            direct = d / name
            if direct.is_file():
                return direct
            found = next(d.rglob(name), None) if d.name != "Fonts" else None
            if found is not None:
                return found
    return None


def _usable(path: Path) -> bool:
    try:
        font = ImageFont.truetype(str(path), 20)
        font.getbbox(_PROBE)
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class SceneFonts:
    bold: Path
    regular: Path
    _cache: dict[tuple[bool, int], ImageFont.FreeTypeFont] = field(default_factory=dict, compare=False, repr=False)

    def get(self, size: int, *, bold: bool = True) -> ImageFont.FreeTypeFont:
        key = (bold, size)
        font = self._cache.get(key)
        if font is None:
            font = self._cache[key] = ImageFont.truetype(str(self.bold if bold else self.regular), size)
        return font


@lru_cache(maxsize=4)
def load_fonts(font_path: Path | None = None) -> SceneFonts:
    """`SCENE_FONT_PATH` if set, else a system font with Vietnamese diacritics; raises `SceneFontError`."""
    if font_path is not None:
        if not font_path.is_file() or not _usable(font_path):
            raise SceneFontError(f"SCENE_FONT_PATH {font_path} không mở được hoặc không phải font TrueType/OpenType")
        return SceneFonts(font_path, font_path)
    bold = _find(_BOLD_CANDIDATES)
    regular = _find(_REGULAR_CANDIDATES)
    if bold is None and regular is None:
        raise SceneFontError(
            "Không tìm thấy font có dấu tiếng Việt (Segoe UI, Arial hoặc DejaVu Sans) để vẽ thẻ sản phẩm; "
            "đặt SCENE_FONT_PATH tới một file .ttf hoặc tắt SCENE_ENABLED"
        )
    bold = bold or regular
    regular = regular or bold
    assert bold is not None and regular is not None
    return SceneFonts(bold, regular)
