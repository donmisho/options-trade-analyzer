const sectionLabelStyle = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.6px',
  color: 'var(--muted)',
  fontFamily: 'monospace',
  margin: '16px 0 8px',
};

export default function SectionD() {
  return (
    <div>
      <div style={sectionLabelStyle}>PROBABILITY MATRIX</div>
      <div
        style={{
          border: '1px solid var(--border)',
          borderRadius: 4,
          padding: 20,
          textAlign: 'center',
        }}
      >
        <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'monospace' }}>
          Probability matrix — available when Phase 2.11 backend is complete
        </span>
      </div>
    </div>
  );
}
