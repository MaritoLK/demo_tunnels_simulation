// Parse the raw string from a `<input type="number">` onChange event
// into a number, preserving the previous value when the input is
// empty, whitespace-only, or unparseable.
//
// Prevents `Number('') === 0` from silently snapping a cleared field
// to 0, which then gets sent to the API on submit (PUT /simulation
// rejects width=0 with 400).
export function parseNumberInput(raw: string, previous: number): number {
  if (raw.trim() === '') return previous;
  const n = Number(raw);
  return Number.isNaN(n) ? previous : n;
}
