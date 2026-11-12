import { NextResponse, type NextRequest } from "next/server";
import { finnApiBaseUrl, missingFinnApiConfiguration } from "@/lib/server-config";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const baseUrl = finnApiBaseUrl();
  if (!baseUrl) return missingFinnApiConfiguration();
  const workspaceId = process.env.FINN_WORKSPACE_ID;
  if (!workspaceId) {
    return NextResponse.json(
      {
        error: {
          code: "workspace_not_configured",
          message: "Set FINN_WORKSPACE_ID to a workspace that the authenticated user belongs to.",
        },
      },
      { status: 503 },
    );
  }

  const upstreamUrl = new URL(
    `/api/v1/network/${path.map(encodeURIComponent).join("/")}`,
    baseUrl,
  );
  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });
  if (!upstreamUrl.searchParams.has("workspace_id")) {
    upstreamUrl.searchParams.set("workspace_id", workspaceId);
  }

  try {
    const body = request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.text();
    const authorization = request.headers.get("authorization");
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: {
        Accept: "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
        ...(body ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "network_api_unavailable",
          message: "FINN could not reach the Network API. Check the backend service and try again.",
        },
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
