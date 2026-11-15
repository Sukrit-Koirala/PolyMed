import type { ExtractedField } from "../types";
import { uid } from "../utils";

/**
 * Local, rule-based extraction of intake fields from a transcript.
 * No AI model or external service is used. Every result is a DRAFT that a
 * clinician must accept or reject.
 */
const SYMPTOMS = ["chest discomfort", "chest pain", "chest tightness", "shortness of breath", "headache", "dizziness", "palpitations", "nausea", "fatigue", "cough", "fever", "back pain", "knee pain", "abdominal pain", "swelling"];
const MEDS = ["lisinopril", "metformin", "atorvastatin", "aspirin", "amlodipine", "furosemide", "apixaban", "sumatriptan", "ibuprofen", "albuterol", "levothyroxine", "omeprazole"];
const HOSPITALS = ["Valley Medical", "Memorial Hospital", "Northside Clinic"];
const NUM: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, a: 1, an: 1 };
const WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

export function extractFields(transcript: string): ExtractedField[] {
  const t = transcript.toLowerCase();
  const out: ExtractedField[] = [];
  const push = (label: string, value: string) => out.push({ id: uid("xf"), label, value, status: "draft" });
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

  for (const s of SYMPTOMS) if (t.includes(s)) push("Symptom", cap(s));

  const dur = t.match(/(?:for|since|past|last)\s+(?:the\s+)?(?:past\s+|last\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)\s+(days?|weeks?|months?|hours?)/);
  if (dur) {
    const n = NUM[dur[1]] ?? Number(dur[1]);
    const unit = dur[2].replace(/s$/, "");
    push("Duration", `${WORDS[n] ?? n} ${unit}${n === 1 ? "" : "s"}`);
  }

  const pain = t.match(/(\d{1,2})\s*(?:out of|\/)\s*10/);
  if (pain) push("Severity", `${pain[1]}/10`);

  for (const h of HOSPITALS) if (t.includes(h.toLowerCase())) push("Previous hospital", h);

  for (const m of MEDS) if (t.includes(m)) push("Medication mentioned", cap(m));

  if (/(heart test|stress test|echo|ecg|ekg|cardiac test|cardiogram)/.test(t)) push("Prior cardiac testing mentioned", "Yes");

  if (/smok/.test(t)) push("Lifestyle", /(never|quit|stopped|do not|don.t) smok/.test(t) ? "Non-smoker or former smoker (reported)" : "Smoking mentioned");

  const allergy = t.match(/(?:allergic to|allergy to)\s+(\w+)/);
  if (allergy) push("Allergy mentioned", cap(allergy[1]));

  return out;
}
