"use client";

import { RoleGuard } from "@/components/role-guard";
import { DoctorShell } from "@/components/doctor/shell";

export default function DoctorLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="doctor">
      <DoctorShell>{children}</DoctorShell>
    </RoleGuard>
  );
}
