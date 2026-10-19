// Server-side proxy to the extraction API. It adds the bearer token, so the browser never holds it,
// and only forwards the paths the app uses (admin endpoints are not reachable from the browser).

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8040";
const ALLOWED = /^(documents|review|results)(\/|$)/;

async function forward(request: Request, path: string[]): Promise<Response> {
  const joined = path.map(encodeURIComponent).join("/");
  if (!ALLOWED.test(joined)) {
    return Response.json({ detail: "not found" }, { status: 404 });
  }
  const token = process.env.API_TOKEN;
  if (!token) {
    return Response.json({ detail: "API_TOKEN is not set for the web app (web/.env.local)" }, { status: 500 });
  }
  const search = new URL(request.url).search;
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/${joined}${search}`, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "The extraction API is not reachable. Start it on port 8040." }, { status: 502 });
  }
  const out = new Headers();
  for (const name of ["content-type", "content-disposition"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export async function GET(request: Request, ctx: RouteContext<"/api/[...path]">) {
  return forward(request, (await ctx.params).path);
}

export async function POST(request: Request, ctx: RouteContext<"/api/[...path]">) {
  return forward(request, (await ctx.params).path);
}
