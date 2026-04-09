/**
 * WatchlistPicker — Source selector for the Security Strategies scan page.
 *
 * Props:
 *   selectedSource — { id, name, type: 'watchlist'|'positions', symbolCount, isDefault } | null
 *   onSourceChange(source) — called when user selects a different source
 *
 * Shows:
 *   - User's named watchlists with symbol counts + ⋯ rename/delete menu
 *   - "All Positions" built-in source
 *   - "+ New Watchlist" inline creation
 */

import { useState, useEffect, useRef } from 'react';
import {
  getWatchlistSources,
  createWatchlist,
  renameWatchlist,
  deleteWatchlist,
} from '../api/client';
import './WatchlistPicker.css';

export default function WatchlistPicker({ selectedSource, onSourceChange }) {
  const [open, setOpen]                 = useState(false);
  const [sources, setSources]           = useState(null);
  const [creating, setCreating]         = useState(false);
  const [newName, setNewName]           = useState('');
  const [menuOpenId, setMenuOpenId]     = useState(null);
  const [renamingId, setRenamingId]     = useState(null);
  const [renameName, setRenameName]     = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [busy, setBusy]                 = useState(false);
  const containerRef                    = useRef(null);

  // autoSelect: if true and no source is currently selected, pick the default watchlist.
  // Called with autoSelect=true only on mount so it uses the initial selectedSource value (null).
  async function loadSources(autoSelect = false) {
    try {
      const data = await getWatchlistSources();
      setSources(data);
      if (autoSelect && !selectedSource && data?.watchlists?.length > 0) {
        const def = data.watchlists.find(w => w.is_default) || data.watchlists[0];
        onSourceChange({
          id: def.id,
          name: def.name,
          type: 'watchlist',
          symbolCount: def.symbol_count,
          isDefault: def.is_default,
        });
      }
      return data;
    } catch {
      return null;
    }
  }

  // Initial load — auto-select default if nothing is selected yet
  useEffect(() => { loadSources(true); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    function onMouseDown(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        closeAll();
      }
    }
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [open]);

  function closeAll() {
    setOpen(false);
    setMenuOpenId(null);
    setCreating(false);
    setNewName('');
    setRenamingId(null);
    setConfirmDeleteId(null);
  }

  function selectSource(source) {
    onSourceChange(source);
    closeAll();
  }

  // ── Create new watchlist ───────────────────────────────────────────
  async function handleCreateKeyDown(e) {
    if (e.key === 'Escape') { setCreating(false); setNewName(''); return; }
    if (e.key !== 'Enter') return;
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await createWatchlist(name);
      await loadSources();
      onSourceChange({
        id: created.id,
        name: created.name,
        type: 'watchlist',
        symbolCount: 0,
        isDefault: false,
      });
      setCreating(false);
      setNewName('');
      setOpen(false);
    } catch {
      // silent — backend validation will surface via toast in parent
    } finally {
      setBusy(false);
    }
  }

  // ── Rename watchlist ───────────────────────────────────────────────
  async function handleRenameKeyDown(id, e) {
    if (e.key === 'Escape') { setRenamingId(null); return; }
    if (e.key !== 'Enter') return;
    const name = renameName.trim();
    if (!name) return;
    setBusy(true);
    try {
      await renameWatchlist(id, name);
      await loadSources();
      if (selectedSource?.id === id) {
        onSourceChange({ ...selectedSource, name });
      }
      setRenamingId(null);
      setMenuOpenId(null);
    } catch { /* silent */ } finally {
      setBusy(false);
    }
  }

  // ── Delete watchlist ───────────────────────────────────────────────
  async function handleDelete(id) {
    setBusy(true);
    try {
      await deleteWatchlist(id);
      const data = await loadSources();
      if (selectedSource?.id === id) {
        const def = data?.watchlists?.find(w => w.is_default) || data?.watchlists?.[0];
        if (def) {
          onSourceChange({
            id: def.id,
            name: def.name,
            type: 'watchlist',
            symbolCount: def.symbol_count,
            isDefault: def.is_default,
          });
        }
      }
      setConfirmDeleteId(null);
      setMenuOpenId(null);
    } catch { /* silent */ } finally {
      setBusy(false);
    }
  }

  const label = selectedSource
    ? `${selectedSource.name} (${selectedSource.symbolCount ?? 0})`
    : 'Select source…';

  return (
    <div className="wl-picker" ref={containerRef}>
      {/* Trigger button */}
      <button
        className="wl-trigger"
        onClick={() => setOpen(o => !o)}
        type="button"
        disabled={busy}
      >
        {label} <span className="wl-caret">▾</span>
      </button>

      {open && (
        <div className="wl-dropdown">
          {/* ── User watchlists ── */}
          {(sources?.watchlists || []).map(wl => (
            <div key={wl.id} className="wl-item-wrap">

              {/* Rename input */}
              {renamingId === wl.id ? (
                <div className="wl-rename-wrap">
                  <input
                    className="wl-inline-input"
                    autoFocus
                    value={renameName}
                    onChange={e => setRenameName(e.target.value)}
                    onKeyDown={e => handleRenameKeyDown(wl.id, e)}
                    placeholder="New name…"
                    disabled={busy}
                  />
                </div>
              ) : confirmDeleteId === wl.id ? (
                /* Delete confirmation */
                <div className="wl-confirm-delete">
                  <span className="wl-confirm-text">Delete "{wl.name}"?</span>
                  <button
                    className="wl-btn-danger"
                    onClick={() => handleDelete(wl.id)}
                    disabled={busy}
                  >Delete</button>
                  <button
                    className="wl-btn-cancel"
                    onClick={() => setConfirmDeleteId(null)}
                  >Cancel</button>
                </div>
              ) : (
                /* Normal row */
                <div
                  className={`wl-item${selectedSource?.id === wl.id ? ' wl-item-active' : ''}`}
                  onClick={() => selectSource({
                    id: wl.id,
                    name: wl.name,
                    type: 'watchlist',
                    symbolCount: wl.symbol_count,
                    isDefault: wl.is_default,
                  })}
                >
                  <span className="wl-item-name">{wl.name}</span>
                  <span className="wl-item-count">({wl.symbol_count})</span>
                  <button
                    className="wl-menu-btn"
                    type="button"
                    onClick={e => {
                      e.stopPropagation();
                      setMenuOpenId(menuOpenId === wl.id ? null : wl.id);
                      setConfirmDeleteId(null);
                    }}
                  >⋯</button>
                </div>
              )}

              {/* ⋯ submenu */}
              {menuOpenId === wl.id && renamingId !== wl.id && confirmDeleteId !== wl.id && (
                <div className="wl-menu">
                  <button
                    className="wl-menu-item"
                    onClick={e => {
                      e.stopPropagation();
                      setRenamingId(wl.id);
                      setRenameName(wl.name);
                      setMenuOpenId(null);
                    }}
                  >Rename</button>
                  {!wl.is_default && (
                    <button
                      className="wl-menu-item wl-menu-item-danger"
                      onClick={e => {
                        e.stopPropagation();
                        setConfirmDeleteId(wl.id);
                        setMenuOpenId(null);
                      }}
                    >Delete</button>
                  )}
                </div>
              )}
            </div>
          ))}

          <div className="wl-divider" />

          {/* ── Built-in sources (All Positions, etc.) ── */}
          {(sources?.builtin || []).map(b => (
            <div
              key={b.id}
              className={`wl-item${selectedSource?.id === b.id ? ' wl-item-active' : ''}`}
              onClick={() => selectSource({
                id: b.id,
                name: b.name,
                type: 'positions',
                symbolCount: b.symbol_count,
              })}
            >
              <span className="wl-item-name">{b.name}</span>
              <span className="wl-item-count">({b.symbol_count})</span>
            </div>
          ))}

          <div className="wl-divider" />

          {/* ── New watchlist ── */}
          {creating ? (
            <div className="wl-new-input-wrap">
              <input
                className="wl-inline-input"
                autoFocus
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={handleCreateKeyDown}
                placeholder="Watchlist name…"
                disabled={busy}
              />
            </div>
          ) : (
            <div
              className="wl-item wl-new-action"
              onClick={() => { setCreating(true); setNewName(''); }}
            >
              + New Watchlist
            </div>
          )}
        </div>
      )}
    </div>
  );
}
