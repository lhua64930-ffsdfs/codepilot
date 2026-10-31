import legacy from "./index.cjs";

export default legacy;
export const {
  minimatch, Minimatch, filter, match, makeRe, braceExpand,
  escape, unescape, GLOBSTAR, defaults, sep
} = legacy;
