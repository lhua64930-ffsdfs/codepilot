# Patched minimatch with the legacy ESLint API

Legacy ESLint plugins expect `require("minimatch")` to be callable. Modern
minimatch exports a namespace instead. This private local adapter provides both
the old callable interface and modern named exports, delegating every operation
to the official `minimatch@11.0.1` package under the alias `minimatch-engine`.
No matching algorithm is copied, patched or implemented here. For the legacy
import rule, `makeRe()` supplies a test-only matcher rather than a regular
expression; its `test()` delegates to the patched engine. RegExp operations such
as `exec()` are intentionally unsupported. Do not use this adapter as a general
purpose substitute for the old regexp compiler.

The root npm override makes all lint consumers use the adapter, including the
TypeScript parser's modern named API. The underlying package version and
integrity are recorded in the lockfile and audited by npm under its real name.
Nothing is excluded from the audit. Neither package has installation scripts.

11.0.1 fixes GHSA-g3hv-75wg-m249. Run `npm run test:lint-compat`, `npm run lint`
and `npm audit` after dependency changes. Remove this adapter and override once
the lint dependency tree supports a patched minimatch version natively.
