import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function shortHash(input: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < input.length; i++) {
    const c = input.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 16777619) >>> 0;
    h2 = Math.imul(h2 ^ c, 2246822519) >>> 0;
  }
  return (h1.toString(16).padStart(8, "0") + h2.toString(16).padStart(8, "0")).slice(0, 7);
}

let counter = 0;
export function uid(prefix: string) {
  counter = (counter + 1) % 100000;
  return `${prefix}-${Date.now().toString(36)}${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

export function ageFrom(dob: string, now = Date.now()) {
  const d = new Date(dob);
  if (isNaN(d.getTime())) return undefined;
  const n = new Date(now);
  let a = n.getFullYear() - d.getFullYear();
  if (n.getMonth() < d.getMonth() || (n.getMonth() === d.getMonth() && n.getDate() < d.getDate())) a--;
  return a;
}

export function fmtDate(t: number | string | undefined) {
  if (t === undefined) return "—";
  const d = new Date(t);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function fmtDateTime(t: number | undefined) {
  if (t === undefined) return "—";
  return new Date(t).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function fmtTime(t: number) {
  return new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function relTime(t: number | undefined, now = Date.now()) {
  if (t === undefined) return "—";
  const diff = now - t;
  const abs = Math.abs(diff);
  const fut = diff < 0;
  const m = Math.round(abs / 60000);
  let s: string;
  if (m < 1) return fut ? "in moments" : "just now";
  if (m < 60) s = `${m} min`;
  else if (m < 60 * 24) s = `${Math.round(m / 60)} h`;
  else if (m < 60 * 24 * 45) s = `${Math.round(m / 1440)} d`;
  else return fmtDate(t);
  return fut ? `in ${s}` : `${s} ago`;
}

export function countdown(ms: number) {
  if (ms <= 0) return "0:00";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function initials(name: string) {
  return name.replace(/^(Dr\.|NP)\s+/, "").split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}
