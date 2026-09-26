import { ApiError } from "@/lib/api";

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Please log in again.";
    if (error.status === 403) return "You do not have permission to perform this action.";
    if (error.status === 404) return error.message || "The requested resource could not be found.";
    if (error.status === 409 || error.status === 422 || error.status === 503) return error.message;
    if (error.status >= 500) return "The service is temporarily unavailable. Please retry later.";
    if (error.status === 0) return error.message;
    return error.message || fallback;
  }
  if (error instanceof TypeError) return "Could not reach the PortfolioPilot API. Check connectivity and try again.";
  return fallback;
}
