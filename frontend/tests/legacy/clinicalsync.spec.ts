import { test, expect, type Page } from '@playwright/test';

const password = process.env.DEMO_PASSWORD || 'ClinicalSync-demo-2026!';
test.beforeAll(async ({ request }) => {
  const login = await request.post('/api/auth/login', { data: { email: 'admin@clinicalsync.demo', password } });
  expect(login.ok()).toBeTruthy();
  const context = await login.json();
  const reset = await request.post('/api/demo/reset', { data: { confirmation: 'RESET SYNTHETIC DEMO' }, headers: { 'X-CSRF-Token': context.csrf_token, 'X-Workspace-ID': context.user.hospital_id } });
  expect(reset.ok()).toBeTruthy();
});

async function login(page: Page, account = 'network') {
  await page.goto('/legacy');
  await page.getByLabel('Demo account', { exact: true }).selectOption(`${account}@clinicalsync.demo`);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your day, in focus.' })).toBeVisible();
}

async function openMaya(page: Page) {
  await page.getByRole('link', { name: 'Patients', exact: true }).click();
  await page.getByRole('button', { name: 'Maya Bennett', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Maya Bennett', exact: true })).toBeVisible();
}

test('three-section workspace, readable chart, and progressively disclosed source history', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await login(page);
  await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link')).toHaveCount(3);
  await expect(page.getByRole('heading', { name: 'Records needing review' })).toBeVisible();
  await expect(page.locator('.incoming-list')).toBeVisible();
  await page.screenshot({ path: '../.test-artifacts/v2-overview-desktop.png', fullPage: true });
  await openMaya(page);
  await expect(page.getByText('500 mg · Twice daily', { exact: true })).toBeVisible();
  await expect(page.getByText('1000 mg · Twice daily', { exact: true })).toBeVisible();
  const row = page.locator('.chart-record').filter({ has: page.getByText('Penicillin allergy', { exact: true }) });
  await row.getByRole('button', { name: 'View details', exact: true }).click();
  await row.getByRole('button', { name: 'Source & history' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Record source', exact: true })).toBeVisible();
  await expect(dialog.locator('pre').first()).toBeHidden();
  await dialog.getByText('Technical details', { exact: true }).click();
  await dialog.getByText('Original source representation', { exact: true }).click();
  await expect(dialog.locator('pre').first()).toContainText('patientMrn');
  await dialog.getByText('Destination-compatible preview', { exact: true }).click();
  await expect(dialog.getByText('Preview only. No external EHR import has been performed.')).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: '../.test-artifacts/v2-patient-chart.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('patient registration, local record creation, and independent timelines', async ({ page }) => {
  await login(page);
  await page.getByRole('link', { name: 'Patients', exact: true }).click();
  await page.getByRole('button', { name: 'Add patient', exact: true }).click();
  await page.getByLabel('First name', { exact: true }).fill('Robin');
  await page.getByLabel('Last name', { exact: true }).fill('Hale');
  await page.getByLabel('Date of birth', { exact: true }).fill('1991-03-07');
  await page.getByLabel(/Hospital patient ID/).fill('NS-UI-NEW');
  await page.getByLabel(/This registration uses fictional development data/).check();
  await page.getByRole('button', { name: 'Check for matches' }).click();
  await page.getByRole('button', { name: 'Create patient', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Robin Hale', exact: true })).toBeVisible();
  const medications = page.locator('.chart-category').filter({ has: page.getByRole('heading', { name: /^Medications/ }) });
  await medications.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByLabel('Medication name', { exact: true }).fill('Development tablet');
  await page.getByLabel('Documented dose', { exact: true }).fill('20');
  await page.getByRole('button', { name: 'Add to hospital chart' }).click();
  await expect(page.getByText('Development tablet', { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click();
  await expect(page.getByText('Patient registered in this hospital workspace', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Development tablet/ })).toBeVisible();
  await openMaya(page);
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click();
  await expect(page.getByText(/Development tablet/)).toHaveCount(0);
  await page.getByLabel('Hospital workspace', { exact: true }).selectOption('riverside');
  await expect(page.getByRole('heading', { name: 'Your day, in focus.' })).toBeVisible();
  await page.getByRole('link', { name: 'Patients', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Robin Hale', exact: true })).toHaveCount(0);
});

test('vaccination history distinguishes a planned vaccination from administered reports', async ({ page }) => {
  await login(page); await openMaya(page);
  await page.getByRole('tab', { name: 'Vaccinations', exact: true }).click();
  await expect(page.getByText('Historical report · Dose 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add vaccination', exact: true }).click();
  await page.getByLabel('Vaccine name', { exact: true }).fill('Development planned vaccine');
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('planned');
  await page.getByLabel('Planned date', { exact: true }).fill('2027-01-02');
  await page.getByLabel(/Dose number/).fill('1');
  await page.getByRole('button', { name: 'Add to hospital chart' }).click();
  const planned = page.locator('.chart-record').filter({ has: page.getByText('Development planned vaccine', { exact: true }) });
  await expect(planned.getByText('Planned; not administered · Dose 1', { exact: true })).toBeVisible();
  await expect(planned.getByText('Completed', { exact: true })).toHaveCount(0);
});

test('recording, private editable draft, explicit approval, and receiving acknowledgment', async ({ page }) => {
  await login(page); await openMaya(page);
  await page.getByRole('tab', { name: 'Notes', exact: true }).click();
  await page.getByRole('button', { name: 'New note', exact: true }).click();
  await page.getByLabel('Note title', { exact: true }).fill('Recorded development follow-up');
  await page.getByLabel(/I confirm authorization and the required consent to record/).check();
  await page.getByRole('button', { name: 'Start recording', exact: true }).click();
  await expect(page.getByText('Recording in progress', { exact: true })).toBeVisible();
  await page.waitForTimeout(1200); // Capture an actual chunk from the browser’s fake audio device.
  await page.getByRole('button', { name: 'Stop recording', exact: true }).click();
  await expect(page.locator('.audio-preview audio')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Transcribe recording', exact: true })).toBeDisabled();
  await expect(page.getByText('Manual transcript mode', { exact: true })).toBeVisible();
  await page.locator('input[type=file]').setInputFiles({ name: 'synthetic-consultation.txt', mimeType: 'text/plain', buffer: Buffer.from('Subjective: Synthetic patient reports a scheduled follow-up.\nObjective: Recorded blood pressure is 120/80.\nAssessment: Clinician documented stable follow-up.\nPlan: Clinician plans a follow-up visit.') });
  await expect(page.getByLabel('Consultation transcript', { exact: true })).toHaveValue(/Synthetic patient reports a scheduled follow-up/);
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Draft saved privately');
  await page.reload();
  await page.getByRole('button', { name: /Recorded development follow-up.*Not approved or shared/ }).click();
  await page.getByRole('button', { name: 'Organize draft', exact: true }).click();
  await expect(page.getByRole('textbox', { name: 'Objective', exact: true })).toHaveValue('Recorded blood pressure is 120/80.');
  await page.getByRole('textbox', { name: 'Plan', exact: true }).fill('Clinician-reviewed synthetic follow-up plan.');
  const before = await (await page.request.get('/api/charts/NS-1001')).json();
  expect(before.records.some((record: any) => record.fields['Clinical concept'] === 'Recorded development follow-up')).toBeFalsy();
  await page.getByRole('button', { name: 'Approve note', exact: true }).click();
  await page.getByLabel(/I have reviewed and corrected every section/).check();
  await page.getByRole('button', { name: 'Approve and save note', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recorded development follow-up', exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recorded development follow-up approved by the clinician', exact: true })).toBeVisible();
  await page.getByLabel('Hospital workspace', { exact: true }).selectOption('riverside');
  await page.getByRole('link', { name: 'Clinical Review', exact: true }).click();
  await page.getByLabel('Search clinical updates', { exact: true }).fill('Recorded development follow-up');
  await expect(page.getByRole('heading', { name: 'Recorded development follow-up', exact: true }).last()).toBeVisible();
  await page.getByLabel('Reviewer note', { exact: true }).fill('Acknowledged the source note; no chart import.');
  await page.getByRole('button', { name: 'Acknowledge', exact: true }).click();
  await page.getByLabel('Review status', { exact: true }).selectOption('ACCEPTED');
  await expect(page.getByText('Acknowledged by Dr. Avery Chen', { exact: true })).toBeVisible();
  const local = await (await page.request.get('/api/local/patients/RG-8824')).json();
  expect(local.records.some((record: any) => record.fields['Clinical concept'] === 'Recorded development follow-up')).toBeFalsy();
});

test('cancelling a pending microphone request cannot stop or populate a newer recording', async ({ page }) => {
  await page.addInitScript(() => {
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    (window as any).captures = [];
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await getUserMedia(constraints);
      await new Promise<void>(release => (window as any).captures.push({ stream, release }));
      return stream;
    };
  });
  await login(page); await openMaya(page);
  await page.getByRole('tab', { name: 'Notes', exact: true }).click();
  await page.getByRole('button', { name: 'New note', exact: true }).click();
  await page.getByLabel(/I confirm authorization and the required consent to record/).check();
  await page.getByRole('button', { name: 'Start recording', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).captures.length)).toBe(1);
  await page.getByRole('button', { name: 'Back to notes', exact: true }).click();
  await page.getByRole('button', { name: 'New note', exact: true }).click();
  await page.getByLabel(/I confirm authorization and the required consent to record/).check();
  await page.getByRole('button', { name: 'Start recording', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).captures.length)).toBe(2);
  await page.evaluate(() => (window as any).captures[1].release());
  await expect(page.getByText('Recording in progress', { exact: true })).toBeVisible();
  await page.evaluate(() => (window as any).captures[0].release());
  await expect.poll(() => page.evaluate(() => (window as any).captures[0].stream.getTracks()[0].readyState)).toBe('ended');
  expect(await page.evaluate(() => (window as any).captures[1].stream.getTracks()[0].readyState)).toBe('live');
  await expect(page.getByText('Recording in progress', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel recording', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).captures[1].stream.getTracks()[0].readyState)).toBe('ended');
  await expect(page.locator('.audio-preview audio')).toHaveCount(0);
  await expect(page.getByText('Ready when you are', { exact: true })).toBeVisible();
});

test('medication change produces an understandable diff and a persisted deferral', async ({ page }) => {
  await login(page); await openMaya(page);
  const medication = page.locator('.chart-record').filter({ has: page.getByText('Metformin', { exact: true }) }).filter({ hasText: 'Northstar Medical Center' });
  await medication.getByRole('button', { name: 'View details', exact: true }).click();
  await medication.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Documented dose', { exact: true }).fill('750');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByText('750 mg · Twice daily', { exact: true })).toBeVisible();
  await page.getByLabel('Hospital workspace', { exact: true }).selectOption('riverside');
  await page.getByRole('link', { name: 'Clinical Review', exact: true }).click();
  await page.getByLabel('Search clinical updates', { exact: true }).fill('Metformin');
  const dose = page.locator('.comparison-row.changed').filter({ has: page.getByText('Dose', { exact: true }) });
  await expect(dose).toContainText('500'); await expect(dose).toContainText('750');
  await page.getByLabel('Reviewer note', { exact: true }).fill('Review with the original visit context.');
  await page.getByRole('button', { name: 'Defer', exact: true }).click();
  await page.getByLabel('Review status', { exact: true }).selectOption('DEFERRED');
  await expect(page.getByText('Deferred by Dr. Avery Chen', { exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel('Review status', { exact: true }).selectOption('DEFERRED');
  await expect(page.getByText('Deferred by Dr. Avery Chen', { exact: true })).toBeVisible();
});

test('administrator identity workflow and responsive navigation', async ({ page }) => {
  await login(page, 'admin');
  await page.getByRole('button', { name: 'Workspace tools', exact: true }).click();
  await page.getByLabel('Workspace tool', { exact: true }).selectOption('identity');
  await expect(page.getByText('Elise C. Carter', { exact: true })).toBeVisible();
  await page.getByLabel('Administrator evidence and review note', { exact: true }).fill('Insufficient synthetic matching evidence; keep charts separate.');
  await page.getByRole('button', { name: 'Reject match', exact: true }).click();
  await expect(page.getByText('Rejected', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
  await page.getByRole('link', { name: 'Patients', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Patients', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Maya Bennett', exact: true })).toBeVisible();
  await page.locator('.sidebar').evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
  await page.getByRole('button', { name: 'Dismiss notification', exact: true }).click();
  await page.screenshot({ path: '../.test-artifacts/v2-directory-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
