// Ananta brand mark — the CANONICAL imperial-gold trident, identical to the mobile app
// (mobile/src/components/Logo.tsx) so web + mobile share one emblem across platforms.
// `className` controls size (h-*/w-*); `accent` overrides the gold stroke if ever needed.
export default function AnantaLogo({ className = "h-8 w-8", accent = "#E5B84B" }) {
    return (
        <svg viewBox="0 0 24 24" className={className} fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="Ananta" role="img">
            {/* central shaft */}
            <path d="M12 3 L12 21" stroke={accent} strokeWidth="1.8" strokeLinecap="round" />
            {/* outer prongs */}
            <path d="M6 4 L6 9 Q6 12 12 12 Q18 12 18 9 L18 4" stroke={accent} strokeWidth="1.8" fill="none" strokeLinecap="round" />
            {/* prong tips */}
            <path d="M6 4 L5 6 M6 4 L7 6 M18 4 L17 6 M18 4 L19 6 M12 3 L11 5 M12 3 L13 5" stroke={accent} strokeWidth="1.6" strokeLinecap="round" />
            {/* base */}
            <path d="M9 21 L15 21" stroke={accent} strokeWidth="1.8" strokeLinecap="round" />
        </svg>
    );
}
