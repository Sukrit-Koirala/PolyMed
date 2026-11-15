import {test, expect, type BrowserContext} from '@playwright/test';

const api = 'http://127.0.0.1:3200/api';
const password = process.env.BRIDGE_DEMO_PASSWORD || 'Demo-access-2026!';

async function staff(context: BrowserContext, login: string) {
  const signedIn = await context.request.post(api + '/auth/login', {data: {login, password}});
  expect(signedIn.ok()).toBeTruthy();
  const csrf = (await signedIn.json()).csrf_token;
  return async (path: string, data: unknown) => {
    const response = await context.request.post(api + path, {data, headers: {'X-CSRF-Token': csrf}});
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };
}

function native(format: string, day: string, observations: Record<string, string>, updated = false) {
  const medications = [{name: 'Ibuprofen', dose: '200', unit: 'mg', frequency: 'As documented'}];
  if (updated) medications.push({name: 'Mouth wash', dose: '10', unit: 'mL', frequency: 'As documented'});
  const allergies = updated ? ['Apple', 'Almonds'] : ['Apple'];
  const extra = {blood_group: 'A+', follow_up: {instructions: ['Bring records', 'Confirm contact details'], pain_score: 0, fasting: false}};
  return format === 'epic' ? {
    patientId: 'PT-DEMO-SARAH', visitDate: day, chiefComplaint: 'Fictional continuity review',
    clinicalNotes: updated ? 'Fictional updated visit notes.' : 'Fictional visit notes.', medications, allergies, observations, additionalInformation: extra,
  } : {
    personId: 'PT-DEMO-SARAH', encounter: {date: day, reason: 'Fictional older hospital report', note: 'Fictional report from another hospital.'},
    drugList: [], allergyList: [], measurements: observations, extraClinicalData: {},
  };
}

test('patient fields update live and show every source version in plain language', async ({page, browser}) => {
  test.setTimeout(60000);
  const memorial = await browser.newContext(), valley = await browser.newContext(), jordan = await browser.newContext();
  try {
    const a = await staff(memorial, 'emily@bridge.demo');
    const b = await staff(valley, 'daniel@bridge.demo');
    const correction = await staff(jordan, 'jordan@bridge.demo');
    await b('/hospital/visits', {patient_id: 'PT-DEMO-SARAH', payload: native('oracle', '2025-02-10', {blood_pressure: '110/70 mmHg'})});
    const current = await a('/hospital/visits', {patient_id: 'PT-DEMO-SARAH', payload: native('epic', '2026-11-15', {'Blood pressure': '118/78 mmHg'})});
    // Upload the oldest report last; its upload time must not make it the latest reading.
    await a('/hospital/visits', {patient_id: 'PT-DEMO-SARAH', payload: native('epic', '2024-01-01', {BP: '100/60 mmHg'})});

    await page.goto('/');
    await page.getByRole('button', {name: 'Patient', exact: true}).click();
    await page.getByLabel('Patient ID', {exact: true}).fill('PT-DEMO-SARAH');
    await page.getByLabel('Password', {exact: true}).fill(password);
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    const bloodPressure = page.getByRole('article', {name: 'Blood pressure data', exact: true});
    await expect(bloodPressure).toContainText('118/78 mmHg');
    await expect(page.locator('.clinical-summary pre')).toHaveCount(0);
    const allergies = page.getByRole('article', {name: 'Allergies data', exact: true});
    const medications = page.getByRole('article', {name: 'Medications data', exact: true});
    await expect(allergies.locator('.human-list')).toContainText('Apple');
    await allergies.locator('summary').click();
    await expect(allergies.locator('details')).not.toHaveAttribute('open');

    await correction('/hospital/visits', {patient_id: 'PT-DEMO-SARAH', visit_id: current.visit_id, expected_version: 1,
      payload: native('epic', '2026-11-15', {bloodPressure: '120/80 mmHg'}, true)});
    await expect(bloodPressure).toContainText('120/80 mmHg', {timeout: 15000});
    await expect(bloodPressure).toContainText('Dr. Jordan Lee');
    await expect(allergies.locator('details')).not.toHaveAttribute('open');
    await allergies.locator('summary').click();
    await expect(allergies.locator('.human-list > li')).toContainText(['Apple', 'Almonds']);
    await expect(medications).toContainText('Ibuprofen');
    await expect(medications).toContainText('Mouth wash');
    await expect(page.getByRole('article', {name: 'Follow up · Instructions data', exact: true})).toContainText('Bring records');
    await expect(page.getByRole('article', {name: 'Follow up · Pain score data', exact: true})).toContainText('0');
    await expect(page.getByRole('article', {name: 'Follow up · Fasting data', exact: true})).toContainText('No');
    await page.locator('.clinical-summary').scrollIntoViewIfNeeded();
    await page.screenshot({path: '../.data/screenshots/patient-readable-summary.png'});

    await bloodPressure.getByRole('button', {name: 'Show versions for Blood pressure', exact: true}).click();
    let history = page.getByRole('dialog');
    const snapshots = history.locator('[data-field-version]');
    await expect(snapshots.first()).toContainText('120/80 mmHg');
    await expect(snapshots.first()).toContainText('Dr. Jordan Lee');
    await expect(snapshots.first()).toContainText('Source version 2');
    const values = await snapshots.allTextContents();
    for (const value of ['118/78 mmHg', '110/70 mmHg', '100/60 mmHg']) await expect(history).toContainText(value);
    expect(values.findIndex(text => text.includes('118/78 mmHg'))).toBeLessThan(values.findIndex(text => text.includes('110/70 mmHg')));
    expect(values.findIndex(text => text.includes('110/70 mmHg'))).toBeLessThan(values.findIndex(text => text.includes('100/60 mmHg')));
    await expect(history).toContainText('Valley Medical');
    await expect(history).toContainText('Memorial Hospital');
    await page.screenshot({path: '../.data/screenshots/blood-pressure-history.png'});
    await history.getByRole('button', {name: 'View source', exact: true}).first().click();
    await expect(history.locator('.source-code')).toContainText('patientId');
    await expect(history.locator('.source-code')).toContainText('120/80 mmHg');
    await history.getByRole('button', {name: 'Back to versions', exact: true}).click();
    await expect(history.locator('.source-code')).toHaveCount(0);
    await history.getByRole('button', {name: 'Close dialog', exact: true}).click();

    await allergies.getByRole('button', {name: 'Show versions for Allergies', exact: true}).click();
    history = page.getByRole('dialog');
    await expect(history.locator('[data-field-version]').first()).toContainText('Almonds');
    await expect(history.locator('[data-field-version]').first()).toContainText('Apple');
    await history.getByRole('button', {name: 'Close dialog', exact: true}).click();
    await expect(page.locator('pre')).toHaveCount(0);
    await expect(page.getByRole('button', {name: 'Upload visit', exact: true})).toHaveCount(0);

    await page.setViewportSize({width: 390, height: 844});
    await bloodPressure.scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await bloodPressure.getByRole('button', {name: 'Show versions for Blood pressure', exact: true}).click();
    history = page.getByRole('dialog');
    expect(await history.evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy();
    await page.screenshot({path: '../.data/screenshots/patient-field-history-mobile.png'});
    await history.getByRole('button', {name: 'Close dialog', exact: true}).click();

    // A hospital sees only copies it owns/has approval for, while the patient sees all sources.
    const hospitalPage = await memorial.newPage();await hospitalPage.goto('/');
    await hospitalPage.getByLabel('Patient ID lookup', {exact: true}).fill('PT-DEMO-SARAH');
    await hospitalPage.getByRole('button', {name: 'Find patient', exact: true}).click();
    await hospitalPage.getByRole('button', {name: 'Show versions for Blood pressure', exact: true}).click();
    await expect(hospitalPage.getByRole('dialog')).not.toContainText('110/70 mmHg');
  } finally {
    await memorial.close();await valley.close();await jordan.close();
  }
});
