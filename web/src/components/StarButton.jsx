/**
 * StarButton — Toggles a trade in/out of favorites.
 *
 * WHY a dedicated component?
 * Every results table row needs this same star button with the same
 * behavior: check if favorited, toggle on click, animate, update context.
 * Rather than repeating this logic in every screen, we extract it once.
 *
 * Props:
 *   trade — The trade object to favorite (must have .id and .label)
 */

import { useApp } from '../context/AppContext';
import './StarButton.css';

export default function StarButton({ trade }) {
  const { isFavorited, addFavorite, removeFavorite } = useApp();
  const active = isFavorited(trade.id);

  const handleClick = (e) => {
    e.stopPropagation(); // Don't trigger row click if we add one later
    if (active) {
      removeFavorite(trade.id);
    } else {
      addFavorite(trade);
    }
  };

  return (
    <button
      className={`star-btn ${active ? 'favorited' : ''}`}
      onClick={handleClick}
      title={active ? 'Remove from favorites' : 'Add to favorites'}
      aria-label={active ? 'Remove from favorites' : 'Add to favorites'}
    >
      {active ? '★' : '☆'}
    </button>
  );
}
