import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ClinicalSync · Connected clinical context',
  description: 'A synthetic demonstration of shared, source-attributed clinical information and hospital-specific review.'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
