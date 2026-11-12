import { NextResponse } from "next/server";

export function finnApiBaseUrl(): string | null {
  const configured = process.env.FINN_API_BASE_URL?.trim();
  if (!configured) {
    return process.env.NODE_ENV === "production" ? null : "http://localhost:8000";
  }
  try {
    const url = new URL(configured);
    if (
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash ||
      (process.env.NODE_ENV === "production" && url.protocol !== "https:")
    ) {
      return null;
    }
    return url.origin;
  } catch {
    return null;
  }
}

export function missingFinnApiConfiguration() {
  return NextResponse.json(
    {
      error: {
        code: "backend_not_configured",
        message: "Set FINN_API_BASE_URL to the deployed FINN API origin.",
      },
    },
    { status: 503 },
  );
}
