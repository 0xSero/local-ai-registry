import catalog from "../../../../../dist/catalog.json";
import { json } from "@/lib/api";
export const dynamic = "force-static";
export const GET = () => json(catalog);
