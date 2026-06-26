// Ananta brand mark — a minimalist trident rendered in MATTE SILVER, with the
// damaruka (the small hourglass/drum crossing the shaft) faded to a very light,
// ghosted tone per brand direction.
export default function AnantaTrident({ size = 28, className = "" }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 48 64"
            fill="none"
            className={className}
            data-testid="ananta-trident"
            aria-label="Ananta"
        >
            <defs>
                <linearGradient id="mattesilver" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#E2E4E9" />
                    <stop offset="55%" stopColor="#C0C5CE" />
                    <stop offset="100%" stopColor="#878E99" />
                </linearGradient>
            </defs>

            {/* central prong */}
            <path d="M24 2 L24 40" stroke="url(#mattesilver)" strokeWidth="2.4" strokeLinecap="round" />
            <path d="M24 2 L20.5 9 H27.5 Z" fill="url(#mattesilver)" />

            {/* left prong */}
            <path d="M9 8 V20 Q9 28 24 30" stroke="url(#mattesilver)" strokeWidth="2.2" strokeLinecap="round" fill="none" />
            <path d="M9 8 L5.8 14 H12.2 Z" fill="url(#mattesilver)" />

            {/* right prong */}
            <path d="M39 8 V20 Q39 28 24 30" stroke="url(#mattesilver)" strokeWidth="2.2" strokeLinecap="round" fill="none" />
            <path d="M39 8 L35.8 14 H42.2 Z" fill="url(#mattesilver)" />

            {/* crossbar */}
            <path d="M9 18 H39" stroke="url(#mattesilver)" strokeWidth="2" strokeLinecap="round" />

            {/* shaft */}
            <path d="M24 30 L24 62" stroke="url(#mattesilver)" strokeWidth="2.4" strokeLinecap="round" />

            {/* damaruka (faded / ghosted very light) */}
            <g opacity="0.28">
                <path d="M16 44 L32 52 L32 44 L16 52 Z" fill="#E2E4E9" />
                <path d="M16 44 L32 52 M16 52 L32 44" stroke="#E2E4E9" strokeWidth="1" />
            </g>
        </svg>
    );
}
