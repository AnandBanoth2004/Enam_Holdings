import { NextResponse } from "next/server";
import { finnApiBaseUrl } from "@/lib/server-config";

export async function GET() {
  const baseUrl = finnApiBaseUrl();
  if (!baseUrl) {
    return NextResponse.json({ status: "offline" }, { status: 503 });
  }

  try {
    const response = await fetch(`${baseUrl}/health/live`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2500),
    });

    return NextResponse.json(
      { status: response.ok ? "online" : "offline" },
      { status: response.ok ? 200 : 503 },
    );
  } catch {
    return NextResponse.json({ status: "offline" }, { status: 503 });
  }
}
