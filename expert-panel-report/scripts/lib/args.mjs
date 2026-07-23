/**
 * args.mjs — shared CLI flag parser.
 *
 * Consolidates the three near-duplicate parseArgs() implementations that lived
 * in run.mjs / enforce-gate.mjs / render-with-watermark.mjs. They differed in
 * small, accidental ways (render-with-watermark did not understand --key=val;
 * run.mjs needed a separate `=== "true"` check for booleans). One parser here,
 * one behaviour.
 *
 * Grammar (both forms supported, interchangeable):
 *   --flag              → { flag: true }
 *   --key value         → { key: "value" }      (value must not start with "--")
 *   --key=value         → { key: "value" }      (value may contain "=" and "--")
 *   --key=              → { key: "" }
 *
 * Positional (non "--") tokens are NOT collected here. Callers that need
 * positionals (build-pdf.mjs) keep their own parser — this is flag-only.
 *
 * Sharp edges (degenerate but locked by test/test-args.mjs): a lone "--"
 * becomes an empty key ({ "": nextToken|true }), and "--=v" is NOT the equals
 * form (eqIdx===2 fails `> 2`) — it parses as the weird key "=v". Neither is a
 * supported input; do not rely on them.
 *
 * @param {string[]} [argv] - defaults to process.argv.slice(2)
 * @returns {Record<string, string|boolean>} parsed flags
 */
export function parseFlags(argv = process.argv.slice(2)) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const tok = argv[i];
    if (!tok.startsWith("--")) continue;

    // --key=value  (value is everything after the first "=", so "a=b=c" → "b=c")
    const eqIdx = tok.indexOf("=");
    if (eqIdx > 2) {
      const key = tok.slice(2, eqIdx);
      out[key] = tok.slice(eqIdx + 1);
      continue;
    }

    const key = tok.slice(2);
    // --key value  (only consume the next token if it isn't itself a flag)
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith("--")) {
      out[key] = next;
      i++;
    } else {
      out[key] = true;
    }
  }
  return out;
}
