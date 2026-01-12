export function MiniGrantsPage() {
  const cardStyle = {
    background: "var(--mini-bg-card)",
    border: "1px solid var(--mini-border)",
    borderRadius: "var(--mini-radius-lg)",
    padding: "20px",
    boxShadow: "var(--mini-shadow-sm)"
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header Card */}
      <div style={{
        ...cardStyle,
        background: "var(--mini-gradient-primary)",
        color: "#fff",
        position: "relative",
        overflow: "hidden"
      }} className="mini-animate-slide-up">
        <div style={{
          position: "absolute",
          top: "-20px",
          right: "-20px",
          width: "80px",
          height: "80px",
          background: "rgba(255,255,255,0.1)",
          borderRadius: "50%"
        }} />
        <div style={{ position: "relative", zIndex: 1 }}>
          <p style={{
            fontSize: "18px",
            fontWeight: 600,
            marginBottom: "8px",
            display: "flex",
            alignItems: "center",
            gap: "8px"
          }}>
            🔐 Access management
          </p>
          <p style={{
            fontSize: "14px",
            opacity: 0.9,
            lineHeight: 1.5
          }}>
            Grants and permissions for your files with blockchain verification
          </p>
        </div>
      </div>

      {/* Info Card */}
      <div style={cardStyle} className="mini-animate-slide-up">
        <div style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "12px"
        }}>
          <div style={{
            width: "40px",
            height: "40px",
            borderRadius: "var(--mini-radius)",
            background: "var(--mini-accent-light)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0
          }}>
            <span style={{ fontSize: "20px" }}>📋</span>
          </div>
          <div>
            <p style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--mini-text)",
              marginBottom: "6px"
            }}>
              Feature in development
            </p>
            <p style={{
              fontSize: "13px",
              color: "var(--mini-text-secondary)",
              lineHeight: 1.5,
              marginBottom: "12px"
            }}>
              UI for managing grants and revokes will appear after API is connected.
            </p>
            <div style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 12px",
              background: "var(--mini-bg-tertiary)",
              borderRadius: "var(--mini-radius-full)",
              fontSize: "12px",
              color: "var(--mini-text-muted)"
            }}>
              <span style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: "var(--mini-success)"
              }} />
              Webapp JWT auth is active
            </div>
          </div>
        </div>
      </div>

      {/* Feature Preview */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: "12px"
      }}>
        {[
          { icon: "📤", title: "Grant access", desc: "Share file" },
          { icon: "📥", title: "Received", desc: "Access from others" },
          { icon: "🔄", title: "Active", desc: "Current grants" },
          { icon: "❌", title: "Revoke", desc: "Revoke grants" }
        ].map((item) => (
          <div
            key={item.title}
            style={{
              ...cardStyle,
              opacity: 0.6,
              cursor: "not-allowed"
            }}
            className="mini-animate-slide-up"
          >
            <div style={{
              width: "32px",
              height: "32px",
              borderRadius: "var(--mini-radius-sm)",
              background: "var(--mini-bg-tertiary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: "8px",
              fontSize: "16px"
            }}>
              {item.icon}
            </div>
            <p style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--mini-text)",
              marginBottom: "2px"
            }}>
              {item.title}
            </p>
            <p style={{
              fontSize: "12px",
              color: "var(--mini-text-muted)"
            }}>
              {item.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
