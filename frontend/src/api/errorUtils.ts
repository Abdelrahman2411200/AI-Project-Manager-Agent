import { ApiError } from "./client";

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.problem.detail : fallback;
}

export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.problem.status === 409;
}

export function isPermissionError(error: unknown): boolean {
  return error instanceof ApiError && [401, 403, 404].includes(error.problem.status);
}
