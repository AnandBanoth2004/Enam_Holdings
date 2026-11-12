"use client";

import { Search } from "lucide-react";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";

export function ResearchTickerForm() {
  const [ticker, setTicker] = useState("");
  const [message, setMessage] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ticker.trim()) {
      setMessage("Enter a company name or ticker to prepare a research request.");
      return;
    }

    setMessage("Research sources are not connected yet. No company lookup was performed.");
  }

  return (
    <div>
      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="company-ticker">Company name or NSE ticker</label>
        <div className="flex min-h-11 flex-1 items-center gap-2 rounded-md border border-line bg-white px-3 focus-within:ring-2 focus-within:ring-info">
          <Search aria-hidden="true" className="text-ink-muted" size={17} />
          <input
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-muted"
            id="company-ticker"
            onChange={(event) => {
              setTicker(event.target.value);
              setMessage("");
            }}
            placeholder="e.g. RELIANCE or a company name"
            value={ticker}
          />
        </div>
        <Button type="submit">Prepare research</Button>
      </form>
      {message ? <p aria-live="polite" className="mt-3 text-xs text-caution">{message}</p> : null}
      <p className="mt-3 text-[11px] leading-5 text-ink-muted">
        Research will use company and exchange primary sources only. Any supported NSE ticker is intended; this setup has not connected the source adapters yet.
      </p>
    </div>
  );
}
