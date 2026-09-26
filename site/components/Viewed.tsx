"use client";
import { useEffect } from "react";
import { track } from "./PostHog";
export default function Viewed({ event, props }: { event: string; props: Record<string, unknown> }) {
  useEffect(() => { track(event, props); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}
