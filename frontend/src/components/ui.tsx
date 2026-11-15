'use client';
import * as Dialog from '@radix-ui/react-dialog';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cva, type VariantProps } from 'class-variance-authority';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { Loader2, X } from 'lucide-react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
const variants = cva('button', { variants: { variant: { default: 'button-primary', outline: 'button-outline', ghost: 'button-ghost', danger: 'button-danger' }, size: { default: '', sm: 'button-sm' } }, defaultVariants: { variant: 'default', size: 'default' } });
export function Button({ variant, size, className, busy, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof variants> & { busy?: boolean }) {
  return <button className={cn(variants({ variant, size }), className)} disabled={props.disabled || busy} {...props}>{busy && <Loader2 size={15} className="spin" />}{children}</button>;
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) { return <span className={`badge badge-${tone}`}>{children}</span>; }
export function Modal({ open, onClose, title, description, children }: { open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode }) {
  return <Dialog.Root open={open} onOpenChange={v => !v && onClose()}><Dialog.Portal><Dialog.Overlay className="modal-overlay" /><Dialog.Content className="modal-content"><div className="modal-heading"><div><Dialog.Title>{title}</Dialog.Title><Dialog.Description>{description || 'Inspect the synthetic clinical source and its history.'}</Dialog.Description></div><Dialog.Close asChild><button className="icon-button" aria-label="Close dialog"><X size={19} /></button></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>;
}
export const Tabs = TabsPrimitive.Root;
export const TabsList = TabsPrimitive.List;
export const TabsTrigger = TabsPrimitive.Trigger;
export const TabsContent = TabsPrimitive.Content;
export function Empty({ title, children }: { title: string; children?: ReactNode }) { return <div className="empty"><div className="empty-symbol">+</div><h3>{title}</h3><p>{children}</p></div>; }
export function Json({ value }: { value: unknown }) { return <pre className="json">{JSON.stringify(value, null, 2)}</pre>; }
export function Diff({ changes, beforeLabel = 'Previous source version', afterLabel = 'Published source version' }: { changes: any[]; beforeLabel?: string; afterLabel?: string }) {
  return <div className="diff"><div className="diff-header"><span>Clinical field</span><span>{beforeLabel}</span><span>{afterLabel}</span></div>{changes.length ? changes.map((d, i) => <div className="diff-row" key={i}><strong>{d.field}</strong><span className="diff-before">{d.before === null || d.before === undefined || d.before === '' ? 'Not documented' : String(d.before)}</span><span className="diff-after">{d.after === null || d.after === undefined || d.after === '' ? 'Not documented' : String(d.after)}</span></div>) : <p className="muted pad">No clinical field differences.</p>}</div>;
}
