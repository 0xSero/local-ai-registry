import { cards, card } from "@/lib/registry";
import { json, gpu } from "@/lib/api";
export const dynamic = "force-static";
export const generateStaticParams = () => cards.map((c) => ({ card: c.id }));
export async function GET(_: Request, { params }: { params: Promise<{ card: string }> }) {
  const c = card((await params).card);
  return c ? json(gpu(c)) : json({ error: "unknown gpu" }, 404);
}
