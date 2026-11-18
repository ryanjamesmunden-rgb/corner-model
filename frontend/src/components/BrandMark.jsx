// THE MARK, drawn once, from the same geometry as public/favicon.svg.
//
// The header and the footer were showing lucide's CornerDownRight — a generic arrow
// glyph. It is a reasonable stand-in for "corner" and it is not the logo: the favicon in
// the tab, the account photos and the launch artwork all carry the wedge and the ball,
// so the one surface a member actually looks at was the only one not using the brand.
//
// INLINE SVG RATHER THAN <img src="/favicon.svg">, so it inherits the layout's colours,
// scales without a second request, and cannot flash in late on a slow connection — the
// header is the first thing painted.
//
// The geometry is copied, not imported: favicon.svg is a static asset the browser fetches
// by name and there is nothing to import. Both carry the same note, so a change to the
// shape has to be made in both places on purpose rather than drifting in one.
//
//   ground  (the rounded square, drawn only when `plated`)
//   wedge   #14DBF5 — centre (112,400) r 230, swept from straight up round to the right
//   ball    #F3F5F7 — (360,168) r 46
export default function BrandMark({ className = "h-4 w-4", plated = false, title = "" }) {
  return (
    <svg viewBox="0 0 512 512" className={className}
      role={title ? "img" : "presentation"} aria-hidden={title ? undefined : "true"}
      aria-label={title || undefined} data-testid="brand-mark">
      {title ? <title>{title}</title> : null}
      {/* Plated for the header tile, which paints its own accent square behind the mark;
          bare everywhere else, so the mark takes the colour around it. */}
      {plated && <rect width="512" height="512" rx="112" fill="#0B0F14" />}
      <path d="M112 170 A230 230 0 0 1 342 400 L112 400 Z"
        fill={plated ? "#14DBF5" : "currentColor"} />
      {/* FULL STRENGTH IN BOTH VARIANTS. The ball was drawn at 0.55 so it would read as a
          separate shape in monochrome; on the header's accent tile that made it nearly
          invisible. It does not need the help — favicon.svg's own note is that the ball is
          kept clear of the wedge precisely so the two never fuse, and that gap does the
          separating at any size. */}
      <circle cx="360" cy="168" r="46" fill={plated ? "#F3F5F7" : "currentColor"} />
    </svg>
  );
}
