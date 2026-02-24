/**
 * Header — Top bar with logo, nav tabs, and favorites badge.
 *
 * WHY NavLink instead of <a> tags?
 * React Router's NavLink automatically adds an "active" class
 * to the link that matches the current URL. This means the
 * blue underline on the active tab is handled by CSS alone —
 * no manual state tracking needed.
 */

import { NavLink } from 'react-router-dom';
import Logo from '../assets/Logo';
import { useApp } from '../context/AppContext';
import './Header.css';

export default function Header() {
  const { favorites } = useApp();
  const favCount = favorites.length;

  return (
    <header className="header">
      <div className="logo">
        <Logo size={28} />
        <span>Options Analyzer</span>
      </div>
      <nav className="nav-tabs">
        <NavLink to="/verticals" className="nav-tab">
          Vertical Spreads
        </NavLink>
        <NavLink to="/long-calls" className="nav-tab">
          Long Calls
        </NavLink>
        <NavLink to="/directional" className="nav-tab">
          Directional Compare
        </NavLink>
        <NavLink to="/favorites" className="nav-tab">
          ★ Favorites
          {favCount > 0 && <span className="fav-count">{favCount}</span>}
        </NavLink>
      </nav>
    </header>
  );
}
