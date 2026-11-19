"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, OtpApiError, type OtpChallenge } from "@/lib/api";
import { OtpCodeInput } from "@/components/OtpCodeInput";

const PURPOSE = "delete_all_transactions";

type Phase = "idle" | "confirm" | "requesting" | "code" | "verifying" | "deleting";

export function DeleteAllTransactions() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** true when the challenge is dead (locked/expired) and a fresh code is required */
  const [blocked, setBlocked] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [resetKey, setResetKey] = useState(0);
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);

  const open = phase !== "idle";

  // Native modal <dialog>: showModal() makes the page behind it inert (focus trap,
  // hidden from assistive tech and test agents) and gives Esc-to-cancel for free.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);
  const resendIn = Math.max(0, Math.ceil((resendAt - now) / 1000));

  // Tick the "Resend in Ns" countdown while the code step is shown.
  useEffect(() => {
    if (!challenge || !open) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [challenge, open]);

  function close() {
    setPhase("idle");
    setChallenge(null);
    setError(null);
    setBlocked(false);
  }

  function applyChallenge(ch: OtpChallenge) {
    setChallenge(ch);
    setResendAt(Date.now() + ch.resend_in * 1000);
    setNow(Date.now());
    setError(null);
    setBlocked(false);
    setResetKey((k) => k + 1);
    setPhase("code");
  }

  async function requestCode() {
    setPhase("requesting");
    setError(null);
    try {
      applyChallenge(await api.requestOtp(PURPOSE));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the code");
      setPhase("confirm");
    }
  }

  async function resend() {
    if (!challenge || resendIn > 0) return;
    try {
      applyChallenge(await api.resendOtp(challenge.challenge_id));
      toast.success("New code sent", { description: `Check ${challenge.email_hint}` });
    } catch (err) {
      if (err instanceof OtpApiError && err.resendIn) {
        setResendAt(Date.now() + err.resendIn * 1000);
      } else if (err instanceof OtpApiError && err.status === 404) {
        // challenge gone (expired / finished) — start a fresh one
        await requestCode();
      } else {
        setError(err instanceof Error ? err.message : "Could not resend the code");
      }
    }
  }

  async function submit(code: string) {
    if (!challenge || phase !== "code" || blocked) return;
    setPhase("verifying");
    setError(null);
    let token: string;
    try {
      token = (await api.verifyOtp(challenge.challenge_id, code)).confirmation_token;
    } catch (err) {
      if (err instanceof OtpApiError) {
        if (err.status === 400) {
          const left = err.attemptsLeft;
          setError(
            `Incorrect code${left !== undefined ? ` — ${left} attempt${left === 1 ? "" : "s"} left` : ""}`,
          );
        } else {
          setError(err.message);
          setBlocked(err.status === 429 || err.status === 410 || err.status === 404);
        }
      } else {
        setError("Could not verify the code");
      }
      setResetKey((k) => k + 1);
      setPhase("code");
      return;
    }

    setPhase("deleting");
    try {
      const { deleted } = await api.deleteAllTransactions(token);
      close();
      router.refresh();
      toast.success("All transactions deleted", {
        description: `${deleted} transaction${deleted === 1 ? "" : "s"} removed`,
      });
    } catch (err: unknown) {
      toast.error("Delete failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      close();
    }
  }

  const busy = phase === "requesting" || phase === "verifying" || phase === "deleting";

  return (
    <>
      <button
        onClick={() => setPhase("confirm")}
        disabled={open}
        className="h-8 px-3.5 rounded-lg text-sm font-medium border border-destructive/40 text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
      >
        {phase === "deleting" ? "Deleting…" : "Delete all"}
      </button>

      <dialog
        ref={dialogRef}
        aria-labelledby="delete-all-title"
        onCancel={(e) => {
          e.preventDefault();
          if (phase !== "deleting") close();
        }}
        className="m-auto bg-background text-foreground border border-border rounded-xl shadow-2xl w-[calc(100%-2rem)] max-w-sm p-0 backdrop:bg-black/50"
      >
        {open && (
          <div className="p-6 flex flex-col gap-4">
            {phase === "confirm" || phase === "requesting" ? (
              <>
                <div>
                  <h2 id="delete-all-title" className="text-sm font-semibold">Delete all transactions?</h2>
                  <p className="text-xs text-muted-foreground mt-1.5">
                    This will permanently delete every transaction and cannot be undone.
                    Category rules will not be affected. We&apos;ll e-mail you a confirmation code first.
                  </p>
                </div>
                {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={close}
                    className="text-xs px-3 py-1.5 rounded-md text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={requestCode}
                    disabled={busy}
                    className="text-xs px-4 py-1.5 rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 transition-colors font-medium"
                  >
                    {phase === "requesting" ? "Sending code…" : "Send confirmation code"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div>
                  <h2 id="delete-all-title" className="text-sm font-semibold">Enter confirmation code</h2>
                  <p className="text-xs text-muted-foreground mt-1.5">
                    We sent a six-digit code to <span className="font-medium text-foreground">{challenge?.email_hint}</span>.
                    Enter it to delete all transactions.
                  </p>
                </div>

                <OtpCodeInput
                  key={resetKey}
                  onComplete={submit}
                  disabled={busy || blocked}
                  invalid={!!error}
                />

                <p role="alert" aria-live="assertive" className="text-xs text-destructive text-center min-h-4">
                  {phase === "verifying" ? "" : error}
                </p>
                {phase === "verifying" && (
                  <p className="text-xs text-muted-foreground text-center -mt-3">Checking…</p>
                )}
                {phase === "deleting" && (
                  <p className="text-xs text-muted-foreground text-center -mt-3">Deleting…</p>
                )}

                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={resend}
                    disabled={resendIn > 0 || busy}
                    className="text-xs px-2 py-1.5 rounded-md text-primary hover:underline disabled:no-underline disabled:text-muted-foreground disabled:cursor-not-allowed tabular-nums"
                  >
                    {resendIn > 0 ? `Resend in ${resendIn}s` : "Resend code"}
                  </button>
                  <button
                    onClick={close}
                    disabled={phase === "deleting"}
                    className="text-xs px-3 py-1.5 rounded-md text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </dialog>
    </>
  );
}
