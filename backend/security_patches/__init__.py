"""Version- and hash-gated local fixes for two unpatched upstream advisories.

Run `python -m security_patches --apply` after installing requirements. These
are local source fixes, not upstream releases or advisory suppressions.
"""
import ast
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name("manifest.json")


def _replace_once(source, before, after):
    if source.count(before) != 1:
        raise RuntimeError("Upstream patch context changed; refusing to modify it")
    return source.replace(before, after, 1)


def _function(source, qualified, body):
    nodes = ast.parse(source).body
    for name in qualified.split("."):
        matches = [node for node in nodes if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name]
        if len(matches) != 1:
            raise RuntimeError(f"Unexpected upstream function: {qualified}")
        node = matches[0]
        nodes = node.body
    lines = source.splitlines(keepends=True)
    prefix = " " * (node.col_offset + 4)
    replacement = "".join(prefix + line + "\n" for line in body.splitlines())
    return "".join(lines[:node.body[0].lineno - 1]) + replacement + "".join(lines[node.end_lineno:])


def patched_source(relative, source):
    if relative == "diskcache/core.py":
        source = _replace_once(source,
            "            data = pickle.dumps(key, protocol=self.pickle_protocol)\n            result = pickletools.optimize(data)\n            return sqlite3.Binary(result), False",
            '            raise TypeError("Unsafe object keys are unsupported; use JSONDisk")')
        source = _replace_once(source, "            return pickle.load(io.BytesIO(key))",
            '            raise ValueError("Refusing unsafe pickle cache key")')
        source = _replace_once(source,
            "            result = pickle.dumps(value, protocol=self.pickle_protocol)\n\n            if len(result) < min_file_size:\n                return 0, MODE_PICKLE, None, sqlite3.Binary(result)\n            else:\n                filename, full_path = self.filename(key, value)\n                self._write(full_path, io.BytesIO(result), 'xb')\n                return len(result), MODE_PICKLE, filename, None",
            '            raise TypeError("Unsafe object values are unsupported; use JSONDisk")')
        source = _replace_once(source,
            "        elif mode == MODE_PICKLE:\n            if value is None:\n                with open(op.join(self._directory, filename), 'rb') as reader:\n                    return pickle.load(reader)\n            else:\n                return pickle.load(io.BytesIO(value))",
            '        elif mode == MODE_PICKLE:\n            raise ValueError("Refusing unsafe pickle cache value")')
        source = _replace_once(source, "def __init__(self, directory=None, timeout=60, disk=Disk, **settings):",
            "def __init__(self, directory=None, timeout=60, disk=JSONDisk, **settings):")
    else:
        if relative.endswith("collections/multi_modal_faithfulness/util.py"):
            names = ["_try_process_url", "_try_process_local_file"]
            base64_name = "_try_process_base64_uri"
        elif relative == "ragas/prompt/multi_modal_prompt.py":
            names = ["ImageTextPromptValue._try_process_allowed_url", "ImageTextPromptValue._download_validate_and_encode", "ImageTextPromptValue._try_process_local_file"]
            base64_name = "ImageTextPromptValue._try_process_base64_uri"
        else:
            raise RuntimeError("Unknown patch target")
        for name in names:
            source = _function(source, name, '"""CodePilot: image contexts never fetch URLs or read host files."""\nreturn None')
        source = _function(source, base64_name, '''"""CodePilot: accept only bounded, validated inline image data."""
if not isinstance(item, str) or len(item) > 14 * 1024 * 1024:
    return None
match = DATA_URI_REGEX.fullmatch(item)
if not match:
    return None
try:
    decoded = base64.b64decode(match.group(2), validate=True)
except (ValueError, binascii.Error):
    return None
if base64.b64encode(decoded).decode("ascii") != match.group(2):
    return None
if len(decoded) > 10 * 1024 * 1024:
    return None
return {"mime_type": match.group(1), "encoded_data": match.group(2)}''')
    compile(source, relative, "exec")
    return source


def _targets():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for package in manifest["packages"]:
        distribution = importlib.metadata.distribution(package["name"])
        if distribution.version != package["version"]:
            raise RuntimeError(f"Unexpected {package['name']} version; review local security patches")
        root = distribution.locate_file("").resolve()
        for item in package["files"]:
            path = distribution.locate_file(item["path"]).resolve()
            path.relative_to(root)
            yield distribution, item, path


def verify_installed_patches():
    for _, item, path in _targets():
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["patched_sha256"]:
            raise RuntimeError("Required dependency security patch missing or modified; run python -m security_patches --apply")


def apply_patches():
    pending = []
    for distribution, item, path in _targets():
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest == item["patched_sha256"]:
            continue
        if digest not in [item["upstream_sha256"], *item.get("prior_patched_sha256", [])]:
            raise RuntimeError(f"Unknown upstream file hash: {item['path']}; refusing to patch")
        patched = patched_source(item["path"], data.decode("utf-8")).encode("utf-8")
        if hashlib.sha256(patched).hexdigest() != item["patched_sha256"]:
            raise RuntimeError("Patched source differs from reviewed manifest")
        pending.append((distribution, item, path, patched))
    # Validate every target before modifying any package. Never change versions.
    records = {}
    for distribution, item, path, data in pending:
        path.write_bytes(data)
        record_entry = next(entry for entry in distribution.files if str(entry).endswith(".dist-info/RECORD"))
        record = distribution.locate_file(record_entry)
        records.setdefault(record, {})[item["path"]] = data
    for record, changed in records.items():
        rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
        for row in rows:
            if row[0] in changed:
                data = changed[row[0]]
                row[1] = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
                row[2] = str(len(data))
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(rows)
        record.write_text(output.getvalue(), encoding="utf-8")
    verify_installed_patches()
    return len(pending)
