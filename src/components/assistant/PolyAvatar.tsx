import { cn } from '@/lib/utils'

type PolyAvatarProps = {
  className?: string
}

export function PolyAvatar({ className }: PolyAvatarProps) {
  return (
    <span className={cn('inline-flex overflow-hidden rounded-[28%] shadow-sm', className)}>
      <svg viewBox="0 0 96 96" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-full w-full">
        <defs>
          <linearGradient id="poly-bg" x1="16" y1="8" x2="80" y2="88" gradientUnits="userSpaceOnUse">
            <stop stopColor="#113153" />
            <stop offset="1" stopColor="#081A2E" />
          </linearGradient>
          <linearGradient id="poly-cream" x1="22" y1="20" x2="74" y2="78" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FFF6E8" />
            <stop offset="1" stopColor="#EBDDC8" />
          </linearGradient>
          <linearGradient id="poly-teal" x1="24" y1="16" x2="74" y2="80" gradientUnits="userSpaceOnUse">
            <stop stopColor="#38D1C9" />
            <stop offset="1" stopColor="#0E8B95" />
          </linearGradient>
          <linearGradient id="poly-gold" x1="14" y1="14" x2="80" y2="80" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FFD573" />
            <stop offset="1" stopColor="#D7961F" />
          </linearGradient>
        </defs>

        <rect x="2" y="2" width="92" height="92" rx="24" fill="url(#poly-bg)" />

        <ellipse cx="48" cy="18" rx="24" ry="10" fill="#0C2744" />
        <path d="M24 22C24 13.2 34.7 8 48 8C61.3 8 72 13.2 72 22V26H24V22Z" fill="#133B63" />
        <path d="M24 24H72" stroke="url(#poly-gold)" strokeWidth="3" strokeLinecap="round" />
        <circle cx="48" cy="18" r="7.5" fill="url(#poly-gold)" />
        <circle cx="48" cy="18" r="5.5" fill="url(#poly-teal)" />
        <path d="M45.7 14.5H49.8C52.5 14.5 54 16 54 18.1C54 20.4 52.1 22 49.1 22H45.7V14.5ZM48.8 20C50.4 20 51.4 19.3 51.4 18.2C51.4 17.1 50.5 16.4 49 16.4H47.9V20H48.8Z" fill="white" />

        <circle cx="17" cy="47" r="8" fill="#0F8E94" />
        <circle cx="79" cy="47" r="8" fill="#0F8E94" />
        <circle cx="17" cy="47" r="5.5" fill="#24C4BC" opacity="0.5" />
        <circle cx="79" cy="47" r="5.5" fill="#24C4BC" opacity="0.5" />

        <rect x="22" y="23" width="52" height="46" rx="14" fill="url(#poly-cream)" />
        <rect x="28" y="29" width="40" height="28" rx="10" fill="#06172A" />

        <path d="M36 37C37.8 35.2 40.2 34.2 42.7 34.2C45.2 34.2 47.4 35.1 49.2 36.8" stroke="#8BE9E0" strokeWidth="2.5" strokeLinecap="round" opacity="0.9" />
        <path d="M46.8 36.8C48.6 35.1 50.8 34.2 53.3 34.2C55.8 34.2 58.2 35.2 60 37" stroke="#8BE9E0" strokeWidth="2.5" strokeLinecap="round" opacity="0.9" />

        <circle cx="41" cy="45" r="5.6" fill="#B7FFF2" />
        <circle cx="55" cy="45" r="5.6" fill="#B7FFF2" />
        <circle cx="41" cy="45" r="3.5" fill="#0A8F97" />
        <circle cx="55" cy="45" r="3.5" fill="#0A8F97" />
        <circle cx="42.2" cy="43.5" r="1.1" fill="white" />
        <circle cx="56.2" cy="43.5" r="1.1" fill="white" />

        <path d="M44 51.5C45.6 53 47.5 53.8 49.7 53.8C51.8 53.8 53.8 53 55.4 51.5" stroke="#8BE9E0" strokeWidth="2.6" strokeLinecap="round" />

        <rect x="33" y="63" width="30" height="16" rx="6" fill="#0E897E" />
        <rect x="35.5" y="65.5" width="25" height="11" rx="4.5" fill="#0E314B" />
        <rect x="39" y="69" width="3" height="4.5" rx="1.2" fill="#3ED4CF" />
        <rect x="44" y="67" width="3" height="6.5" rx="1.2" fill="#3ED4CF" />
        <rect x="49" y="64.5" width="3" height="9" rx="1.2" fill="#3ED4CF" />
        <path d="M56 67.2A4.2 4.2 0 1 1 51.8 71.4V67.2H56Z" fill="#FFC84D" />

        <path d="M58.5 67.5L64 72L58.5 76.5L54.5 75.5L52.8 72L54.5 68.5L58.5 67.5Z" fill="url(#poly-gold)" />
        <path d="M56 72L57.5 73.6L60.8 70.4" stroke="#0B2440" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}
