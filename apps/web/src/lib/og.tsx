import { ImageResponse } from "next/og";

export const OG_SIZE = { width: 1200, height: 630 };

/** Social preview image drawn at build time from the page title. */
export function ogImage(title: string, kicker: string): ImageResponse {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: "#0B1B33",
        padding: 72,
        color: "white",
      }}
    >
      <div
        style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 30, fontWeight: 600 }}
      >
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: "#12305A",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#00A3A3",
            fontSize: 28,
          }}
        >
          P
        </div>
        Provenance Risk
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div
          style={{ fontSize: 26, color: "#00A3A3", letterSpacing: 2, textTransform: "uppercase" }}
        >
          {kicker}
        </div>
        <div style={{ fontSize: 64, fontWeight: 700, lineHeight: 1.1, maxWidth: 1000 }}>
          {title}
        </div>
      </div>
      <div style={{ fontSize: 24, color: "#cbd5e1" }}>
        Risk signals are leads for human review and not statements of fault.
      </div>
    </div>,
    OG_SIZE,
  );
}
