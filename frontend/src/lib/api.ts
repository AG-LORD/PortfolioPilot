const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message = "Request failed") {
    super(message);
    this.status = status;
  }
}

// Takes the access token as a param rather than fetching the session itself, so callers control timing.
export async function apiFetch<T>(
  path: string,
  accessToken: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${accessToken}`,
    },
  });

  const bodyText = await res.text();

  if (!res.ok) {
    console.error(`API request failed: ${options.method ?? "GET"} ${path}`, {
      status: res.status,
      body: bodyText,
    });
    throw new ApiError(res.status, "Request failed. Please try again.");
  }

  return bodyText ? (JSON.parse(bodyText) as T) : (undefined as T);
}
