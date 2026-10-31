import pickle
import sqlite3
import json

import pytest

from security_patches import apply_patches, verify_installed_patches


def test_patches_are_present_and_application_is_idempotent():
    verify_installed_patches()
    assert apply_patches() == 0


@pytest.mark.parametrize("version", ["5.6.3", "9.9.9"])
def test_unknown_source_or_version_fails_without_modifying_files(tmp_path, monkeypatch, version):
    import security_patches
    target = tmp_path / "diskcache" / "core.py"
    target.parent.mkdir()
    target.write_bytes(b"unexpected source")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"packages": [{"name": "diskcache", "version": "5.6.3", "files": [{
        "path": "diskcache/core.py", "upstream_sha256": "a" * 64, "patched_sha256": "b" * 64}]}]}), encoding="utf-8")
    class Distribution:
        def locate_file(self, path):
            return tmp_path / path
    distribution = Distribution()
    distribution.version = version
    monkeypatch.setattr(security_patches, "MANIFEST", manifest)
    monkeypatch.setattr(security_patches.importlib.metadata, "distribution", lambda _: distribution)
    with pytest.raises(RuntimeError):
        apply_patches()
    assert target.read_bytes() == b"unexpected source"


def test_default_disk_cache_round_trips_json_and_rejects_objects(tmp_path):
    from diskcache import Cache, JSONDisk
    with Cache(str(tmp_path)) as cache:
        assert isinstance(cache.disk, JSONDisk)
        cache.set("answer", {"values": [1, True, None, "中文"]})
        assert cache.get("answer") == {"values": [1, True, None, "中文"]}
        with pytest.raises(TypeError):
            cache.set("unsafe", object())


def test_tampered_cache_value_never_unpickles(tmp_path, monkeypatch):
    from diskcache import Cache
    from diskcache.core import MODE_PICKLE
    payload = pickle.dumps({"untrusted": True})
    with Cache(str(tmp_path)) as cache:
        cache.set("answer", {"safe": True})
        with sqlite3.connect(tmp_path / "cache.db") as db:
            db.execute("UPDATE Cache SET mode=?, value=?, filename=NULL", (MODE_PICKLE, sqlite3.Binary(payload)))
        def forbidden(*args, **kwargs):
            raise AssertionError("pickle decoding must never be called")
        monkeypatch.setattr(pickle, "load", forbidden)
        monkeypatch.setattr(pickle, "loads", forbidden)
        with pytest.raises(ValueError, match="pickle"):
            cache.get("answer")


def test_pickle_key_and_file_payload_are_rejected_before_io(tmp_path, monkeypatch):
    from diskcache import Disk
    from diskcache.core import MODE_PICKLE
    disk = Disk(str(tmp_path))
    def forbidden(*args, **kwargs):
        raise AssertionError("unsafe deserialization or file read attempted")
    monkeypatch.setattr(pickle, "load", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    with pytest.raises(ValueError, match="pickle"):
        disk.get(b"untrusted", False)
    with pytest.raises(ValueError, match="pickle"):
        disk.fetch(MODE_PICKLE, "untrusted.val", None, False)


@pytest.mark.parametrize("reference", ["http://127.0.0.1/private.png", "http://169.254.169.254/latest/meta-data", "https://example.com/image.png", "../../secret.png", "C:/secret.png"])
def test_ragas_image_contexts_cannot_access_network_or_files(reference, monkeypatch):
    from app.services.evals.ragas_runner import _ensure_ragas_compatibility
    _ensure_ragas_compatibility()
    from ragas.metrics.collections.multi_modal_faithfulness import util
    from ragas.prompt import multi_modal_prompt
    def forbidden(*args, **kwargs):
        raise AssertionError("context must not trigger network or host file IO")
    monkeypatch.setattr(util.requests, "get", forbidden)
    monkeypatch.setattr(util.os.path, "isfile", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    assert util._try_process_url(reference) is None
    assert util._try_process_local_file(reference) is None
    assert util.process_image_to_base64(reference) is None
    legacy = multi_modal_prompt.ImageTextPromptValue(items=[])
    assert legacy._try_process_allowed_url(reference) is None
    assert legacy._download_validate_and_encode(reference) is None
    assert legacy._try_process_local_file(reference) is None


def test_ragas_still_accepts_inline_images_and_rejects_invalid_or_large_data():
    from app.services.evals.ragas_runner import _ensure_ragas_compatibility
    _ensure_ragas_compatibility()
    from ragas.metrics.collections.multi_modal_faithfulness import util
    from ragas.prompt.multi_modal_prompt import ImageTextPromptValue
    # A one-pixel PNG, entirely supplied in the request rather than fetched.
    content = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9RkAAAAASUVORK5CYII="
    uri = "data:image/png;base64," + content
    assert util.process_image_to_base64(uri)["encoded_data"] == content
    assert ImageTextPromptValue(items=[])._try_process_base64_uri(uri)["encoded_data"] == content
    assert util._try_process_base64_uri("data:image/png;base64,AAAA=") is None
    assert util._try_process_base64_uri("data:image/png;base64," + "A" * (14 * 1024 * 1024)) is None


def test_noncanonical_padding_is_rejected_even_with_a_lenient_decoder(monkeypatch):
    from app.services.evals.ragas_runner import _ensure_ragas_compatibility
    _ensure_ragas_compatibility()
    from ragas.metrics.collections.multi_modal_faithfulness import util
    from ragas.prompt.multi_modal_prompt import ImageTextPromptValue
    # Python 3.11 accepts this redundant padding; emulate that on stricter
    # interpreters so the security boundary does not depend on Python version.
    monkeypatch.setattr(util.base64, "b64decode", lambda *args, **kwargs: b"\x00\x00\x00")
    value = "data:image/png;base64,AAAA="
    assert util._try_process_base64_uri(value) is None
    assert ImageTextPromptValue(items=[])._try_process_base64_uri(value) is None
