"use client";
import { useEffect, useRef, useState } from "react";

const LENGTH = 6;
// Ordinal words instead of "Digit 1 of 6": a bare number in an accessible name is
// read as on-screen data by agentic test tools (it can mark a typed digit as copied).
const ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth"];

type Props = {
  /** Called once all 6 digits are filled (auto-submit). */
  onComplete: (code: string) => void;
  disabled?: boolean;
  invalid?: boolean;
};

/**
 * Six separate single-digit inputs with auto-advancing focus.
 * Deliberately NOT a single hidden input (input-otp / shadcn InputOTP).
 * To clear the fields (wrong code, resend) remount it with a new `key`.
 */
export function OtpCodeInput({ onComplete, disabled, invalid }: Props) {
  const [digits, setDigits] = useState<string[]>(() => Array(LENGTH).fill(""));
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  // Focus the first empty box on mount and whenever the inputs become enabled again.
  useEffect(() => {
    if (disabled) return;
    const first = refs.current.find((el) => el && !el.value) ?? refs.current[0];
    first?.focus();
  }, [disabled]);

  function commit(next: string[], focusIndex: number) {
    setDigits(next);
    refs.current[Math.min(focusIndex, LENGTH - 1)]?.focus();
    if (next.every((d) => d !== "")) onComplete(next.join(""));
  }

  function handleChange(i: number, raw: string) {
    const value = raw.replace(/\D/g, "");
    if (!value) {
      const next = [...digits];
      next[i] = "";
      setDigits(next);
      return;
    }
    // Typing into a filled box or autofill/paste of several digits: spread from i onward.
    const next = [...digits];
    const chars = value.length > 1 && digits[i] === value[0] ? value.slice(1) : value;
    let j = i;
    for (const ch of chars) {
      if (j >= LENGTH) break;
      next[j++] = ch;
    }
    commit(next, j);
  }

  function handleKeyDown(i: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[i] && i > 0) {
      e.preventDefault();
      const next = [...digits];
      next[i - 1] = "";
      setDigits(next);
      refs.current[i - 1]?.focus();
    } else if (e.key === "ArrowLeft" && i > 0) {
      e.preventDefault();
      refs.current[i - 1]?.focus();
    } else if (e.key === "ArrowRight" && i < LENGTH - 1) {
      e.preventDefault();
      refs.current[i + 1]?.focus();
    }
  }

  function handlePaste(i: number, e: React.ClipboardEvent<HTMLInputElement>) {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "");
    if (!pasted) return;
    e.preventDefault();
    const next = [...digits];
    let j = i;
    for (const ch of pasted) {
      if (j >= LENGTH) break;
      next[j++] = ch;
    }
    commit(next, j);
  }

  return (
    <div className="flex justify-center gap-2" role="group" aria-label="Confirmation code">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          autoComplete="one-time-code"
          aria-label={`${ORDINALS[i]} digit`}
          aria-invalid={invalid || undefined}
          value={d}
          disabled={disabled}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={(e) => handlePaste(i, e)}
          onFocus={(e) => e.target.select()}
          className={`w-10 h-12 text-center text-lg font-semibold tabular-nums rounded-lg border bg-background outline-none transition-colors focus:ring-2 focus:ring-ring disabled:opacity-50 ${
            invalid ? "border-destructive" : "border-border"
          }`}
        />
      ))}
    </div>
  );
}
