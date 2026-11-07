let token = "";
export function setToken(value: string) {
  token = value;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-Spill-Token": token } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
  const type = response.headers.get("content-type") ?? "";
  const data = type.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const detail = data?.detail;
    if (Array.isArray(detail))
      throw new Error(
        detail
          .map(
            (d: { loc?: string[]; msg?: string }) =>
              `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`,
          )
          .join(" · "),
      );
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status}).`,
    );
  }
  return data as T;
}
