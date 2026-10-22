export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function api(path, { signal } = {}) {
  return request(path, { signal });
}

export function saveInvestigatorSettings(body, csrf) {
  return request("/workbench/investigator/settings", { method: "PATCH", body, csrf });
}

async function request(path, { signal, method = "GET", body, csrf } = {}) {
  const timeout = AbortSignal.timeout(12000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  try {
    const response = await fetch(path, {
      method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json", "X-Sentinel-CSRF": csrf } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: combined,
      cache: "no-store",
      credentials: "omit",
    });
    let data;
    try {
      data = await response.json();
    } catch (error) {
      if (combined.aborted) throw error;
      throw new ApiError(response.status, "The server returned an unreadable response");
    }
    if (!response.ok) {
      const detail = typeof data.detail === "string"
        ? data.detail.slice(0, 250) : "The request could not be completed";
      throw new ApiError(response.status, `${detail} (${response.status})`);
    }
    return data;
  } catch (error) {
    if (timeout.aborted && !signal?.aborted)
      throw new ApiError(0, "Request timed out; refresh will retry");
    throw error;
  }
}
