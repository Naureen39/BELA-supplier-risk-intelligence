/** In-house illustrations drawn with the brand palette. They are schematic, not screenshots. */

const base = "w-full h-auto";

export function UploadArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="A spreadsheet with uneven supplier names"
    >
      <rect x="8" y="8" width="184" height="94" rx="8" fill="#fff" stroke="#DDE3EC" />
      {[0, 1, 2, 3, 4].map((i) => (
        <g key={i}>
          <rect
            x="18"
            y={20 + i * 16}
            width={[96, 82, 104, 70, 90][i]}
            height="8"
            rx="4"
            fill={i === 2 ? "#2F74D8" : "#CBD5E1"}
          />
          <rect x="130" y={20 + i * 16} width="52" height="8" rx="4" fill="#E2E8F0" />
        </g>
      ))}
    </svg>
  );
}

export function ResolveArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="Several name variants resolving to one company"
    >
      {[18, 44, 70].map((y, i) => (
        <g key={y}>
          <rect x="8" y={y} width="72" height="18" rx="9" fill="#fff" stroke="#CBD5E1" />
          <rect x="18" y={y + 6} width={[44, 36, 48][i]} height="6" rx="3" fill="#94A3B8" />
          <path
            d={`M80 ${y + 9} C 110 ${y + 9}, 110 55, 130 55`}
            fill="none"
            stroke="#2F74D8"
            strokeWidth="1.6"
          />
        </g>
      ))}
      <rect x="130" y="38" width="62" height="34" rx="8" fill="#E6EFFB" stroke="#2F74D8" />
      <circle cx="146" cy="55" r="5" fill="#1F5FBF" />
      <rect x="156" y="51" width="28" height="8" rx="4" fill="#1F5FBF" />
    </svg>
  );
}

export function EventsArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="Regulator records and news feeding one company"
    >
      <rect x="8" y="14" width="64" height="30" rx="6" fill="#fff" stroke="#DDE3EC" />
      <rect x="16" y="22" width="40" height="5" rx="2.5" fill="#00A3A3" />
      <rect x="16" y="32" width="28" height="5" rx="2.5" fill="#CBD5E1" />
      <rect x="8" y="64" width="64" height="30" rx="6" fill="#fff" stroke="#DDE3EC" />
      <rect x="16" y="72" width="40" height="5" rx="2.5" fill="#E69F00" />
      <rect x="16" y="82" width="28" height="5" rx="2.5" fill="#CBD5E1" />
      <path
        d="M72 29 C 110 29, 110 55, 134 55 M72 79 C 110 79, 110 55, 134 55"
        fill="none"
        stroke="#6C7A89"
        strokeWidth="1.6"
      />
      <circle cx="152" cy="55" r="18" fill="#E6EFFB" stroke="#2F74D8" />
      <path d="M152 46v10m0 5v.5" stroke="#1F5FBF" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export function MonitorArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="A corporate family with one alert at the top"
    >
      <circle cx="100" cy="24" r="12" fill="#12305A" />
      {[44, 100, 156].map((x) => (
        <g key={x}>
          <path d={`M100 36 L ${x} 72`} stroke="#94A3B8" strokeWidth="1.6" />
          <circle
            cx={x}
            cy="82"
            r="10"
            fill={x === 156 ? "#FBE4E1" : "#E6EFFB"}
            stroke={x === 156 ? "#C0392B" : "#2F74D8"}
          />
        </g>
      ))}
      <circle cx="170" cy="16" r="9" fill="#C77700" />
      <path d="M170 11v6m0 3v.4" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function NamesArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="Different spellings of one company name"
    >
      {["ACME FOODS INC", "Acme Foods, Incorporated", "THE ACME FOODS CO"].map((t, i) => (
        <g key={t}>
          <rect
            x="14"
            y={14 + i * 32}
            width="172"
            height="24"
            rx="12"
            fill="#fff"
            stroke="#CBD5E1"
          />
          <text
            x="28"
            y={30 + i * 32}
            fontSize="11"
            fontFamily="JetBrains Mono, monospace"
            fill="#475569"
          >
            {t}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function SubsidiaryArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="A parent company with hidden subsidiaries"
    >
      <rect x="70" y="8" width="60" height="22" rx="6" fill="#12305A" />
      {[24, 84, 144].map((x) => (
        <g key={x}>
          <path
            d={`M100 30 V 44 H ${x + 16} V 62`}
            fill="none"
            stroke="#94A3B8"
            strokeWidth="1.5"
          />
          <rect
            x={x}
            y="62"
            width="32"
            height="18"
            rx="5"
            fill={x === 84 ? "#FBE4E1" : "#E6EFFB"}
            stroke={x === 84 ? "#C0392B" : "#2F74D8"}
          />
        </g>
      ))}
      <rect x="68" y="90" width="64" height="10" rx="5" fill="#E2E8F0" />
    </svg>
  );
}

export function SheetArt() {
  return (
    <svg
      viewBox="0 0 200 110"
      className={base}
      role="img"
      aria-label="A large spreadsheet with many rows"
    >
      <rect x="10" y="8" width="180" height="94" rx="8" fill="#fff" stroke="#DDE3EC" />
      {Array.from({ length: 8 }, (_, r) => (
        <g key={r}>
          {[0, 1, 2, 3].map((c) => (
            <rect
              key={c}
              x={18 + c * 44}
              y={16 + r * 11}
              width="36"
              height="6"
              rx="3"
              fill={(r * 3 + c) % 7 === 0 ? "#E69F00" : "#E2E8F0"}
            />
          ))}
        </g>
      ))}
    </svg>
  );
}

/** The corporate family graphic: facility, subsidiary, parent, and one linked record. */
export function FamilyGraphic({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 360 220"
      className={`${base} ${className}`}
      role="img"
      aria-label="Corporate family: a parent, two subsidiaries, and a facility with a regulator record"
    >
      <path
        d="M180 44 L90 104 M180 44 L270 104 M90 130 L90 176"
        stroke="#94A3B8"
        strokeWidth="2"
        fill="none"
      />
      <rect x="130" y="14" width="100" height="34" rx="10" fill="#12305A" />
      <text
        x="180"
        y="35"
        textAnchor="middle"
        fontSize="12"
        fill="#fff"
        fontFamily="Inter, sans-serif"
      >
        Parent company
      </text>
      <rect x="40" y="104" width="100" height="30" rx="10" fill="#E6EFFB" stroke="#2F74D8" />
      <text
        x="90"
        y="123"
        textAnchor="middle"
        fontSize="12"
        fill="#12305A"
        fontFamily="Inter, sans-serif"
      >
        Subsidiary A
      </text>
      <rect x="220" y="104" width="100" height="30" rx="10" fill="#E6EFFB" stroke="#2F74D8" />
      <text
        x="270"
        y="123"
        textAnchor="middle"
        fontSize="12"
        fill="#12305A"
        fontFamily="Inter, sans-serif"
      >
        Subsidiary B
      </text>
      <rect
        x="40"
        y="176"
        width="100"
        height="30"
        rx="10"
        fill="#fff"
        stroke="#00A3A3"
        strokeDasharray="4 3"
      />
      <text
        x="90"
        y="195"
        textAnchor="middle"
        fontSize="12"
        fill="#0B1B33"
        fontFamily="Inter, sans-serif"
      >
        Facility
      </text>
      <rect x="170" y="176" width="150" height="30" rx="10" fill="#FBEED6" stroke="#C77700" />
      <text
        x="245"
        y="195"
        textAnchor="middle"
        fontSize="12"
        fill="#6b3f00"
        fontFamily="Inter, sans-serif"
      >
        Public record on file
      </text>
      <path d="M140 191 H170" stroke="#C77700" strokeWidth="2" markerEnd="url(#a)" />
      <defs>
        <marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0 0 L8 4 L0 8 z" fill="#C77700" />
        </marker>
      </defs>
    </svg>
  );
}
