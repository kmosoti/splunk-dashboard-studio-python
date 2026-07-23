import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const target = process.env.SPLUNK_VISUAL_TARGET ?? "unconfigured";
const artifacts = process.env.SPLUNK_VISUAL_ARTIFACTS ?? path.join(root, "artifacts", target);
const reportPath = process.argv[2] ?? path.join(artifacts, "vision-report.json");
const contract = JSON.parse(fs.readFileSync(path.join(root, "qa", "vision-contract.json"), "utf8"));
const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
const overview = JSON.parse(fs.readFileSync(path.join(artifacts, "qa-overview.json"), "utf8"));
const deterministicFailures = new Set(overview.deterministic_failures ?? []);

if (report.schema_version !== "splunk-vision-qa-report/v1" || !Array.isArray(report.findings)) {
  throw new Error("Vision report must use splunk-vision-qa-report/v1 and contain findings[]");
}

for (const [index, finding] of report.findings.entries()) {
  for (const field of contract.finding.required) {
    if (!(field in finding)) throw new Error(`findings[${index}] is missing ${field}`);
  }
  if (!contract.categories.includes(finding.category)) {
    throw new Error(`findings[${index}] has unsupported category ${finding.category}`);
  }
  if (!contract.finding.severity.includes(finding.severity)) {
    throw new Error(`findings[${index}] has unsupported severity ${finding.severity}`);
  }
  if (typeof finding.confidence !== "number" || finding.confidence < 0 || finding.confidence > 1) {
    throw new Error(`findings[${index}] confidence must be between 0 and 1`);
  }
  const box = finding.bounding_box;
  if (!box || !contract.finding.bounding_box.every((field) => Number.isFinite(box[field]))) {
    throw new Error(`findings[${index}] has an invalid bounding_box`);
  }
  if (
    finding.deterministic_evidence !== null &&
    !deterministicFailures.has(finding.deterministic_evidence)
  ) {
    throw new Error(
      `findings[${index}] cites unknown deterministic evidence ${finding.deterministic_evidence}`,
    );
  }
}

const corroboratedErrors = report.findings.filter(
  (finding) => finding.severity === "error" && finding.deterministic_evidence !== null,
);
console.log(
  JSON.stringify({
    schema_version: "splunk-vision-qa-validation/v1",
    findings: report.findings.length,
    corroborated_errors: corroboratedErrors.length,
    advisory: corroboratedErrors.length === 0,
  }),
);
process.exitCode = corroboratedErrors.length > 0 ? 1 : 0;
