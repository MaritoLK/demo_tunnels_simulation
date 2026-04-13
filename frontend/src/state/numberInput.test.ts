import { describe, it, expect } from 'vitest';
import { parseNumberInput } from './numberInput';

// `<input type="number">` with a React-controlled `value` cannot be
// cleared without snapping the value. `onChange(Number(e.target.value))`
// is the tempting one-liner, but `Number('') === 0`, so backspacing the
// field writes 0 into state. On a width/height field, submitting then
// sends `{ width: 0 }` which the backend 400s. The fix is to return the
// previous value when the raw string is empty — i.e. treat "the user is
// mid-edit" as "don't clobber state." Same for garbage input that
// parses to NaN.
describe('parseNumberInput', () => {
  it('keeps previous value when input cleared', () => {
    expect(parseNumberInput('', 42)).toBe(42);
  });

  it('parses a valid integer string', () => {
    expect(parseNumberInput('40', 0)).toBe(40);
  });

  it('parses a negative number', () => {
    expect(parseNumberInput('-7', 0)).toBe(-7);
  });

  it('parses a zero value explicitly typed', () => {
    // User typed "0" — that is an intentional zero, not an empty field.
    expect(parseNumberInput('0', 42)).toBe(0);
  });

  it('keeps previous value when input is non-numeric garbage', () => {
    expect(parseNumberInput('abc', 42)).toBe(42);
  });

  it('keeps previous value when input is only a minus sign', () => {
    // Transient state while typing a negative number: "-" parses to NaN.
    expect(parseNumberInput('-', 42)).toBe(42);
  });

  it('parses a floating value', () => {
    expect(parseNumberInput('3.14', 0)).toBe(3.14);
  });

  it('keeps previous value when input is whitespace', () => {
    // `Number('  ')` is 0 — an accidental zero, not an intent.
    expect(parseNumberInput('   ', 42)).toBe(42);
  });
});
