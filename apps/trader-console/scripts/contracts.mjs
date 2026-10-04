import openapiTS, { astToString } from "openapi-typescript";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const source = new URL("../../../contracts/trader-console/openapi.json", import.meta.url);
const destination = new URL("../src/generated/api.d.ts", import.meta.url);
// Resolve from this script, not the caller's working directory.
const output = astToString(await openapiTS(source));
if (process.argv.includes("--check")) {
  const existing = await readFile(destination, "utf8").catch(() => null);
  if (existing !== output) {
    console.error("Generated API types are missing or stale. Run npm run generate.");
    process.exitCode = 1;
  }
} else {
  await mkdir(new URL("../src/generated/", import.meta.url), { recursive: true });
  await writeFile(destination, output);
}
