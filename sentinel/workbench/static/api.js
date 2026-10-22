export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { signal } = {}) {
  const response = await fetch(path, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
    cache: "no-store",
    credentials: "omit",
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
