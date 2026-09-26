import Link from "next/link"

import { getHardwareMarket } from "@/lib/registry"

function money(amount: number | null, currency: string): string {
  if (amount === null) return "—"
  return `${currency} ${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
}

function day(value: string): string {
  return value.slice(0, 10)
}

export function HardwareMarket({ hardwareId }: { hardwareId: string }) {
  const market = getHardwareMarket(hardwareId)
  if (market.length === 0) return null
  return (
    <section aria-label="Current market prices" className="record-evidence">
      <p className="eyebrow">Current market</p>
      <p className="trust-note">
        Lowest live retailer listings per region, in native currency, from the market price collection. Each row links
        to the underlying observations with retailer and URL.
      </p>
      <table className="flag-table">
        <thead>
          <tr>
            <th>Region</th>
            <th>Lowest new</th>
            <th>Refurbished</th>
            <th>Used</th>
            <th>Listings</th>
            <th>Observed</th>
          </tr>
        </thead>
        <tbody>
          {market.map((row) => (
            <tr key={row.record_id}>
              <td><Link href={`/prices/${row.record_id}`}>{row.region}</Link></td>
              <td>{money(row.lowest_new, row.currency)}</td>
              <td>{money(row.lowest_refurbished, row.currency)}</td>
              <td>{money(row.lowest_used, row.currency)}</td>
              <td>{row.listing_count.toLocaleString("en-US")} · {row.retailer_count.toLocaleString("en-US")} retailers</td>
              <td>{day(row.observed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
