export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  request_id: string;
  errors: Array<{ field: string | null; code: string; message: string }>;
}

export class ApiError extends Error {
  constructor(public readonly problem: ProblemDetail) {
    super(problem.detail);
    this.name = "ApiError";
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

function readCookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length);
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? "GET";
  const csrfToken = !["GET", "HEAD", "OPTIONS"].includes(method)
    ? readCookie("apm_csrf")
    : undefined;
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(csrfToken ? { "X-CSRF-Token": decodeURIComponent(csrfToken) } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError((await response.json()) as ProblemDetail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
