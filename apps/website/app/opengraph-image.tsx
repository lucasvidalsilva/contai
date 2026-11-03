import { ImageResponse } from "next/og";

export const alt = "contAI — Conferência fiscal, sem caixa-preta";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        background: "#eee8dc",
        color: "#111314",
        display: "flex",
        fontFamily: "Georgia, serif",
        height: "100%",
        padding: 54,
        width: "100%",
      }}
    >
      <div
        style={{
          border: "2px solid #111314",
          display: "flex",
          flexDirection: "column",
          height: "100%",
          justifyContent: "space-between",
          padding: 46,
          position: "relative",
          width: "100%",
        }}
      >
        <div
          style={{
            alignItems: "center",
            display: "flex",
            fontFamily: "Arial, sans-serif",
            fontSize: 27,
            fontWeight: 800,
            justifyContent: "space-between",
          }}
        >
          <span>
            cont<span style={{ color: "#3d5afe" }}>AI</span>
          </span>
          <span style={{ fontSize: 14, letterSpacing: 2, textTransform: "uppercase" }}>
            Inteligência fiscal com evidências
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 88, letterSpacing: -5, lineHeight: 0.95 }}>
            Conferência fiscal,
          </span>
          <span
            style={{
              color: "#3d5afe",
              fontSize: 88,
              fontStyle: "italic",
              letterSpacing: -5,
              lineHeight: 0.95,
            }}
          >
            sem caixa-preta.
          </span>
        </div>

        <div
          style={{
            alignItems: "center",
            display: "flex",
            fontFamily: "Arial, sans-serif",
            fontSize: 14,
            justifyContent: "space-between",
            letterSpacing: 1.4,
            textTransform: "uppercase",
          }}
        >
          <span>Regras determinísticas · Fontes rastreáveis</span>
          <span style={{ background: "#111314", color: "#f7f3ea", padding: "14px 22px" }}>
            Em breve
          </span>
        </div>
      </div>
    </div>,
    size,
  );
}
