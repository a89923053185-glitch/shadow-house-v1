import {
  AdminFilter,
  AdminPeriod,
  AdminSessionDetail,
  AdminSessionListResponse,
  ApiResponse,
  ContactCodeResponse,
  ContactVerifyResponse,
  SessionState,
} from "@/lib/types";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1").replace(/\/$/, "");

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Request failed");
  }
  return response.json() as Promise<T>;
}

export async function createSession(): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store"
  });
  return parseJson<ApiResponse>(response);
}

export async function resetSession(sessionId: string): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store"
  });
  return parseJson<ApiResponse>(response);
}

export async function sendMessage(sessionId: string, payload: { text?: string; choice?: string }): Promise<ApiResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload)
  });
  return parseJson<ApiResponse>(response);
}

export function recordBonusDownload(sessionId: string) {
  const url = `${API_BASE_URL}/sessions/${sessionId}/bonus-download`;
  if (typeof navigator !== "undefined" && navigator.sendBeacon) {
    navigator.sendBeacon(url);
    return;
  }

  void fetch(url, {
    method: "POST",
    cache: "no-store",
    keepalive: true,
  });
}

export function recordBlueprintOpen(sessionId: string) {
  const url = `${API_BASE_URL}/sessions/${sessionId}/blueprint-open`;
  if (typeof navigator !== "undefined" && navigator.sendBeacon) {
    navigator.sendBeacon(url);
    return;
  }

  void fetch(url, {
    method: "POST",
    cache: "no-store",
    keepalive: true,
  });
}

export async function getSessionState(sessionId: string): Promise<SessionState> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
    cache: "no-store"
  });
  return parseJson<SessionState>(response);
}

export async function requestPhoneCode(
  sessionId: string,
  payload: { display_name?: string; phone_number: string }
): Promise<ContactCodeResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/contact/request-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload)
  });
  return parseJson<ContactCodeResponse>(response);
}

export async function verifyPhoneCode(
  sessionId: string,
  payload: { phone_number: string; code: string }
): Promise<ContactVerifyResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/contact/verify-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload)
  });
  return parseJson<ContactVerifyResponse>(response);
}

type AdminQuery = {
  filter: AdminFilter;
  period: AdminPeriod;
  search?: string;
  startDate?: string;
  endDate?: string;
};

function buildAdminQuery(query: AdminQuery) {
  const params = new URLSearchParams();
  params.set("filter", query.filter);
  params.set("period", query.period);
  if (query.search?.trim()) params.set("search", query.search.trim());
  if (query.startDate) params.set("start_date", query.startDate);
  if (query.endDate) params.set("end_date", query.endDate);
  return params.toString();
}

export async function getAdminSessions(query: AdminQuery): Promise<AdminSessionListResponse> {
  const response = await fetch(`${API_BASE_URL}/admin/sessions?${buildAdminQuery(query)}`, {
    cache: "no-store"
  });
  return parseJson<AdminSessionListResponse>(response);
}

export async function getAdminSessionDetail(sessionId: string): Promise<AdminSessionDetail> {
  const response = await fetch(`${API_BASE_URL}/admin/sessions/${sessionId}`, {
    cache: "no-store"
  });
  return parseJson<AdminSessionDetail>(response);
}

export function getAdminExportUrl(kind: "xlsx" | "csv", query: AdminQuery) {
  return `${API_BASE_URL}/admin/export.${kind}?${buildAdminQuery(query)}`;
}

export function getAdminResultPrintUrl(sessionId: string) {
  return `${API_BASE_URL}/admin/sessions/${sessionId}/result-print`;
}
