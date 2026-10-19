# Brightpan AP web app

Next.js 16 + shadcn/ui frontend for the extraction API: upload, document view (original beside the extracted
fields and the money check), review queue with approve/reject, and the test results from `eval/results.csv`.

```bash
cp .env.example .env.local   # API_URL and the same API_TOKEN as the API's .env
npm install
npm run dev                  # http://127.0.0.1:3040
```

The browser only talks to this app. `src/app/api/[...path]/route.ts` forwards requests to the API server-side and
adds the bearer token, so the token never reaches the browser and admin endpoints are not reachable.
