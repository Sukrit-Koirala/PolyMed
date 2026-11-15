"use client";

import { create } from "zustand";

interface UIState {
  newSessionOpen: boolean;
  newSessionPatientId?: string;
  resumeSessionId?: string;
  openNewSession: (patientId?: string, resumeSessionId?: string) => void;
  closeNewSession: () => void;
  codeEntryRequestId?: string;
  openCodeEntry: (requestId: string) => void;
  closeCodeEntry: () => void;
}

export const useUI = create<UIState>((set) => ({
  newSessionOpen: false,
  openNewSession: (patientId, resumeSessionId) => set({ newSessionOpen: true, newSessionPatientId: patientId, resumeSessionId }),
  closeNewSession: () => set({ newSessionOpen: false, newSessionPatientId: undefined, resumeSessionId: undefined }),
  openCodeEntry: (requestId) => set({ codeEntryRequestId: requestId }),
  closeCodeEntry: () => set({ codeEntryRequestId: undefined }),
}));
