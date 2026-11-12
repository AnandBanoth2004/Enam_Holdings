import { NextResponse, type NextRequest } from "next/server";
import { finnApiBaseUrl, missingFinnApiConfiguration } from "@/lib/server-config";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const baseUrl = finnApiBaseUrl();
  if (!baseUrl) return missingFinnApiConfiguration();
  const upstreamUrl = new URL(
    `/api/v1/research/${path.map(encodeURIComponent).join("/")}`,
    baseUrl,
  );
  request.nextUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value);
  });

  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const rawBody = await request.text();
    if (rawBody) {
      try {
        const parsed: unknown = JSON.parse(rawBody);
        if (
          path.at(-1) === "report" &&
          parsed !== null &&
          typeof parsed === "object" &&
          !Array.isArray(parsed)
        ) {
          const workspaceId = process.env.FINN_WORKSPACE_ID;
          if (!workspaceId) {
            return NextResponse.json(
              {
                detail: {
                  code: "workspace_not_configured",
                  message: "Set FINN_WORKSPACE_ID to generate a saved research report.",
                },
              },
              { status: 503 },
            );
          }
          (parsed as Record<string, unknown>).workspace_id = workspaceId;
        }
        body = JSON.stringify(parsed);
      } catch {
        return NextResponse.json(
          {
            detail: {
              code: "invalid_request",
              message: "Request body must be valid JSON.",
            },
          },
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
        detail: {
          code: "research_api_unavailable",
          message: "FINN could not reach the research service. Check the backend and try again.",
        },
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
