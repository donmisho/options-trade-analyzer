/**
 * MediaWidget — Phase 2.3
 *
 * Displays images from Azure Blob Storage via SAS URLs fetched from the backend.
 * Three display modes:
 *   "single"     — one full-width image with caption below
 *   "thumbnails" — responsive grid; click to enlarge (lightbox)
 *   "carousel"   — auto-rotating, configurable interval
 *
 * SAS URLs expire after 15 minutes. Re-fetches every 14 minutes.
 *
 * Props: { config: { id, type, title, settings: { display_mode, interval_seconds } }, isEditMode }
 */

import { useState, useEffect, useRef } from 'react';
import { getDashboardMedia } from '../api/client';

const SAS_REFRESH_MS = 14 * 60 * 1000; // 14 minutes

export default function MediaWidget({ config, isEditMode }) {
  const displayMode     = config.settings?.display_mode    ?? 'single';
  const intervalSeconds = config.settings?.interval_seconds ?? 5;

  const [items, setItems]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [lightbox, setLightbox] = useState(null);  // index of enlarged image
  const [carouselIdx, setCarouselIdx] = useState(0);
  const refreshTimer = useRef(null);
  const carouselTimer = useRef(null);

  async function fetchMedia() {
    try {
      const data = await getDashboardMedia(config.id);
      setItems(data?.items ?? []);
    } catch {
      // silently fail — show placeholder
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchMedia();
    refreshTimer.current = setInterval(fetchMedia, SAS_REFRESH_MS);
    return () => clearInterval(refreshTimer.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  // Carousel auto-advance
  useEffect(() => {
    if (displayMode !== 'carousel' || items.length <= 1) return;
    carouselTimer.current = setInterval(() => {
      setCarouselIdx(i => (i + 1) % items.length);
    }, intervalSeconds * 1000);
    return () => clearInterval(carouselTimer.current);
  }, [displayMode, items.length, intervalSeconds]);

  const imgStyle = { width: '100%', height: '100%', objectFit: 'cover', borderRadius: 6 };

  if (loading) {
    return (
      <div style={s.wrap}>
        <div style={s.header}><span style={s.title}>{config.title}</span></div>
        <div style={s.placeholder}>Loading…</div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div style={s.wrap}>
        <div style={s.header}><span style={s.title}>{config.title}</span></div>
        <div style={s.placeholder}>No images configured for this widget.</div>
      </div>
    );
  }

  return (
    <div style={s.wrap}>
      <div style={s.header}><span style={s.title}>{config.title}</span></div>

      {/* ── Single ── */}
      {displayMode === 'single' && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ flex: 1, minHeight: 0 }}>
            <img src={items[0].sas_url} alt={items[0].caption ?? ''} style={imgStyle} />
          </div>
          {items[0].caption && <p style={s.caption}>{items[0].caption}</p>}
        </div>
      )}

      {/* ── Thumbnails ── */}
      {displayMode === 'thumbnails' && (
        <>
          <div style={s.thumbGrid}>
            {items.map((item, i) => (
              <div
                key={item.id}
                style={s.thumb}
                onClick={() => setLightbox(i)}
                title={item.caption ?? ''}
              >
                <img src={item.sas_url} alt={item.caption ?? ''} style={{ ...imgStyle, cursor: 'pointer' }} />
              </div>
            ))}
          </div>

          {/* Lightbox */}
          {lightbox != null && (
            <div style={s.lightboxOverlay} onClick={() => setLightbox(null)}>
              <div style={s.lightboxInner} onClick={e => e.stopPropagation()}>
                <img
                  src={items[lightbox].sas_url}
                  alt={items[lightbox].caption ?? ''}
                  style={{ maxWidth: '90vw', maxHeight: '80vh', borderRadius: 8 }}
                />
                {items[lightbox].caption && (
                  <p style={{ ...s.caption, color: '#e4e7ef', marginTop: 8 }}>{items[lightbox].caption}</p>
                )}
                <button style={s.closeBtn} onClick={() => setLightbox(null)}>✕</button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Carousel ── */}
      {displayMode === 'carousel' && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
            <img
              src={items[carouselIdx].sas_url}
              alt={items[carouselIdx].caption ?? ''}
              style={imgStyle}
            />
            {items.length > 1 && (
              <div style={s.dots}>
                {items.map((_, i) => (
                  <span
                    key={i}
                    style={{ ...s.dot, background: i === carouselIdx ? '#38bdf8' : '#374151' }}
                    onClick={() => setCarouselIdx(i)}
                  />
                ))}
              </div>
            )}
          </div>
          {items[carouselIdx].caption && (
            <p style={s.caption}>{items[carouselIdx].caption}</p>
          )}
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    padding: '12px 14px',
    overflow: 'hidden',
  },
  header: {
    marginBottom: 10,
    flexShrink: 0,
  },
  title: {
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#6b7280',
    fontSize: 13,
    background: '#1a1d27',
    borderRadius: 8,
    border: '1px solid #252a3a',
  },
  caption: {
    fontSize: 12,
    color: '#6b7280',
    margin: 0,
    flexShrink: 0,
  },
  thumbGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))',
    gap: 8,
    flex: 1,
    overflow: 'auto',
  },
  thumb: {
    aspectRatio: '1',
    borderRadius: 6,
    overflow: 'hidden',
    border: '1px solid #252a3a',
  },
  lightboxOverlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.85)',
    zIndex: 1000,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  lightboxInner: {
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  closeBtn: {
    position: 'absolute',
    top: -36,
    right: 0,
    background: 'none',
    border: 'none',
    color: '#e4e7ef',
    fontSize: 20,
    cursor: 'pointer',
    width: 'auto',
  },
  dots: {
    position: 'absolute',
    bottom: 8,
    left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex',
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    cursor: 'pointer',
    display: 'inline-block',
    transition: 'background 0.2s',
  },
};
