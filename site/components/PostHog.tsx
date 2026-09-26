"use client";
// PostHog for events and funnels (GPU picked -> recipe viewed -> command copied). Off unless NEXT_PUBLIC_POSTHOG_KEY is set.
import posthog from "posthog-js";
import { useEffect } from "react";
import { usePathname } from "next/navigation";

const KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
let started = false;

export function track(event: string, props: Record<string, unknown> = {}) {
  if (KEY) posthog.capture(event, props);
  // Vercel custom events, where the plan has them
  import("@vercel/analytics").then(({ track }) => track(event, props as Record<string, string | number | boolean | null>)).catch(() => {});
}

export default function PostHog() {
  const path = usePathname();
  useEffect(() => {
    if (!KEY || started) return;
    posthog.init(KEY, { api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com", person_profiles: "identified_only", capture_pageview: false });
    started = true;
  }, []);
  useEffect(() => { if (KEY) posthog.capture("$pageview", { path }); }, [path]);
  return null;
}
