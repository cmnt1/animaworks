export function mapAnimaStatusToAnim(status) {
  if (!status) return "idle";
  const value = typeof status === "object" ? status.state || status.status || "idle" : String(status);
  const lower = value.toLowerCase();
  if (lower === "not_found" || lower === "stopped") return "sleeping";
  if (lower.includes("bootstrap")) return "thinking";
  if (lower.includes("think") || lower.includes("process")) return "thinking";
  if (lower.includes("work") || lower.includes("busy") || lower.includes("running")) return "working";
  if (lower.includes("error") || lower.includes("fail")) return "error";
  if (lower.includes("sleep") || lower.includes("stop") || lower.includes("inactive")) return "sleeping";
  if (lower.includes("talk") || lower.includes("chat")) return "talking";
  if (lower.includes("report")) return "reporting";
  return "idle";
}
