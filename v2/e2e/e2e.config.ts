import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { existsSync, readFileSync } from 'node:fs';

/**
 * The first of `names` set in the shell; otherwise that key alone from the app's .env
 * files (v2/.env, then v2/backend/.env) — nothing else from them is loaded.
 */
function apiKey(names: readonly string[]): string | undefined {
  for (const name of names) if (process.env[name]) return process.env[name];
  for (const rel of ['../.env', '../backend/.env']) {
    const file = new URL(rel, import.meta.url);
    if (!existsSync(file)) continue;
    const text = readFileSync(file, 'utf8');
    for (const name of names) {
      const m = text.match(new RegExp(`^\\s*(?:export\\s+)?${name}\\s*=\\s*(.*)$`, 'm'));
      const value = m?.[1].trim().replace(/^(['"])(.*)\1$/, '$2');
      if (value) return value;
    }
  }
  return undefined;
}

const google = createGoogleGenerativeAI({
  apiKey: apiKey(['GOOGLE_GENERATIVE_AI_API_KEY', 'GOOGLE_API_KEY']),
});

// Runs against the e2e docker stack (separate DuckDB volume — never ./db):
//   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up --build
// Model: Gemini Flash-Lite — free tier ~250K tokens/min and ~500 requests/day
// (Groq's free 8K tokens/min is smaller than one request with the Mailpit page).
// Override with E2E_GEMINI_MODEL; check access with `npx e2e doctor --check-model`.
export default {
  targets: [{
    engine: web(),
    app: {
      // Must be localhost (not 127.0.0.1): backend CORS allows http://localhost:3000 only.
      url: process.env.APP_URL ?? 'http://localhost:3000',
    },
  }],
  agents: {
    default: {
      model: google(process.env.E2E_GEMINI_MODEL ?? 'gemini-flash-lite-latest'),
      system: 'You are a thorough QA agent. Verify every outcome on screen.',
    },
  },
  // Free-tier model calls are rate limited; the OTP flow needs ~10 of them.
  timeout: 600_000,
  reporters: ['list', 'markdown'],
  trace: 'on',
} satisfies E2EConfig;
