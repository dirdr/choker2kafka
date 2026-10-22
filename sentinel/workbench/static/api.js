export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", token, body, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    headers,
    signal,
    cache: "no-store",
    credentials: "same-origin",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      response.status,
      "The server returned an unreadable response",
    );
  }
  if (!response.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail.slice(0, 250)
        : "The request could not be completed";
    throw new ApiError(response.status, `${detail} (${response.status})`);
  }
  return data;
}
