import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { createGroq } from '@ai-sdk/groq';
import { existsSync, readFileSync } from 'node:fs';

// GROQ_API_KEY: the shell env wins; otherwise take ONLY that key from the app's .env files
// (v2/.env, then v2/backend/.env) — nothing else from them is loaded.
function groqApiKey(): string | undefined {
  if (process.env.GROQ_API_KEY) return process.env.GROQ_API_KEY;
  for (const rel of ['../.env', '../backend/.env']) {
    const file = new URL(rel, import.meta.url);
    if (!existsSync(file)) continue;
    const m = readFileSync(file, 'utf8').match(/^\s*(?:export\s+)?GROQ_API_KEY\s*=\s*(.*)$/m);
    const value = m?.[1].trim().replace(/^(['"])(.*)\1$/, '$2');
    if (value) return value;
  }
  return undefined;
}

const groq = createGroq({ apiKey: groqApiKey() });

// Runs against the e2e docker stack (separate DuckDB volume — never ./db):
//   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up --build
// Model: Groq (GROQ_API_KEY, see above). Default openai/gpt-oss-120b: tool calls, text-only.
// Override with E2E_GROQ_MODEL; check access with `npx e2e doctor --check-model`.
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
      model: groq(process.env.E2E_GROQ_MODEL ?? 'openai/gpt-oss-120b'),
      system: 'You are a thorough QA agent. Verify every outcome on screen.',
    },
  },
  reporters: ['list', 'markdown'],
  trace: 'on',
} satisfies E2EConfig;
