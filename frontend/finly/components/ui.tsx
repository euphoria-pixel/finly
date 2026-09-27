import { useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'
import { Check, ChevronDown, Info, X } from 'lucide-react'

type ClassValue = string | false | null | undefined | Record<string, boolean>

export function cn(...classes: ClassValue[]) {
  return classes.flatMap((value) => {
    if (!value) return []
    if (typeof value === 'string') return [value]
    return Object.entries(value).filter(([, enabled]) => enabled).map(([name]) => name)
  }).join(' ')
}

export function Button({ className, variant = 'primary', size = 'default', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger'; size?: 'sm' | 'default' | 'icon' }) {
  return <button className={cn('inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all focus:outline-none focus:ring-2 focus:ring-lime/30 disabled:cursor-not-allowed disabled:opacity-45', {
    'bg-lime text-white hover:bg-[#1d6844]': variant === 'primary',
    'bg-[#eef2ef] text-ink hover:bg-[#e3ebe6]': variant === 'secondary',
    'text-muted hover:bg-[#eef2ef] hover:text-ink': variant === 'ghost',
    'border border-[#d5e0d9] bg-white text-ink hover:border-[#aebdb4] hover:bg-[#f7faf8]': variant === 'outline',
    'bg-coral/10 text-coral hover:bg-coral/15': variant === 'danger',
    'h-9 px-3 text-xs': size === 'sm',
    'h-11 px-5 text-sm': size === 'default',
    'h-10 w-10': size === 'icon',
  }, className)} {...props} />
}

export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-2xl border border-line bg-panel text-ink shadow-[0_1px_2px_rgba(32,48,42,.03)]', className)} {...props}>{children}</div>
}

export function Badge({ children, color = 'lime', className }: { children: ReactNode; color?: 'lime' | 'lilac' | 'sun' | 'coral' | 'muted'; className?: string }) {
  return <span className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold', {
    'bg-lime/12 text-lime': color === 'lime',
    'bg-lilac/12 text-lilac': color === 'lilac',
    'bg-sun/12 text-sun': color === 'sun',
    'bg-coral/12 text-coral': color === 'coral',
    'bg-[#eef2ef] text-muted': color === 'muted',
  }, className)}>{children}</span>
}

export function Progress({ value, className, color = 'lime' }: { value: number; className?: string; color?: 'lime' | 'lilac' | 'sun' }) {
  return <div className={cn('h-2 overflow-hidden rounded-full bg-[#e3ebe6]', className)}><div className={cn('h-full rounded-full transition-all', {
    'bg-lime': color === 'lime', 'bg-lilac': color === 'lilac', 'bg-sun': color === 'sun',
  })} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} /></div>
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn('h-11 w-full rounded-xl border border-[#d5e0d9] bg-white px-3 text-sm text-ink outline-none placeholder:text-muted/70 focus:border-lime/60 focus:ring-2 focus:ring-lime/10', className)} {...props} />
}

export function Select({ value, onChange, options, placeholder }: { value: string; onChange: (value: string) => void; options: Array<{ label: string; value: string }>; placeholder?: string }) {
  return <div className="relative"><select value={value} onChange={(event) => onChange(event.target.value)} className="h-11 w-full appearance-none rounded-xl border border-[#d5e0d9] bg-white px-3 pr-9 text-sm text-ink outline-none focus:border-lime/60">
    {placeholder && <option value="">{placeholder}</option>}
    {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
  </select><ChevronDown size={15} className="pointer-events-none absolute right-3 top-3.5 text-muted" /></div>
}

export function InfoTip({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (event: MouseEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  return <div className="relative inline-flex" ref={ref}><button aria-label="Показать расчёт" onClick={() => setOpen(!open)} className="inline-flex text-muted transition-colors hover:text-ink"><Info size={14} /></button>{open && <div className="absolute left-0 top-6 z-30 w-[min(280px,calc(100vw-32px))] rounded-xl border border-[#d5e0d9] bg-white p-3 text-xs leading-relaxed text-muted shadow-xl"><p className="mb-1 font-semibold text-ink">Расчёт</p>{children}</div>}</div>
}

export function Dialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  if (!open) return null
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/25 p-3 sm:items-center"><div className="max-h-[calc(100dvh-24px)] w-full max-w-md overflow-y-auto rounded-2xl border border-[#d5e0d9] bg-white p-5 shadow-2xl"><div className="mb-5 flex items-center justify-between"><h2 className="text-base font-semibold text-ink">{title}</h2><Button variant="ghost" size="icon" aria-label="Закрыть" onClick={onClose}><X size={18} /></Button></div>{children}</div></div>
}

export function Sheet({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  if (!open) return null
  return <div className="fixed inset-0 z-50 bg-ink/25"><div className="absolute bottom-0 left-0 right-0 max-h-[85dvh] overflow-y-auto rounded-t-3xl border-t border-[#d5e0d9] bg-white p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]"><div className="mx-auto mb-5 h-1 w-10 rounded-full bg-ink/15" /><button onClick={onClose} aria-label="Закрыть" className="absolute right-4 top-4 text-muted"><X size={18} /></button>{children}</div></div>
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div className="flex min-h-[260px] flex-col items-center justify-center px-6 text-center"><div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-lime/10 text-lime">{icon}</div><h3 className="mb-2 text-lg font-semibold text-ink">{title}</h3><p className="mb-5 max-w-xs text-sm leading-relaxed text-muted">{description}</p>{action}</div>
}

export function SuccessIcon() {
  return <span className="flex h-5 w-5 items-center justify-center rounded-full bg-lime text-ink"><Check size={12} strokeWidth={3} /></span>
}
