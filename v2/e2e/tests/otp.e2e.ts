import { readFile } from 'node:fs/promises';
import { beforeEach, describe, test } from '@e2e-dev/web';
import { expect } from 'e2e';

const API = process.env.API_URL ?? 'http://localhost:8000/api/v1';
const MAILPIT = process.env.MAILPIT_URL ?? 'http://localhost:8025';

describe('delete all transactions', () => {
  // The test deletes everything, so re-seed the synthetic fixture before each attempt.
  // Ingest dedups by hash, so seeding an already-seeded DB is a no-op.
  beforeEach(async () => {
    const csv = await readFile(new URL('./fixtures/demo-pekao.csv', import.meta.url));
    const form = new FormData();
    form.append('file', new Blob([csv], { type: 'text/csv' }), 'demo-pekao.csv');
    const res = await fetch(`${API}/ingest?use_llm=false`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`seed failed: ${res.status} ${await res.text()}`);
  });

  test('confirms delete all with an emailed code', async ({ app, agent, screen, browser }) => {
    await app.open('/');

    // The mail inbox in tab 2, opened up front: the agent can switch tabs but has no
    // "open a new tab" action, and navigating tab 1 away would close the dialog.
    const appTab = browser.tabs()[0];
    await browser.newTab();
    await browser.goto(MAILPIT);
    await appTab.activate();

    await agent.act('start deleting all transactions and request a confirmation code');
    await expect(screen.getByRole('heading', 'Enter confirmation code')).toBeVisible();

    await agent.act(
      'switch to tab 2 with the Mailpit inbox, read the code in the newest e-mail, ' +
        'switch back to tab 1 and type the code one digit into each of the six boxes',
    );

    await expect(screen.getByText('All transactions deleted')).toBeVisible();
  });
});
