import { NextResponse, type NextRequest } from "next/server";
import { finnApiBaseUrl, missingFinnApiConfiguration } from "@/lib/server-config";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const baseUrl = finnApiBaseUrl();
  if (!baseUrl) return missingFinnApiConfiguration();
  const workspaceId = process.env.FINN_WORKSPACE_ID;
  const upstreamUrl = new URL(
    `/api/v1/push/${path.map(encodeURIComponent).join("/")}`,
    baseUrl,
  );
  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });
  if (workspaceId && !upstreamUrl.searchParams.has("workspace_id")) {
    upstreamUrl.searchParams.set("workspace_id", workspaceId);
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    const rawBody = await request.text();
    if (rawBody) {
      try {
        const body: unknown = JSON.parse(rawBody);
        if (
          workspaceId &&
          body !== null &&
          typeof body === "object" &&
          !Array.isArray(body) &&
          !("workspace_id" in body)
        ) {
          (body as Record<string, unknown>).workspace_id = workspaceId;
        }
        return await fetchUpstream(request, upstreamUrl, JSON.stringify(body));
      } catch (error) {
        if (error instanceof SyntaxError) {
          return NextResponse.json(
            { error: { code: "invalid_request", message: "Request body must be valid JSON." } },
            { status: 400 },
          );
        }
        throw error;
      }
    }
  }
  return fetchUpstream(request, upstreamUrl);
}

async function fetchUpstream(
  request: NextRequest,
  url: URL,
  body?: string,
) {
  const needsWorkspace =
    !url.pathname.includes("/results/") &&
    !url.pathname.endsWith("/classify");
  if (needsWorkspace && !process.env.FINN_WORKSPACE_ID) {
    return NextResponse.json(
      {
        error: {
          code: "workspace_not_configured",
          message: "Set FINN_WORKSPACE_ID to a seeded or authorized workspace ID.",
        },
      },
      { status: 503 },
    );
  }

  try {
    const authorization = request.headers.get("authorization");
    const upstream = await fetch(url, {
      method: request.method,
      headers: {
        Accept: "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    const responseBody = await upstream.text();
    return new NextResponse(responseBody, {
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
          code: "push_api_unavailable",
          message: "FINN could not reach the Push API. Check the backend service and try again.",
        },
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const PUT = proxy;
export const POST = proxy;
export const PATCH = proxy;
