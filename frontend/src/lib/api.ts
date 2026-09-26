const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message = "Request failed") {
    super(message);
    this.status = status;
  }
}

function validationDetail(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null;
  const messages = detail.flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const item = entry as { loc?: unknown[]; msg?: unknown };
    if (typeof item.msg !== "string") return [];
    const field = Array.isArray(item.loc)
      ? item.loc.filter((part): part is string => typeof part === "string" && part !== "body").join(".")
      : "";
    return [field ? `${field}: ${item.msg}` : item.msg];
  });
  return messages.length ? messages.join("; ") : null;
}

function responseErrorMessage(status: number, bodyText: string): string {
  let detail: unknown;
  try {
    detail = (JSON.parse(bodyText) as { detail?: unknown }).detail;
  } catch {
    detail = undefined;
  }

  if (status >= 500 && status !== 503) {
    return "The server could not complete the request. Please try again later.";
  }
  if (typeof detail === "string") return detail;
  const validationMessage = validationDetail(detail);
  if (validationMessage) return validationMessage;
  if (status === 401) return "Your session has expired. Please log in again.";
  if (status === 403) return "You do not have permission to perform this action.";
  if (status === 404) return "The requested resource could not be found.";
  if (status === 409) return "The portfolio changed while you were working. Refresh and retry.";
  if (status === 422) return "Please check the submitted values and try again.";
  if (status === 503) return "This service is temporarily unavailable. Please try again later.";
  return "Request failed. Please try again.";
}

// Takes the access token as a param rather than fetching the session itself, so callers control timing.
export async function apiFetch<T>(
  path: string,
  accessToken: string,
  options: RequestInit = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${accessToken}`,
      },
    });
  } catch {
    throw new ApiError(0, "Could not reach the PortfolioPilot API. Check connectivity and try again.");
  }

  const bodyText = await res.text();

  if (!res.ok) {
    console.error(`API request failed: ${options.method ?? "GET"} ${path}`, {
      status: res.status,
    });
    throw new ApiError(res.status, responseErrorMessage(res.status, bodyText));
  }

  return bodyText ? (JSON.parse(bodyText) as T) : (undefined as T);
}
