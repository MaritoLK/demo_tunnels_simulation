// Hero shown inside the observation frame when no simulation exists.
//
// Why a full hero and not a tiny "no data" label:
//   - On first load the right pane is otherwise a dead dark rectangle.
//     A user who hasn't read the sidebar would stare at it wondering
//     if the app broke.
//   - This gives the app a confident first impression and points the
//     eye to the exact control that starts the flow (Generate World).
//
// Decorative elements (drifting dots, sigil glyph) are absolute-
// positioned and pointer-events:none so they never intercept clicks.
export function EmptyState() {
  return (
    <div className="empty-hero">
      <div className="empty-hero__backdrop" aria-hidden />
      <div className="empty-hero__dots" aria-hidden>
        {Array.from({ length: 10 }, (_, i) => <span key={i} />)}
      </div>

      <div className="empty-hero__card">
        <div className="empty-hero__sigil" aria-hidden>
          {/* Concentric hex — tunnel / honeycomb / colony-cell motif, which
              reads as a real mark rather than a single punctuation glyph.
              The outer hex rotates slowly, the inner sits still, the dot
              pulses — three planes of motion on a static card. */}
          <svg viewBox="0 0 96 96" aria-hidden>
            <polygon className="sigil__hex-outer"
              points="48,6 86,28 86,68 48,90 10,68 10,28" />
            <polygon className="sigil__hex-inner"
              points="48,24 72,36 72,60 48,72 24,60 24,36" />
            <circle className="sigil__dot" cx="48" cy="48" r="6" />
          </svg>
        </div>
        <h2 className="empty-hero__title">no world yet</h2>
        <p className="empty-hero__sub">
          generate a map to drop a seed colony and watch agents forage,
          move, and die.
        </p>
        <ul className="empty-hero__hints">
          <li><span>1</span> pick width, height, seed &amp; agents</li>
          <li><span>2</span> hit <em>Generate World</em></li>
          <li><span>3</span> advance ticks, watch the log</li>
        </ul>
      </div>
    </div>
  );
}
