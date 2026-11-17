import type { E2EConfig } from 'e2e';
import { web } from '@e2e-dev/web';
import { google } from '@ai-sdk/google';

// Runs against the e2e docker stack (separate DuckDB volume — never ./db):
//   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up --build
// Model: Gemini via @ai-sdk/google, reads GOOGLE_GENERATIVE_AI_API_KEY.
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
      model: google(process.env.E2E_GEMINI_MODEL ?? 'gemini-flash-latest'),
      system: 'You are a thorough QA agent. Verify every outcome on screen.',
    },
  },
  reporters: ['list', 'markdown'],
  trace: 'on',
} satisfies E2EConfig;
