// Generate TypeScript types from the exported JSON Schema (contracts/schemas/match_bundle.schema.json).
// The bundle schema contains every contract the UI consumes. Run `npm run gen:types` after `make schemas`.
import { readFile, writeFile } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";

const SRC = new URL("../../contracts/schemas/match_bundle.schema.json", import.meta.url);
const OUT = new URL("../src/contracts/bundle.ts", import.meta.url);

const schema = JSON.parse(await readFile(SRC, "utf8"));
const ts = await compile(schema, "MatchBundle", {
  bannerComment: "/* Generated from contracts/schemas/match_bundle.schema.json. Do not edit: run `npm run gen:types`. */",
  additionalProperties: false,
});

if (process.argv.includes("--check")) {
  const current = await readFile(OUT, "utf8").catch(() => "");
  if (current !== ts) {
    console.error("web/src/contracts/bundle.ts is stale: run `npm run gen:types`");
    process.exit(1);
  }
  console.log("types OK");
} else {
  await writeFile(OUT, ts);
  console.log("wrote src/contracts/bundle.ts");
}
