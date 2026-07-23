import { requestJson } from "./client";
import type { SessionView } from "./types";

export function getCurrentSession(): Promise<SessionView> {
  return requestJson<SessionView>("/auth/session");
}

export function login(email: string, password: string): Promise<SessionView> {
  return requestJson<SessionView>("/auth/session", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return requestJson<void>("/auth/session", { method: "DELETE" });
}
