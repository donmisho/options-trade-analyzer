/**
 * formatDate — single source of truth for all date display in the app.
 *
 * House rule: ALWAYS mm-dd-yyyy. With time: mm-dd-yyyy hh:mm. No exceptions.
 * All date display MUST use these functions. No other date formatting allowed.
 */

/**
 * Format a date to mm-dd-yyyy or mm-dd-yyyy hh:mm
 * @param {Date|string|number} dateInput
 * @param {boolean} includeTime
 * @returns {string}
 */
export function formatDate(dateInput, includeTime = false) {
  if (!dateInput) return '';
  const date = new Date(dateInput);
  if (isNaN(date.getTime())) return '';

  const mm  = String(date.getUTCMonth() + 1).padStart(2, '0');
  const dd  = String(date.getUTCDate()).padStart(2, '0');
  const yyyy = date.getUTCFullYear();

  if (!includeTime) return `${mm}-${dd}-${yyyy}`;

  const hh  = String(date.getUTCHours()).padStart(2, '0');
  const min = String(date.getUTCMinutes()).padStart(2, '0');
  return `${mm}-${dd}-${yyyy} ${hh}:${min}`;
}

/**
 * Format expiration date with DTE: "04-06-2026 (21d)"
 * @param {Date|string|number} dateInput
 * @returns {string}
 */
export function formatExpiry(dateInput) {
  if (!dateInput) return '';
  const date = new Date(dateInput);
  if (isNaN(date.getTime())) return '';

  const formatted = formatDate(dateInput);
  const now       = new Date();
  const diffMs    = date.getTime() - now.getTime();
  const dte       = Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));

  return `${formatted} (${dte}d)`;
}
