"use strict";

// Older ESLint plugins call require("minimatch") directly. All matching still
// runs in the official, patched engine; this adapter only restores that API.
const engine = require("minimatch-engine");
const legacy = Object.assign(
  (path, pattern, options) => engine.minimatch(path, pattern, options),
  engine
);

// v11 intentionally no longer compiles regexes. The legacy import plugin only
// calls .test() on makeRe's result; delegate that operation to the safe matcher.
// Do not reintroduce the old regex compiler or pretend to support RegExp.exec.
function testMatcher(matcher) {
  return Object.freeze({ test: (value) => matcher.match(value) });
}
class LegacyMinimatch extends engine.Minimatch {
  makeRe() { return testMatcher(this); }
}
legacy.Minimatch = LegacyMinimatch;
legacy.makeRe = (pattern, options) => testMatcher(new engine.Minimatch(pattern, options));

module.exports = legacy;
