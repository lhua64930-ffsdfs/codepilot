"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { createRequire } = require("node:module");
const { spawnSync } = require("node:child_process");
const legacy = require("minimatch");
const engine = require("minimatch-engine");

test("legacy callable interface and class-based ESLint selectors", () => {
  assert.equal(typeof legacy, "function");
  assert.equal(legacy("app/page.tsx", "**/*.tsx"), true);
  assert.equal(legacy("app/page.tsx", "**/*.js"), false);
  assert.equal(legacy(".config.js", "*.js", { dot: true }), true);
  assert.equal(legacy("src/index.ts", "*.ts", { matchBase: true }), true);
  assert.equal(legacy("src/Page.TSX", "**/*.tsx", { nocase: true }), true);
  assert.equal(new legacy.Minimatch("**/*.{ts,tsx}").match("lib/api.ts"), true);
  assert.equal(legacy.makeRe("**/*.tsx").test("app/page.tsx"), true);
  assert.deepEqual(legacy.match(["a.ts", "b.js"], "*.ts"), ["a.ts"]);
  assert.ok(new legacy.Minimatch("*.ts") instanceof engine.Minimatch);
  assert.equal(new legacy.Minimatch("*.ts").makeRe().test("a.ts"), true);
  assert.equal(legacy.makeRe("*.ts").test("a.js"), false);
  assert.equal(legacy.minimatch, engine.minimatch);
});

test("legacy import rule can use makeRe-based allow and forbid checks", () => {
  const { Linter } = require("eslint");
  const linter = new Linter({ configType: "eslintrc" });
  linter.defineRule("import/no-internal-modules", require("eslint-plugin-import").rules["no-internal-modules"]);
  const config = { parserOptions: { ecmaVersion: 2022, sourceType: "module" },
    rules: { "import/no-internal-modules": ["error", { forbid: ["**/private/**"] }] } };
  const denied = linter.verify("import value from './private/value.js';", config);
  assert.ok(denied.some((message) => message.ruleId === "import/no-internal-modules"));
  assert.deepEqual(linter.verify("import value from './public/value.js';", config), []);
});

test("ES module consumers get both legacy default and named exports", async () => {
  const esm = await import("minimatch");
  assert.equal(esm.default("components/card.tsx", "**/*.tsx"), true);
  assert.equal(esm.minimatch("a.ts", "*.ts"), true);
  assert.equal(new esm.Minimatch("*.ts").match("a.ts"), true);
});

test("TypeScript parser resolves the patched modern API", () => {
  const parserRequire = createRequire(require.resolve("@typescript-eslint/typescript-estree"));
  const modern = parserRequire("minimatch");
  assert.equal(modern.minimatch("src/a.ts", "**/*.ts", { dot: true }), true);
  assert.equal(parserRequire("minimatch/package.json").version, "11.0.1");
});

test("adversarial optimization patterns complete in a bounded child process", () => {
  const result = spawnSync(process.execPath, ["-e", `
    const { Minimatch } = require('minimatch-engine');
    new Minimatch('**/../'.repeat(24) + '*.js', { optimizationLevel: 2 });
  `], { cwd: process.cwd(), timeout: 5000, encoding: "utf8" });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
});
