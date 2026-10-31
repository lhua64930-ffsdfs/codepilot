# Reviewed local dependency security patches

Upstream releases `diskcache==5.6.3` and `ragas==0.4.3` have no published fixed
release for GHSA-w8v5-vhqr-4h9v / GHSA-95ww-475f-pr4f. This directory applies
small, deterministic source fixes to the installed packages. It is not a claim
that upstream published a fix, and does not alter package versions or suppress
advisories. Version-only scanners may still flag both packages.

After installing backend requirements, from `backend` run:

```powershell
.\.venv\Scripts\python.exe -m security_patches --apply
.\.venv\Scripts\python.exe -m security_patches
```

The application and Ragas adapter verify patched hashes before use. Unknown
versions, unknown original source hashes or modified patched files fail closed.
The installer validates all targets before writing; reapplying is idempotent.
Reinstalling dependencies may overwrite a patch; reapply and verify afterwards.
Do not change the manifest to accept a new version without reviewing its code.

## Changes

- DiskCache: default `Cache` serialization becomes `JSONDisk`; primitive Disk
  rejects non-primitive keys/values rather than pickling them. Both pickle key
  decoding and in-memory/on-disk pickle value decoding raise before IO or
  deserialization. JSON cache round trips remain supported. Existing pickle
  caches are intentionally unreadable and are never migrated by unpickling.
- Ragas: both Collections and legacy multimodal helpers never fetch URLs or
  read host files, even if old configuration flags are enabled. Image data must
  be provided inline as a validated, size-limited data URI. Text metrics and
  inline images remain available. Remote/local image-reference fetching is
  deliberately unsupported by this project, not controlled by a bypass flag.

`manifest.json` contains official PyPI wheel URLs and SHA-256 values, plus hashes
of each original and patched file. The originals were compared with the official
wheels before generating the manifest. Patches only apply when those identities
match. Installed RECORD hashes are updated to describe the modified files.
Original package copyright and Apache-2.0 license files are retained unchanged;
the modifications are maintained by this project, not endorsed by upstream.

Regression tests tamper with SQLite cache mode/value fields and check that no
pickle decoder runs, deny network/file IO while exercising image helpers, check
bounded inline data, JSON caching, idempotence and unknown-source rejection.

These patches address the cited code paths, not every possible vulnerability in
either library. Other projects or interpreters are not patched by this command.
