// Server-side proxy to the extraction API. It adds the bearer token, so the browser never holds it.
// Only the exact routes the app uses are forwarded, only same-origin requests may change anything,
// and uploads are always tagged as "upload" (a browser can't pass itself off as email or eval).

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8040";
const ALLOWED_HOSTS = new Set((process.env.ALLOWED_HOSTS ?? "127.0.0.1:3040,localhost:3040").split(","));

const MAX_UPLOAD_BYTES = 21 * 1024 * 1024; // the API's 20 MB file limit plus form overhead
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const ROUTES: Record<string, RegExp[]> = {
  GET: [
    /^\/documents$/,
    new RegExp(`^/documents/${UUID}$`),
    new RegExp(`^/documents/${UUID}/file$`),
    new RegExp(`^/documents/${UUID}/pages/[1-9][0-9]{0,2}$`),
    /^\/review$/,
    /^\/results$/,
  ],
  POST: [/^\/documents$/, new RegExp(`^/documents/${UUID}/retry$`), new RegExp(`^/review/${UUID}$`)],
};

const deny = (status: number, detail: string) => Response.json({ detail }, { status });

function sameOrigin(request: Request): boolean {
  const site = request.headers.get("sec-fetch-site");
  if (site) return site === "same-origin";
  const origin = request.headers.get("origin");
  return origin !== null && ALLOWED_HOSTS.has(new URL(origin).host);
}

async function forward(request: Request, path: string[]): Promise<Response> {
  if (!ALLOWED_HOSTS.has(request.headers.get("host") ?? "")) return deny(400, "unexpected host");
  if (path.some((s) => s === "" || s === "." || s === ".." || /[\\/]/.test(s))) return deny(404, "not found");

  const target = new URL(path.map(encodeURIComponent).join("/"), `${API_URL}/`);
  target.search = new URL(request.url).search;
  if (!(ROUTES[request.method] ?? []).some((re) => re.test(target.pathname))) return deny(404, "not found");
  if (request.method !== "GET" && !sameOrigin(request)) return deny(403, "cross-site request refused");

  const token = process.env.API_TOKEN;
  if (!token) return deny(500, "API_TOKEN is not set for the web app (web/.env.local)");
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };

  let body: BodyInit | undefined;
  if (target.pathname === "/documents" && request.method === "POST") {
    // Refuse oversized bodies before buffering them (browsers always send Content-Length for form uploads).
    const length = Number(request.headers.get("content-length"));
    if (!Number.isFinite(length) || length <= 0) return deny(411, "upload needs a Content-Length");
    if (length > MAX_UPLOAD_BYTES) return deny(413, "file is larger than 20 MB");
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) return deny(400, "attach a file in the 'file' field");
    body = new FormData();
    body.append("file", file, file.name);
    body.append("source", "upload");
  } else if (target.pathname.endsWith("/retry")) {
    body = undefined; // no body
  } else if (request.method === "POST") {
    headers["Content-Type"] = "application/json";
    body = await request.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
  } catch {
    return deny(502, "The extraction API is not reachable. Start it on port 8040.");
  }
  const out = new Headers();
  for (const name of ["content-type", "content-disposition", "cache-control", "x-content-type-options"]) {
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
