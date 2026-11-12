export type ApiHealth = {
  status: "online" | "offline";
};

export async function fetchApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  const response = await fetch("/api/health", {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    return { status: "offline" };
  }

  return (await response.json()) as ApiHealth;
}
