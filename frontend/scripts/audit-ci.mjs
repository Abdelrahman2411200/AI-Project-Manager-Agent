import { spawnSync } from "node:child_process";

const npmCli = process.env.npm_execpath;
if (!npmCli) {
  process.stderr.write("npm_execpath is unavailable; run this check through npm run audit:ci\n");
  process.exit(1);
}

const audit = spawnSync(process.execPath, [npmCli, "audit", "--json"], {
  encoding: "utf8",
});

if (!audit.stdout) {
  process.stderr.write(audit.stderr || "npm audit produced no report\n");
  process.exit(1);
}

const report = JSON.parse(audit.stdout);
const vulnerabilities = report.vulnerabilities ?? {};

// This Vite application is a client-only SPA. It does not enable React Router
// RSC mode, server actions, or action execution on a server. Keep this exception
// advisory-specific so a new React Router finding still blocks the build.
const allowedAdvisories = new Map([
  [
    "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
    "React Router RSC/server-action CSRF is unreachable in this client-only SPA",
  ],
]);

const allowedPackages = new Set();
const blocked = [];

for (const [packageName, vulnerability] of Object.entries(vulnerabilities)) {
  if (!["high", "critical"].includes(vulnerability.severity)) {
    continue;
  }
  const advisoryEntries = vulnerability.via.filter((entry) => typeof entry === "object");
  const packageReferences = vulnerability.via.filter((entry) => typeof entry === "string");
  const advisoriesAllowed =
    advisoryEntries.length > 0 &&
    advisoryEntries.every((entry) => allowedAdvisories.has(entry.url));

  if (advisoriesAllowed && packageReferences.length === 0) {
    allowedPackages.add(packageName);
    continue;
  }
}

let changed = true;
while (changed) {
  changed = false;
  for (const [packageName, vulnerability] of Object.entries(vulnerabilities)) {
    if (allowedPackages.has(packageName) || !["high", "critical"].includes(vulnerability.severity)) {
      continue;
    }
    const entries = vulnerability.via;
    if (
      entries.length > 0 &&
      entries.every(
        (entry) =>
          (typeof entry === "string" && allowedPackages.has(entry)) ||
          (typeof entry === "object" && allowedAdvisories.has(entry.url)),
      )
    ) {
      allowedPackages.add(packageName);
      changed = true;
    }
  }
}

for (const [packageName, vulnerability] of Object.entries(vulnerabilities)) {
  if (
    ["high", "critical"].includes(vulnerability.severity) &&
    !allowedPackages.has(packageName)
  ) {
    blocked.push(`${vulnerability.severity}: ${packageName}`);
  }
}

if (blocked.length > 0) {
  process.stderr.write(`Blocking dependency findings:\n${blocked.join("\n")}\n`);
  process.exit(1);
}

for (const [url, rationale] of allowedAdvisories) {
  process.stdout.write(`Not applicable: ${url} — ${rationale}\n`);
}
process.stdout.write("No applicable High or Critical npm dependency finding.\n");
