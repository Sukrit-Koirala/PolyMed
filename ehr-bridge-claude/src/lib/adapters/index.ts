import type { AdapterId, Category, EhrVendor } from "../types";
import { normalize } from "./translation";

/**
 * EHR adapter contract. Every implementation in this prototype is a MOCK that
 * reads seeded fictional payloads. A real SMART on FHIR adapter would implement
 * the same interface (OAuth2 launch, FHIR search, Provenance capture) without
 * any change to the UI or business layers.
 */
export interface SourceRecord {
  sourceId: string;
  category: Category;
  title: string;
  recordedAt: number;
  author: string;
  payload: Record<string, unknown>;
}

export interface FetchResult {
  ok: boolean;
  records: SourceRecord[];
  error?: string;
  latencyMs: number;
}

export interface EhrAdapter {
  id: AdapterId;
  vendor: EhrVendor;
  label: string;
  isMock: true;
  fetchPatientRecords(mrn: string, categories: Category[], source: SourceRecord[]): Promise<FetchResult>;
  normalize(rec: SourceRecord): { data: Record<string, string> };
  testConnection(): Promise<{ ok: boolean; message: string }>;
}

function makeMockAdapter(id: AdapterId, vendor: EhrVendor, label: string, failureRate = 0): EhrAdapter {
  return {
    id,
    vendor,
    label,
    isMock: true,
    async fetchPatientRecords(_mrn, categories, source) {
      const latencyMs = 500 + Math.round(Math.random() * 600);
      await new Promise((r) => setTimeout(r, latencyMs));
      if (Math.random() < failureRate) return { ok: false, records: [], error: "Mock adapter timeout (simulated)", latencyMs };
      return { ok: true, records: source.filter((s) => categories.includes(s.category)), latencyMs };
    },
    normalize(rec) {
      return { data: normalize(rec.category, vendor, rec.payload).data };
    },
    async testConnection() {
      await new Promise((r) => setTimeout(r, 700));
      return { ok: true, message: `${label}: mock endpoint responded (simulated, no network call made)` };
    },
  };
}

export const ADAPTERS: Record<AdapterId, EhrAdapter> = {
  "mock-epic-fhir": makeMockAdapter("mock-epic-fhir", "Epic", "Mock Epic-facing FHIR adapter"),
  "mock-oracle-style": makeMockAdapter("mock-oracle-style", "Oracle Health", "Mock Oracle-style adapter"),
  "mock-generic-fhir": makeMockAdapter("mock-generic-fhir", "Mock FHIR", "Mock generic FHIR adapter", 0.15),
};
