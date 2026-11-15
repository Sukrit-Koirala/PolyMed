"use client";

import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Building2, HeartPulse, RotateCcw, ShieldCheck, Smartphone, Stethoscope, Workflow, Lock, History, Layers } from "lucide-react";
import { useApp, useAuth } from "@/lib/store";
import type { DemoUser } from "@/lib/types";
import { Wordmark } from "@/components/logo";
import { Button, Badge } from "@/components/ui";
import { DemoTag } from "@/components/chips";
import { toast } from "@/components/toast";

const ACCOUNTS: (DemoUser & { subtitle: string; ehr: string; icon: React.ReactNode; href: string; badge: string })[] = [
  { id: "d-carter", role: "doctor", name: "Dr. Emily Carter", hospitalId: "h-memorial", subtitle: "Internal Medicine · Memorial Hospital", ehr: "Epic (mock adapter)", icon: <Stethoscope />, href: "/doctor", badge: "Doctor — start the demo here" },
  { id: "d-reed", role: "doctor", name: "Dr. Daniel Reed", hospitalId: "h-valley", subtitle: "Cardiology · Valley Medical", ehr: "Oracle Health (mock adapter)", icon: <HeartPulse />, href: "/doctor", badge: "Doctor" },
  { id: "EHB-20417", role: "patient", name: "Sarah Mitchell", subtitle: "Patient · ID EHB-20417", ehr: "Mobile patient portal", icon: <Smartphone />, href: "/patient", badge: "Patient" },
  { id: "a-memorial", role: "admin", name: "Memorial Hospital Administrator", hospitalId: "h-memorial", subtitle: "Jordan Blake · IT & Integrations", ehr: "Organization settings", icon: <Building2 />, href: "/admin", badge: "Hospital admin" },
];

export default function LoginPage() {
  const router = useRouter();
  const login = useAuth((s) => s.login);
  const reset = useApp((s) => s.resetDemo);

  const signIn = (a: (typeof ACCOUNTS)[number]) => {
    login({ id: a.id, role: a.role, name: a.name, hospitalId: a.hospitalId });
    router.push(a.href);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-navy-950 via-navy-900 to-navy-800">
      <div className="mx-auto flex max-w-6xl flex-col px-4 py-8 sm:px-6 lg:py-14">
        <div className="flex items-center justify-between">
          <Wordmark light />
          <DemoTag>Hackathon prototype · fictional data</DemoTag>
        </div>

        <div className="mt-12 grid gap-10 lg:grid-cols-[1.05fr_1fr] lg:items-start">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <Badge tone="blue" className="border-blue-400/30 bg-blue-400/10 text-blue-200">Not a new EHR — a bridge between the ones you have</Badge>
            <h1 className="mt-4 text-4xl font-semibold leading-[1.1] tracking-tight text-white sm:text-5xl">
              Your EHR holds the data.
              <br />
              <span className="text-[#7fb3ff]">EHR Bridge makes it usable.</span>
            </h1>
            <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-navy-200">
              Retrieve authorized records from Epic, Oracle Health and other systems, translate them into one consistent model, keep every version, and give clinicians a faster place to work — with the patient in control of who sees what.
            </p>
            <div className="mt-8 grid max-w-xl grid-cols-2 gap-3">
              {[
                [<Workflow key="i" />, "Cross-EHR translation", "Source → normalized → destination"],
                [<Lock key="i" />, "Patient-approved access", "Scoped, time-limited, single-use codes"],
                [<History key="i" />, "Git-like record history", "Append-only versions with diffs"],
                [<Layers key="i" />, "Nothing gets lost", "Unmapped fields are preserved"],
              ].map(([icon, t, d]) => (
                <div key={t as string} className="rounded-xl border border-white/10 bg-white/[0.04] p-3.5">
                  <div className="text-[#7fb3ff] [&_svg]:size-4">{icon}</div>
                  <div className="mt-2 text-sm font-medium text-white">{t}</div>
                  <div className="text-xs text-navy-300">{d}</div>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.08 }} className="rounded-2xl bg-white p-5 shadow-2xl sm:p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Choose a demo account</h2>
                <p className="text-sm text-slate-500">Each account has its own interface and permission boundary.</p>
              </div>
              <ShieldCheck className="size-5 text-emerald-600" />
            </div>
            <div className="mt-4 space-y-2.5">
              {ACCOUNTS.map((a) => (
                <button key={a.id} onClick={() => signIn(a)} className="group flex w-full items-center gap-3.5 rounded-xl border border-slate-200 p-3.5 text-left transition-all hover:border-navy-300 hover:bg-navy-50/50 hover:shadow-sm">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-700 [&_svg]:size-5">{a.icon}</div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-900">{a.name}</span>
                      <Badge tone={a.role === "doctor" ? "navy" : a.role === "patient" ? "amber" : "slate"}>{a.badge}</Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">{a.subtitle} · {a.ehr}</div>
                  </div>
                  <ArrowRight className="size-4 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-navy-600" />
                </button>
              ))}
            </div>
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
              <strong>Demo security simulation.</strong> Sign-in has no password and access control runs locally in your browser on fictional data. This is not production-grade security and is not represented as HIPAA-compliant.
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>Tip: open the patient portal in a second tab — state syncs live between tabs.</span>
              <Button variant="ghost" size="sm" onClick={() => { reset(); toast("Demo data reset", "All accounts are back to the seeded scenario."); }}>
                <RotateCcw /> Reset demo data
              </Button>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
