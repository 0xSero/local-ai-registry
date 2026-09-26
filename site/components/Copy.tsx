"use client";
import { useState } from "react";
import { track } from "./PostHog";

export default function Copy({ text, event, props }: { text: string; event: string; props?: Record<string, unknown> }) {
  const [done, setDone] = useState(false);
  return (
    <button className="btn copy" onClick={() => { navigator.clipboard.writeText(text); setDone(true); track(event, props); setTimeout(() => setDone(false), 1500); }}>
      {done ? "Copied" : "Copy"}
    </button>
  );
}
