import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'EHR Bridge · Your EHR, made usable',
  description: 'A fictional EHR assistive workspace with patient-controlled access, clinical intake, and preserved source history.'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
