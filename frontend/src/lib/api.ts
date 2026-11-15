let csrf = '';
let workspace = '';
export function setCsrf(value: string) { csrf = value; }
export function setWorkspace(value: string) { workspace = value; }

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: any) { super(message); }
}

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const unavailable = 'The EHR Bridge backend is unavailable. Check that the API is running on port 8000, then try again.';
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options, credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...(workspace ? { 'X-Workspace-ID': workspace } : {}), ...options.headers }
    });
  } catch {
    throw new ApiError(503, unavailable);
  }
  if ([502, 503, 504].includes(response.status)) throw new ApiError(response.status, unavailable);
  let data: any;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(response.ok ? 502 : response.status, response.status >= 500 ? unavailable : 'The API returned an unexpected response. Please try again.');
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((e: any) => `${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ') : data.detail;
    throw new ApiError(response.status, typeof detail === 'object' ? detail.message || 'The request could not be completed' : detail || 'The request could not be completed', data.detail);
  }
  return data;
}

export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body: JSON.stringify(body) });

export function date(value?: string | null, time = false) {
  if (!value) return 'Not yet synchronized';
  const d = new Date(value.length === 10 ? value + 'T12:00:00Z' : value);
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', ...(time ? { hour: 'numeric', minute: '2-digit' } as const : {}), timeZone: 'America/Chicago' }).format(d);
}

export function today() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Chicago', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

export function label(value: string = '') {
  return value.toLowerCase().split('_').map(x => x.charAt(0).toUpperCase() + x.slice(1)).join(' ');
}

export function sourceName(hospital: string) { return hospital === 'northstar' ? 'Northstar' : hospital === 'riverside' ? 'Riverside' : label(hospital); }

export function frequencyText(value: number | string) { return typeof value === 'number' ? ({ 1: 'Once daily', 2: 'Twice daily', 3: 'Three times daily', 4: 'Four times daily' } as Record<number, string>)[value] || `${value} times daily` : `Source frequency: ${value || 'not mapped'}`; }

export const categories = [
  { id: 'MedicationStatement', kind: 'medication', label: 'Medications' },
  { id: 'AllergyIntolerance', kind: 'allergy', label: 'Allergies' },
  { id: 'Condition', kind: 'diagnosis', label: 'Diagnoses' },
  { id: 'Observation', kind: 'lab', label: 'Lab results' },
  { id: 'Immunization', kind: 'vaccination', label: 'Vaccinations' },
  { id: 'DocumentReference', kind: 'note', label: 'Clinical notes' }
];

export function reviewLabel(value: string) {
  return ({ PENDING_REVIEW: 'Needs review', ACCEPTED: 'Acknowledged', DEFERRED: 'Deferred', INVESTIGATING: 'Under investigation', REJECTED: 'Import declined', LOCAL_RECORD: 'Your hospital', SOURCE_RECORD: 'Your hospital', RESOLVED: 'Resolved', NEEDS_REVIEW: 'Needs review' } as Record<string, string>)[value] || label(value);
}

export function clinicalSummary(record: any) {
  const f = record.fields;
  if (record.category === 'medication') return `${f.Dose} ${f.Unit} · ${frequencyText(f.Frequency)}`;
  if (record.category === 'allergy') return f.Reaction || 'Reaction not specified';
  if (record.category === 'lab') return `${f.Result} ${f.Unit}`;
  if (record.category === 'vaccination') return `${f.Documentation}${f['Dose number'] ? ` · Dose ${f['Dose number']}` : ''}`;
  if (record.category === 'note') return `Approved by ${f['Approved by'] || record.author}`;
  return label(f.Status);
}
