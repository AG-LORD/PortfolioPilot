"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Notice } from "@/components/ui/primitives";
import { apiFetch, getAccessToken } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getErrorMessage } from "@/lib/errors";

const INPUT = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

async function requireToken(): Promise<string> {
  const accessToken = await getAccessToken();
  if (!accessToken) throw new Error("You are signed out. Please log in again.");
  return accessToken;
}

function DialogFrame({ titleId, title, onClose, children }: { titleId: string; title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="p-6">
      <div className="mb-5 flex items-start justify-between gap-3">
        <h2 id={titleId} className="text-xl font-bold">
          {title}
        </h2>
        <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </Button>
      </div>
      {children}
    </div>
  );
}

// --- Record a trade manually -------------------------------------------------------

function RecordTradeForm({ portfolioId, onClose, onRecorded }: { portfolioId: string; onClose: () => void; onRecorded: () => Promise<void> }) {
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const quantity = Number(shares);
    const priceValue = Number(price);
    const feesValue = Number(fees);
    if (!ticker.trim() || !Number.isInteger(quantity) || quantity <= 0 || !(priceValue > 0) || !(feesValue >= 0)) {
      setError("Enter a ticker, a whole number of shares, a positive price and non-negative fees.");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      const accessToken = await requireToken();
      await apiFetch(`/portfolios/${portfolioId}/transactions`, accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          transaction_type: side,
          quantity: quantity.toString(),
          price: priceValue.toFixed(2),
          fees: feesValue.toFixed(2),
        }),
      });
      await onRecorded();
      onClose();
    } catch (err) {
      console.error("Failed to record transaction:", err);
      setError(getErrorMessage(err, "Unable to record this trade."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <DialogFrame titleId="record-trade-title" title="Record a trade manually" onClose={onClose}>
      <p id="record-trade-help" className="-mt-2 mb-5 text-sm text-muted-foreground">
        For trades made outside your plan. Plan orders are recorded from the Plan tab.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <div className="inline-flex rounded-md border border-border bg-muted p-1" role="group" aria-label="Transaction side">
          {(["BUY", "SELL"] as const).map((option) => (
            <button
              type="button"
              key={option}
              aria-pressed={side === option}
              onClick={() => setSide(option)}
              className={cn(
                "rounded px-4 py-1.5 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                side === option ? "bg-card text-foreground shadow-sm" : "text-muted-foreground",
              )}
            >
              {option === "BUY" ? "Buy" : "Sell"}
            </button>
          ))}
        </div>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">NSE ticker</span>
          <input className={INPUT} value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="TCS" autoComplete="off" autoFocus />
        </label>
        <div className="grid grid-cols-3 gap-3">
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Shares</span>
            <input className={INPUT} type="number" inputMode="numeric" min="1" step="1" value={shares} onChange={(e) => setShares(e.target.value)} />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Price (₹)</span>
            <input className={INPUT} type="number" inputMode="decimal" min="0.01" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Fees (₹)</span>
            <input className={INPUT} type="number" inputMode="decimal" min="0" step="0.01" value={fees} onChange={(e) => setFees(e.target.value)} />
          </label>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex flex-col-reverse items-stretch justify-between gap-3 pt-2 sm:flex-row sm:items-center">
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck size={15} aria-hidden="true" /> PortfolioPilot never places orders.
          </p>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Recording…" : `Record ${side === "BUY" ? "buy" : "sell"}`}
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}

export function RecordTradeDialog(props: { open: boolean; portfolioId: string; onClose: () => void; onRecorded: () => Promise<void> }) {
  return (
    <Modal open={props.open} onClose={props.onClose} labelledBy="record-trade-title" describedBy="record-trade-help" wide>
      <RecordTradeForm portfolioId={props.portfolioId} onClose={props.onClose} onRecorded={props.onRecorded} />
    </Modal>
  );
}

// --- Add money --------------------------------------------------------------------

function AddMoneyForm({ portfolioId, onClose, onAdded }: { portfolioId: string; onClose: () => void; onAdded: () => Promise<void> }) {
  const [amount, setAmount] = useState("10000");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter an amount greater than ₹0.");
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      const accessToken = await requireToken();
      await apiFetch(`/portfolios/${portfolioId}/capital`, accessToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: value.toFixed(2) }),
      });
      await onAdded();
      onClose();
    } catch (err) {
      console.error("Failed to add money:", err);
      setError(getErrorMessage(err, "Unable to add money right now."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <DialogFrame titleId="add-money-title" title="Add money" onClose={onClose}>
      <p id="add-money-help" className="-mt-2 mb-5 text-sm text-muted-foreground">
        Record cash you moved into this portfolio. It becomes available for new orders.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Amount (₹)</span>
          <input
            className={INPUT}
            type="number"
            inputMode="decimal"
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            autoFocus
          />
        </label>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Adding…" : "Add money"}
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}

export function AddMoneyDialog(props: { open: boolean; portfolioId: string; onClose: () => void; onAdded: () => Promise<void> }) {
  return (
    <Modal open={props.open} onClose={props.onClose} labelledBy="add-money-title" describedBy="add-money-help">
      <AddMoneyForm portfolioId={props.portfolioId} onClose={props.onClose} onAdded={props.onAdded} />
    </Modal>
  );
}

// --- Delete portfolio -------------------------------------------------------------

function DeleteForm({ portfolioId, portfolioName, onClose }: { portfolioId: string; portfolioName: string; onClose: () => void }) {
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matches = typed.trim() === portfolioName.trim();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!matches) return;
    try {
      setDeleting(true);
      setError(null);
      const accessToken = await requireToken();
      await apiFetch(`/portfolios/${portfolioId}`, accessToken, { method: "DELETE" });
      router.push(`/dashboard?deleted=${encodeURIComponent(portfolioName)}`);
    } catch (err) {
      console.error("Failed to delete portfolio:", err);
      setError(getErrorMessage(err, "The portfolio couldn't be deleted. Nothing was removed."));
      setDeleting(false);
    }
  }

  return (
    <DialogFrame titleId="delete-portfolio-title" title="Delete this portfolio?" onClose={onClose}>
      <p id="delete-portfolio-help" className="-mt-2 mb-5 text-sm leading-6 text-muted-foreground">
        This permanently deletes <strong className="text-foreground">{portfolioName}</strong> with its holdings, transactions,
        plans and history. It can&apos;t be undone. Nothing changes at your broker.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Type the portfolio name to confirm</span>
          <input className={INPUT} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={portfolioName} autoComplete="off" autoFocus />
        </label>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={deleting}>
            Cancel
          </Button>
          <Button type="submit" variant="destructive" disabled={!matches || deleting}>
            <Trash2 size={16} aria-hidden="true" />
            {deleting ? "Deleting…" : "Delete portfolio"}
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}

export function DeletePortfolioDialog(props: { open: boolean; portfolioId: string; portfolioName: string; onClose: () => void }) {
  return (
    <Modal open={props.open} onClose={props.onClose} labelledBy="delete-portfolio-title" describedBy="delete-portfolio-help">
      <DeleteForm portfolioId={props.portfolioId} portfolioName={props.portfolioName} onClose={props.onClose} />
    </Modal>
  );
}
