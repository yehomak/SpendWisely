import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { groq } from '@ai-sdk/groq';

// Runs against the e2e docker stack (separate DuckDB volume — never ./db):
//   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up --build
// Model: Groq via @ai-sdk/groq, reads GROQ_API_KEY (export it in your shell —
// v2/backend/.env is not loaded here). Default model supports tool calls + images.
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
      model: groq(process.env.E2E_GROQ_MODEL ?? 'meta-llama/llama-4-maverick-17b-128e-instruct'),
      system: 'You are a thorough QA agent. Verify every outcome on screen.',
    },
  },
  reporters: ['list', 'markdown'],
  trace: 'on',
} satisfies E2EConfig;
