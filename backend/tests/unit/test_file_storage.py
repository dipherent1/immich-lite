from pathlib import Path

import pytest

from app.core.file_storage import LocalFileService


def test_save_and_read_roundtrip(tmp_path):
    svc = LocalFileService(str(tmp_path))
    rel = svc.save_upload(b"image-bytes", "photos/e1/p1.jpg")
    assert rel == "photos/e1/p1.jpg"
    assert svc.read(rel) == b"image-bytes"


def test_resolve_prevents_traversal(tmp_path):
    svc = LocalFileService(str(tmp_path))
    with pytest.raises(ValueError, match="path escapes"):
        svc._resolve("../../../etc/passwd")


def test_save_upload_prevents_traversal(tmp_path):
    svc = LocalFileService(str(tmp_path))
    with pytest.raises(ValueError, match="path escapes"):
        svc.save_upload(b"data", "../../escape.jpg")


def test_collect_images_only_extensions(tmp_path):
    svc = LocalFileService(str(tmp_path))
    svc.save_upload(b"a", "photos/e1/one.jpg")
    svc.save_upload(b"b", "photos/e1/two.png")
    svc.save_upload(b"c", "photos/e1/readme.txt")
    found = svc.collect_images("photos/e1", {".jpg", ".png"})
    assert found == ["photos/e1/one.jpg", "photos/e1/two.png"]


def test_collect_images_missing_dir(tmp_path):
    svc = LocalFileService(str(tmp_path))
    assert svc.collect_images("does-not-exist", {".jpg"}) == []


def test_copy_image(tmp_path):
    svc = LocalFileService(str(tmp_path))
    svc.save_upload(b"payload", "src/a.jpg")
    dst = svc.copy_image("src/a.jpg", "dst/b.jpg")
    assert dst == "dst/b.jpg"
    assert svc.read("dst/b.jpg") == b"payload"


def test_abs_path_is_under_root(tmp_path):
    svc = LocalFileService(str(tmp_path))
    resolved = Path(svc.abs_path("photos/x.jpg"))
    assert resolved.is_relative_to(tmp_path.resolve())


def test_read_missing_file_raises(tmp_path):
    svc = LocalFileService(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        svc.read("photos/nope.jpg")