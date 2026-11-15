import {test, expect, type Page} from '@playwright/test';

async function login(page: Page) {
  await page.goto('/');await page.getByLabel('Hospital staff email', {exact: true}).fill('emily@bridge.demo');
  await page.getByLabel('Password', {exact: true}).fill(process.env.BRIDGE_DEMO_PASSWORD || 'Demo-access-2026!');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('navigation', {name: 'Main navigation'})).toBeVisible();
}

async function findPatient(page: Page) {
  await page.getByLabel('Patient ID lookup', {exact: true}).fill('PT-DEMO-SARAH');
  await page.getByRole('button', {name: 'Find patient', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Upload visit', exact: true})).toBeVisible();
}

test('structured measurements support suggestions, custom names, units, zero and specific validation', async ({page}) => {
  await login(page);await findPatient(page);await page.getByRole('button', {name: 'Upload visit', exact: true}).click();
  const modal = page.getByRole('dialog'), reason = 'Fictional structured measurements ' + Date.now();
  await modal.getByLabel('Visit reason', {exact: true}).fill(reason);
  await expect(modal.getByLabel('Measured observations JSON')).toHaveCount(0);
  await modal.getByLabel('Blood pressure systolic', {exact: true}).fill('120');
  await modal.getByRole('button', {name: 'Upload to central server', exact: true}).click();
  await expect(modal.getByRole('alert')).toContainText('both systolic and diastolic');
  await modal.getByLabel('Blood pressure diastolic', {exact: true}).fill('80');

  const search = modal.getByRole('combobox', {name: 'Other measurement', exact: true});
  await search.fill('spo2');await expect(modal.getByRole('option').first()).toContainText('Oxygen saturation');
  await search.press('Enter');await expect(modal.getByLabel('Oxygen saturation (SpO2) value', {exact: true})).toBeFocused();
  await modal.getByLabel('Oxygen saturation (SpO2) value', {exact: true}).fill('100');
  await modal.getByLabel('Pain score value', {exact: true}).fill('0');
  await search.fill('hemoglobin');await modal.getByRole('option').first().click();
  await expect(modal.getByRole('button', {name: 'Blood count', exact: true})).toHaveAttribute('aria-expanded', 'true');
  await modal.getByLabel('Hemoglobin value', {exact: true}).fill('13.1');

  await search.fill('Skin temperature difference');await modal.getByRole('option', {name: /Use.*Skin temperature difference/}).click();
  await modal.getByLabel('Skin temperature difference value', {exact: true}).fill('0.8');
  await modal.getByLabel('Skin temperature difference unit', {exact: true}).fill('°C');
  await search.fill('Drainage appearance');await modal.getByRole('option', {name: /Use.*Drainage appearance/}).click();
  await modal.getByLabel('Drainage appearance value', {exact: true}).fill('None observed');
  await search.fill('creat');await search.press('Escape');
  await expect(modal.getByRole('listbox')).toHaveCount(0);await expect(modal).toBeVisible();await search.fill('');

  await page.setViewportSize({width: 390, height: 844});
  expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy();
  await modal.getByRole('button', {name: 'Vital signs', exact: true}).scrollIntoViewIfNeeded();
  await page.screenshot({path: '../.data/screenshots/measurement-fields-mobile.png'});
  await page.setViewportSize({width: 1280, height: 900});
  await search.fill('sodium');await expect(modal.getByRole('option').first()).toContainText('Sodium');
  await page.screenshot({path: '../.data/screenshots/measurement-suggestions.png'});
  await search.press('Escape');await search.fill('');

  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/hospital/visits') && response.request().method() === 'POST');
  await modal.getByRole('button', {name: 'Upload to central server', exact: true}).click();
  const response = await responsePromise;expect(response.status()).toBe(201);const result = await response.json();
  await expect(modal).toBeHidden();
  const version = await (await page.request.get('/api/versions/' + result.version_id)).json();
  expect(version.canonical.observations).toEqual({'Blood pressure': '120/80 mmHg', 'Oxygen saturation': '100%', 'Pain score': '0/10', Hemoglobin: '13.1 g/dL', 'Skin temperature difference': '0.8 °C', 'Drainage appearance': 'None observed'});
  await expect(page.locator('.record').filter({hasText: reason})).toContainText('100%');
});

test('editing measurements preserves original readings and supports recorded keys and keyboard lookup', async ({page}) => {
  await login(page);
  const auth = await (await page.request.get('/api/auth/me')).json();
  const observations = {BP: '119/79mmhg', SPO2: '97% on 2 L/min oxygen', Glucose: '5.4 mmol/L', Temperature: '36.7 C', Weight: '68.0 kg', 'Drainage score': 'trace; reviewed onsite'};
  const reason = 'Fictional legacy measurement preservation ' + Date.now();
  const created = await page.request.post('/api/hospital/visits', {headers: {'X-CSRF-Token': auth.csrf_token}, data: {
    patient_id: 'PT-DEMO-SARAH', payload: {patientId: 'PT-DEMO-SARAH', visitDate: '2026-11-15', chiefComplaint: reason,
      clinicalNotes: 'Fictional legacy note.', medications: [], allergies: [], observations, additionalInformation: {}},
  }});expect(created.status()).toBe(201);
  await findPatient(page);
  const record = page.locator('.record').filter({hasText: reason});await record.getByRole('button', {name: 'Add an update', exact: true}).click();
  const modal = page.getByRole('dialog'), search = modal.getByRole('combobox', {name: 'Other measurement', exact: true});
  await expect(modal.getByLabel('Blood pressure systolic', {exact: true})).toHaveValue('119');
  await expect(modal.getByLabel('Blood pressure diastolic', {exact: true})).toHaveValue('79');
  await expect(modal.getByLabel('Oxygen saturation (SpO2) value', {exact: true})).toHaveValue('97');
  await expect(modal).toContainText('Context: on 2 L/min oxygen');
  await search.fill('drain');await modal.getByRole('option').filter({hasText: 'Drainage score'}).click();
  await expect(modal.getByLabel('Drainage score value', {exact: true})).toBeFocused();
  await expect(modal.getByLabel('Drainage score value', {exact: true})).toHaveValue('trace; reviewed onsite');
  await search.fill('glu');await expect(modal.getByRole('option').first()).toContainText('Glucose');
  await search.press('ArrowDown');await expect(modal.getByRole('option').first()).toHaveAttribute('aria-selected', 'true');
  await search.press('ArrowDown');await expect(modal.getByRole('option').nth(1)).toHaveAttribute('aria-selected', 'true');
  await search.press('ArrowUp');await expect(modal.getByRole('option').first()).toHaveAttribute('aria-selected', 'true');
  await search.press('Enter');
  await expect(modal.getByLabel('Glucose value', {exact: true})).toBeFocused();
  await expect(modal.getByLabel('Glucose unit', {exact: true})).toHaveValue('mmol/L');
  await modal.getByLabel('Clinical notes', {exact: true}).fill('Fictional amended note; existing observations retained.');
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/hospital/visits') && response.request().method() === 'POST');
  await modal.getByRole('button', {name: 'Save new version', exact: true}).click();
  const response = await responsePromise;expect(response.status()).toBe(201);const result = await response.json();
  const version = await (await page.request.get('/api/versions/' + result.version_id)).json();
  expect(version.canonical.observations).toEqual(observations);expect(version.version).toBe(2);
});
