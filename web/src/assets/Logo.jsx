/**
 * Options Analyzer Logo — Chart line with insight dot.
 *
 * WHY a React component instead of an <img>?
 * SVG-as-component lets the icon inherit `currentColor` from CSS,
 * so it automatically matches whatever text color the parent sets.
 * If it were an <img>, you'd need a separate SVG file for every
 * color variant.
 */
export default function Logo({ size = 28, className = '' }) {
  return (
    <svg
      viewBox="0 0 28 28"
      width={size}
      height={size}
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M4 20l6-12 4 8 4-4 6 8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="8" r="2" fill="currentColor" opacity="0.4" />
    </svg>
  );
}
