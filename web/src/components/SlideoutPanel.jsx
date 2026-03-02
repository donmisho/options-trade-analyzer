/**
 * SlideoutPanel — Reusable right-side slideout container.
 *
 * WHY a shared component: Both Ask Claude and Formula Breakdown (and later Config)
 * use the same slide-from-right pattern with backdrop, header, scrollable body,
 * and optional footer. Extracting the shell means each panel only defines its
 * content, not its animation/layout boilerplate.
 *
 * Props:
 *   open      — boolean, whether the panel is visible
 *   onClose   — callback to close the panel
 *   title     — string, panel heading (e.g. "Ask Claude")
 *   subtitle  — string, secondary text below title
 *   icon      — string, emoji/icon shown before title
 *   width     — number, panel width in px (default 480)
 *   children  — the panel body content
 *   footer    — optional React node rendered in a sticky footer area
 */
import { C } from "../styles/tokens";

export default function SlideoutPanel({ open, onClose, title, subtitle, icon, width = 480, children, footer }) {
  return (
    <>
      {/* Backdrop — clicking it closes the panel */}
      {open && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: C.overlay,
            zIndex: 90,
          }}
        />
      )}

      {/* Panel */}
      <div
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width,
          backgroundColor: C.surface,
          borderLeft: `1px solid ${C.border}`,
          zIndex: 100,
          transform: open ? "translateX(0)" : `translateX(${width}px)`,
          transition: "transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
          display: "flex",
          flexDirection: "column",
          boxShadow: open ? "-8px 0 30px rgba(0,0,0,0.4)" : "none",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "12px 18px",
            borderBottom: `1px solid ${C.border}`,
            flexShrink: 0,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: `linear-gradient(135deg, ${C.surfaceAlt}, ${C.surface})`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {icon && <span style={{ fontSize: 18 }}>{icon}</span>}
            <div>
              <h2
                style={{
                  margin: 0,
                  fontSize: 15,
                  fontWeight: 700,
                  color: C.accent,
                }}
              >
                {title}
              </h2>
              {subtitle && (
                <p
                  style={{
                    margin: "1px 0 0",
                    fontSize: 10.5,
                    color: C.textDim,
                  }}
                >
                  {subtitle}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: C.textMuted,
              fontSize: 20,
              cursor: "pointer",
              padding: 4,
            }}
          >
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px" }}>
          {children}
        </div>

        {/* Optional sticky footer */}
        {footer && (
          <div
            style={{
              padding: "12px 18px",
              borderTop: `1px solid ${C.border}`,
              flexShrink: 0,
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </>
  );
}
