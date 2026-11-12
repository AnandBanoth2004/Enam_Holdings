"use client";

import { useEffect, useState } from "react";
import { fetchApiHealth } from "@/lib/api-client";

type Status = "checking" | "online" | "offline";

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();

    fetchApiHealth(controller.signal)
      .then((health) => setStatus(health.status))
      .catch(() => {
        if (!controller.signal.aborted) setStatus("offline");
      });

    return () => controller.abort();
  }, []);

  const copy = {
    checking: "API checking",
    online: "API online",
    offline: "API offline",
  }[status];

  return (
    <span
      aria-live="polite"
      className="inline-flex min-h-9 items-center gap-2 rounded-md border border-line bg-surface px-2.5 text-[11px] font-medium text-ink-secondary"
    >
      <span
        aria-hidden="true"
        className={`size-1.5 rounded-full ${
          status === "online"
            ? "bg-positive"
            : status === "offline"
              ? "bg-caution"
              : "animate-pulse bg-ink-muted"
        }`}
      />
      {copy}
    </span>
  );
}
