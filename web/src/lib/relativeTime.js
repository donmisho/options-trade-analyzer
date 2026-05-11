/**
 * Format a date as relative time (SharePoint convention).
 * No external dependencies — native JS only.
 *
 * | Age         | Display              |
 * |-------------|----------------------|
 * | < 60s       | just now             |
 * | < 60 min    | 12 minutes ago       |
 * | < 24 h      | 3 hours ago          |
 * | < 7 days    | 2 days ago           |
 * | ≥ 7 days    | May 3  (current yr)  |
 * | ≥ 1 year    | May 3, 2025          |
 */
export function formatRelativeTime(date) {
  if (!date) return null;
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return null;

  const now = Date.now();
  const diffMs = now - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;
  if (diffHr < 24) return `${diffHr} hour${diffHr !== 1 ? 's' : ''} ago`;
  if (diffDay < 7) return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;

  const nowYear = new Date().getFullYear();
  const month = d.toLocaleString('en-US', { month: 'short' });
  const day = d.getDate();
  if (d.getFullYear() === nowYear) return `${month} ${day}`;
  return `${month} ${day}, ${d.getFullYear()}`;
}
