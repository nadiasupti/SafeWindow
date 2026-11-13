// A small drawing for the Home header: a house and trees on raised ground beside moving water.
// Pure SVG + CSS (about 2 KB): works offline, sharp on every screen, and still when the phone asks for less motion.
// Decoration only: it says nothing about any real village, so screen readers skip it.

// One wave period is 40 px; 16 periods (640 px) let the strip slide left by 320 px and repeat without a seam.
const wave = (y, amp) => {
  let d = `M0 ${y}`
  for (let i = 0; i < 16; i++) d += ` q10 ${-amp} 20 0 t20 0`
  return `${d} V110 H0Z`
}

export default function HeroArt() {
  return (
    <svg className="hero-art" viewBox="0 0 200 110" aria-hidden="true" focusable="false">
      <defs>
        {/* soft edges: the water fades out on the left and at the bottom instead of ending in a straight line */}
        <linearGradient id="ha-fade-x" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#000" />
          <stop offset="0.22" stopColor="#fff" />
          <stop offset="0.9" stopColor="#fff" />
          <stop offset="1" stopColor="#000" />
        </linearGradient>
        <linearGradient id="ha-fade-y" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0.72" stopColor="#fff" />
          <stop offset="1" stopColor="#000" />
        </linearGradient>
        <mask id="ha-mask-x"><rect width="200" height="110" fill="url(#ha-fade-x)" /></mask>
        <mask id="ha-mask-y"><rect width="200" height="110" fill="url(#ha-fade-y)" /></mask>
      </defs>
      <g mask="url(#ha-mask-y)"><g mask="url(#ha-mask-x)">
        {/* cloud, drifting */}
        <g className="ha-cloud" fill="rgba(255,255,255,0.85)">
          <ellipse cx="150" cy="20" rx="16" ry="7" />
          <ellipse cx="140" cy="18" rx="9" ry="7" />
          <ellipse cx="160" cy="17" rx="8" ry="6" />
        </g>
        {/* rain drops, falling */}
        <g className="ha-rain" stroke="rgba(207,229,247,0.8)" strokeWidth="1.6" strokeLinecap="round">
          <line x1="140" y1="30" x2="138" y2="36" />
          <line x1="150" y1="32" x2="148" y2="38" />
          <line x1="160" y1="29" x2="158" y2="35" />
        </g>
        {/* raised ground */}
        <path d="M40 82 C 60 58, 120 56, 150 82 Z" fill="#3f9d6b" />
        <path d="M52 82 C 70 66, 112 64, 138 82 Z" fill="#56b77f" />
        {/* trees */}
        <rect x="56" y="58" width="3" height="12" rx="1" fill="#6b4a2f" />
        <circle cx="57.5" cy="54" r="9" fill="#2f8a5a" />
        <circle cx="52" cy="58" r="6" fill="#3a9c66" />
        <rect x="129" y="62" width="3" height="10" rx="1" fill="#6b4a2f" />
        <circle cx="130.5" cy="58" r="7" fill="#2f8a5a" />
        {/* house */}
        <rect x="82" y="50" width="34" height="22" rx="2" fill="#ffffff" />
        <path d="M77 52 L99 34 L121 52 Z" fill="#9fd0f5" />
        <path d="M77 52 L99 34 L121 52" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinejoin="round" />
        <rect x="95" y="58" width="8" height="14" rx="1" fill="#163f66" />
        <rect x="85" y="56" width="7" height="7" rx="1" fill="#163f66" />
        <rect x="106" y="56" width="7" height="7" rx="1" fill="#163f66" />
        {/* water, two layers sliding at different speeds */}
        <path className="ha-wave ha-wave-back" d={wave(80, 4)} fill="rgba(159,208,245,0.55)" />
        <path className="ha-wave ha-wave-front" d={wave(88, 5)} fill="rgba(207,229,247,0.9)" />
      </g></g>
    </svg>
  )
}
