import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const context = { window: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root, "js/matcher.js"), "utf8"), context);

const { nameScore, idScore, search, prepareRecords } = context.window.OfacMatcher;
const full = "Juan Felipe Castro Maldonado";

const nameCases = [
  ["Juan Castro", full, true],
  ["Juan Felipe Castro", full, true],
  ["Felipe Castro", full, true],
  ["Felipe Maldonado", full, true],
  ["Castro Maldonado", full, true],
  ["Juan Maldonado", full, true],
  ["Juan Felipe Castro Maldonado", full, true],
  ["Pedro Perez", full, false],
  ["Juan", full, false],
  ["Ali Kazan", "Ahmad 'ALI", false],
  ["Ali Kazan", "Ali Muhammad KAZAN", true],
  [full, "Juan Castro", true],
  [full, "Juan Felipe Castro Maldonad", true],
  ["Juan Castro", "Juan Perez", false],
];

console.log("=== Nombre ===");
let failed = 0;
for (const [query, target, shouldMatch] of nameCases) {
  const { score } = nameScore(query, target);
  const matched = score >= 50;
  const ok = matched === shouldMatch;
  if (!ok) failed += 1;
  console.log(
    `${ok ? "OK" : "FAIL"} "${query}" → ${score.toFixed(1)}% ${matched ? "MATCH" : "no"}`
  );
}

console.log("\n=== ID ===");
const idCases = [
  ["10548414", "10548414", 10049, true],
  ["1054-8414", "10548414", 10049, true],
  ["10548415", "10548414", 10049, false],
  ["10049", "", 10049, true],
];
for (const [query, ident, interno, shouldMatch] of idCases) {
  const { score } = idScore(query, ident, interno);
  const matched = score >= 95;
  const ok = matched === shouldMatch;
  if (!ok) failed += 1;
  console.log(`${ok ? "OK" : "FAIL"} "${query}" → ${score.toFixed(1)}% ${matched ? "MATCH" : "no"}`);
}

const sample = prepareRecords([
  { idInterno: 1, nombre: full, identificacion: "123", lista: "OFAC" },
]);
const hits = search(sample, { nombre: "Juan Castro" });
if (hits.length !== 1) {
  failed += 1;
  console.log("FAIL search did not return the subset name");
} else {
  console.log(`OK search returned ${hits[0].riskScore.toFixed(1)}%`);
}

process.exit(failed ? 1 : 0);
