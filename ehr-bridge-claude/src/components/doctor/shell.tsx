"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bell, CalendarDays, ChevronDown, LayoutDashboard, LogOut, Plus, Repeat2, Users, ClipboardList, KeyRound, MessageCircleQuestion, CheckCircle2, XCircle } from "lucide-react";
import { useApp, useAuth } from "@/lib/store";
import { useCurrentDoctor, useNow, effectiveRequestStatus } from "@/lib/hooks";
import { useUI } from "@/lib/ui-store";
import { Wordmark } from "../logo";
import { Avatar, Button, Badge } from "../ui";
import { DemoTag } from "../chips";
import { cn, relTime } from "@/lib/utils";
import { NewSessionModal } from "./new-session/modal";
import { CodeEntryDialog } from "./code-entry";

const NAV = [
  { href: "/doctor", label: "Dashboard", icon: LayoutDashboard },
  { href: "/doctor/patients", label: "Patients", icon: Users },
  { href: "/doctor/sessions", label: "Sessions & Tasks", icon: ClipboardList },
  { href: "/doctor/exchange", label: "Exchange & History", icon: Repeat2 },
];

export function DoctorShell({ children }: { children: React.ReactNode }) {
  const doc = useCurrentDoctor();
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuth((s) => s.logout);
  const hospitals = useApp((s) => s.hospitals);
  const connections = useApp((s) => s.connections);
  const openNewSession = useUI((s) => s.openNewSession);
  const [menu, setMenu] = useState(false);

  if (!doc) return null;
  const hospital = hospitals.find((h) => h.id === doc.primaryHospitalId)!;
  const conn = connections.find((c) => c.hospitalId === hospital.id)!;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-4 px-4 sm:px-6">
          <Link href="/doctor"><Wordmark /></Link>
          <div className="mx-2 hidden h-8 w-px bg-slate-200 lg:block" />
          <div className="hidden items-center gap-2 lg:flex">
            <div className="text-sm">
              <div className="font-medium text-slate-900">{hospital.name}</div>
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className={cn("size-1.5 rounded-full", conn.status === "connected" ? "bg-emerald-500" : conn.status === "paused" ? "bg-slate-400" : "bg-amber-500")} />
                {hospital.vendor} · {conn.status === "connected" ? "Connected" : conn.status === "paused" ? "Paused" : "Degraded"} <span className="text-slate-400">(mock adapter)</span>
              </div>
            </div>
          </div>
          <div className="flex-1" />
          <div className="hidden items-center gap-1.5 text-xs text-slate-500 md:flex">
            <CalendarDays className="size-3.5" />
            {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
          </div>
          <Notifications doctorId={doc.id} />
          <Button variant="primary" onClick={() => openNewSession()} className="hidden sm:inline-flex">
            <Plus /> New Session
          </Button>
          <Button variant="primary" size="icon" onClick={() => openNewSession()} className="sm:hidden" aria-label="New session"><Plus /></Button>
          <div className="relative">
            <button onClick={() => setMenu((m) => !m)} className="flex items-center gap-2 rounded-lg p-1 hover:bg-slate-100">
              <Avatar name={doc.name} />
              <div className="hidden text-left text-xs xl:block">
                <div className="font-medium text-slate-900">{doc.name}</div>
                <div className="text-slate-500">{doc.department}</div>
              </div>
              <ChevronDown className="hidden size-3.5 text-slate-400 xl:block" />
            </button>
            {menu && (
              <div className="absolute right-0 top-11 z-50 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg" onMouseLeave={() => setMenu(false)}>
                <div className="px-2.5 py-2 text-xs text-slate-500">{doc.email}<br />{doc.role}</div>
                <button className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-100" onClick={() => { logout(); router.push("/"); }}>
                  <LogOut className="size-4" /> Switch account
                </button>
              </div>
            )}
          </div>
        </div>
        <nav className="mx-auto flex max-w-[1400px] gap-1 overflow-x-auto px-4 sm:px-6">
          {NAV.map((n) => {
            const active = n.href === "/doctor" ? pathname === "/doctor" : pathname.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href} className={cn("flex shrink-0 items-center gap-2 border-b-2 px-3 pb-2.5 pt-1 text-sm font-medium transition-colors", active ? "border-navy-800 text-navy-900" : "border-transparent text-slate-500 hover:text-slate-800")}>
                <n.icon className="size-4" />
                {n.label}
              </Link>
            );
          })}
          <div className="flex-1" />
          <div className="hidden items-center pb-2 md:flex"><DemoTag>Demo security simulation</DemoTag></div>
        </nav>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">{children}</main>
      <NewSessionModal />
      <CodeEntryDialog />
    </div>
  );
}

function Notifications({ doctorId }: { doctorId: string }) {
  const requests = useApp((s) => s.requests);
  const codes = useApp((s) => s.codes);
  const grants = useApp((s) => s.grants);
  const patients = useApp((s) => s.patients);
  const openCode = useUI((s) => s.openCodeEntry);
  const now = useNow(5000);
  const [open, setOpen] = useState(false);
  const [seenAt, setSeenAt] = useState(() => Date.now() - 6 * 3600_000);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const items = useMemo(() => {
    return requests
      .filter((r) => r.doctorId === doctorId)
      .map((r) => {
        const st = effectiveRequestStatus(r, codes, grants, now);
        const name = patients.find((p) => p.id === r.patientId)?.name ?? r.patientId;
        const at = r.respondedAt ?? r.createdAt;
        if (st === "approved") return { id: r.id, at, icon: <KeyRound className="size-4 text-blue-600" />, text: `${name} approved your request. Enter the code they share with you.`, action: () => openCode(r.id) };
        if (st === "denied") return { id: r.id, at, icon: <XCircle className="size-4 text-rose-600" />, text: `${name} denied your access request.` };
        if (st === "investigating") return { id: r.id, at: r.createdAt, icon: <MessageCircleQuestion className="size-4 text-violet-600" />, text: `${name} has a question about your request${r.patientQuestion ? `: “${r.patientQuestion}”` : ""}` };
        if (st === "active") return { id: r.id, at, icon: <CheckCircle2 className="size-4 text-emerald-600" />, text: `Access to ${name}'s records is active.` };
        if (st === "pending") return { id: r.id, at: r.createdAt, icon: <Bell className="size-4 text-amber-600" />, text: `Waiting for ${name} to respond to your access request.` };
        return null;
      })
      .filter(Boolean)
      .sort((a, b) => b!.at - a!.at)
      .slice(0, 8) as { id: string; at: number; icon: React.ReactNode; text: string; action?: () => void }[];
  }, [requests, codes, grants, patients, doctorId, now, openCode]);
  const unread = items.filter((i) => i.at > seenAt).length;

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => { setOpen((o) => !o); setSeenAt(Date.now()); }} className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100" aria-label="Notifications">
        <Bell className="size-5" />
        {unread > 0 && <span className="absolute right-1 top-1 flex size-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-semibold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-50 w-[340px] rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <span className="text-sm font-semibold">Notifications</span>
            <Badge tone="slate">{items.length}</Badge>
          </div>
          <div className="max-h-96 overflow-y-auto p-1.5">
            {items.length === 0 && <p className="p-4 text-center text-sm text-slate-500">You're all caught up.</p>}
            {items.map((i) => (
              <button key={i.id} onClick={() => { i.action?.(); setOpen(false); }} className="flex w-full gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-slate-50">
                <div className="mt-0.5">{i.icon}</div>
                <div>
                  <p className="text-[13px] text-slate-700">{i.text}</p>
                  <p className="text-[11px] text-slate-400">{relTime(i.at, now)}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
