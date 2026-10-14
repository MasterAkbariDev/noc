import { readFileSync, readdirSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET_BYTES = 512_000;
const ASSET_EXTENSIONS = new Set([".js", ".css"]);
const ASSETS_DIR = fileURLToPath(new URL("../dist/assets", import.meta.url));

function formatKb(bytes) {
  return `${(bytes / 1024).toFixed(2)} KB`;
}

const files = readdirSync(ASSETS_DIR)
  .filter((name) => ASSET_EXTENSIONS.has(extname(name)))
  .sort();

if (files.length === 0) {
  console.error(`No .js or .css files in ${ASSETS_DIR}. Run the build first.`);
  process.exit(1);
}

let total = 0;
for (const name of files) {
  const size = gzipSync(readFileSync(join(ASSETS_DIR, name))).length;
  total += size;
  console.log(`${name.padEnd(40)} ${formatKb(size).padStart(12)} gzipped`);
}

console.log(`${"total".padEnd(40)} ${formatKb(total).padStart(12)} gzipped (budget ${formatKb(BUDGET_BYTES)})`);

if (total > BUDGET_BYTES) {
  console.error("The gzipped bundle is over the budget.");
  process.exit(1);
}
