import { requestJson } from "./client";
import type { SystemCapabilitiesView } from "./types";

export const operationsKeys = {
  capabilities: ["operations", "capabilities"] as const,
};

export function getSystemCapabilities(): Promise<SystemCapabilitiesView> {
  return requestJson<SystemCapabilitiesView>("/system/capabilities");
}
