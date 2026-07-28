import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiBaseUrl, ApiError, requestJson, type ProblemDetail } from "./client";
import { isPermissionError } from "./errorUtils";
import type {
  RecommendationView,
  ReportStartView,
  ReportSummaryView,
  ReportType,
  ReportView,
} from "./types";

export const insightKeys = {
  all: ["insights"] as const,
  recommendations: (projectId: string) =>
    [...insightKeys.all, "recommendations", projectId] as const,
  reports: (projectId: string) =>
    [...insightKeys.all, "reports", projectId] as const,
  report: (reportId: string) => [...insightKeys.all, "report", reportId] as const,
};

export function listRecommendations(projectId: string): Promise<RecommendationView[]> {
  return requestJson(`/projects/${projectId}/recommendations`);
}

export function decideRecommendation(
  recommendation: RecommendationView,
  decision: "accept" | "dismiss" | "defer",
  reason: string,
  deferUntil?: string,
): Promise<RecommendationView> {
  return requestJson(
    `/recommendations/${recommendation.id}/decisions/${decision}`,
    {
      method: "POST",
      headers: {
        "If-Match": String(recommendation.row_version),
        "Idempotency-Key": `recommendation-${decision}-${crypto.randomUUID()}`,
      },
      body: JSON.stringify({
        reason: reason.trim() || null,
        defer_until: deferUntil || null,
      }),
    },
  );
}

export function listReports(projectId: string): Promise<ReportSummaryView[]> {
  return requestJson(`/projects/${projectId}/reports`);
}

export function startReport(
  projectId: string,
  reportType: ReportType,
  periodStart: string,
  periodEnd: string,
): Promise<ReportStartView> {
  return requestJson(`/projects/${projectId}/reports`, {
    method: "POST",
    headers: { "Idempotency-Key": `report-${crypto.randomUUID()}` },
    body: JSON.stringify({
      report_type: reportType,
      period_start: periodStart,
      period_end: periodEnd,
    }),
  });
}

export function getReport(reportId: string): Promise<ReportView> {
  return requestJson(`/reports/${reportId}`);
}

export async function downloadReport(
  reportId: string,
  format: "md" | "pdf" = "md",
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/reports/${reportId}/export.${format}`, {
    credentials: "include",
    headers: { Accept: format === "pdf" ? "application/pdf" : "text/markdown" },
  });
  if (!response.ok) {
    throw new ApiError((await response.json()) as ProblemDetail);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename =
    disposition.match(/filename="([^"]+)"/)?.[1] ?? `project-report.${format}`;
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function useRecommendations(projectId: string) {
  return useQuery({
    queryKey: insightKeys.recommendations(projectId),
    queryFn: () => listRecommendations(projectId),
    enabled: Boolean(projectId),
    retry: (count, error) => !isPermissionError(error) && count < 2,
  });
}

export function useRecommendationDecision(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      recommendation,
      decision,
      reason,
      deferUntil,
    }: {
      recommendation: RecommendationView;
      decision: "accept" | "dismiss" | "defer";
      reason: string;
      deferUntil?: string;
    }) => decideRecommendation(recommendation, decision, reason, deferUntil),
    onSuccess: (updated) => {
      queryClient.setQueryData<RecommendationView[]>(
        insightKeys.recommendations(projectId),
        (current) =>
          current?.map((item) => (item.id === updated.id ? updated : item)),
      );
    },
  });
}
