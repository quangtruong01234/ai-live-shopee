"""The real background-removal model (013 research R6, T033). Deselected by default; run with `-m matting_model`.

Needs the hand-downloaded file named by `MATTING_MODEL_PATH` (e.g. `models/matting/isnet-general-use.onnx`);
skipped without it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from ai_live.core.config import Settings
from fixtures.scene_builder import matting_image

pytestmark = pytest.mark.matting_model


@pytest.fixture
def model_path() -> Path:
    path = Settings().matting_model_path
    if path is None or not path.is_file():
        pytest.skip("MATTING_MODEL_PATH is empty or the model file is missing")
    return path


def test_cli_writes_a_mask_the_size_of_the_input(model_path: Path, tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    out = tmp_path / "mask.png"
    matting_image("noisy_bg").save(src)
    done = subprocess.run(
        [sys.executable, "-m", "ai_live.scene.matting"]
        + ["--model", str(model_path), "--in", str(src), "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    with Image.open(out) as mask:
        assert mask.mode == "L"
        assert mask.size == (320, 400)
