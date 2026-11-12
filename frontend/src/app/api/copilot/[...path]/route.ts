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
    `/api/v1/copilot/${path.map(encodeURIComponent).join("/")}`,
    baseUrl,
  );
  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });
  if (request.method === "GET" || request.method === "DELETE") {
    if (!upstreamUrl.searchParams.has("workspace_id")) {
      upstreamUrl.searchParams.set("workspace_id", workspaceId);
    }
  }

  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD" && request.method !== "DELETE") {
    const rawBody = await request.text();
    if (rawBody) {
      try {
        const parsed: unknown = JSON.parse(rawBody);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          return NextResponse.json(
            { error: { code: "invalid_request", message: "Request body must be a JSON object." } },
            { status: 400 },
          );
        }
        (parsed as Record<string, unknown>).workspace_id = workspaceId;
        body = JSON.stringify(parsed);
      } catch {
        return NextResponse.json(
          { error: { code: "invalid_request", message: "Request body must be valid JSON." } },
          { status: 400 },
        );
      }
    }
  }

  try {
    const authorization = request.headers.get("authorization");
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: {
        Accept: "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(90000),
    });
    const responseBody = await upstream.text();
    return new NextResponse(responseBody || null, {
      status: upstream.status,
      headers: {
        ...(upstream.status !== 204
          ? { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }
          : {}),
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "copilot_api_unavailable",
          message: "FINN could not reach the Copilot service. Check the backend and try again.",
        },
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
