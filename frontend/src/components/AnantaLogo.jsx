// Ananta emblem — a scalable SVG mark that fuses the existing trident/ring motif with a
// sharp central "A" and an upward chart arrow, echoing the "Algorithmic AI Trading" logo.
// Monochrome by default (inherits currentColor) with a subtle cyan accent node.
export default function AnantaLogo({ className = "h-8 w-8", accent = "#14E0C9" }) {
    return (
        <svg viewBox="0 0 64 64" className={className} fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="Ananta" role="img">
            {/* outer ring */}
            <circle cx="32" cy="32" r="29" stroke="currentColor" strokeOpacity="0.35" strokeWidth="2" />
            {/* trident tines (top) */}
            <path d="M22 15v9M32 9v13M42 15v9" stroke="currentColor" strokeOpacity="0.5" strokeWidth="2" strokeLinecap="round" />
            {/* central sharp A */}
            <path d="M32 17 L45 47 H38.5 L36 41 H28 L25.5 47 H19 L32 17 Z" fill="currentColor" />
            <path d="M30 35 H34 L32 29 Z" fill="var(--logo-cut, #0B0D10)" />
            {/* upward chart arrow through the base */}
            <path d="M16 44 L26 38 L33 42 L48 30" stroke={accent} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M42 29 H48 V35" stroke={accent} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            {/* constellation nodes */}
            <circle cx="16" cy="44" r="1.6" fill={accent} />
            <circle cx="48" cy="30" r="1.6" fill={accent} />
            <circle cx="12" cy="26" r="1.1" fill="currentColor" fillOpacity="0.6" />
            <circle cx="52" cy="20" r="1.1" fill="currentColor" fillOpacity="0.6" />
        </svg>
    );
}
