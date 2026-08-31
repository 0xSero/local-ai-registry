import Link from "next/link"

import type { RelatedGroup } from "@/app/lib/record-view"

export function RelatedRecords({ groups }: { groups: RelatedGroup[] }) {
  if (groups.length === 0) return null
  return (
    <nav aria-label="Related records" className="related-records">
      <p className="eyebrow">Related records</p>
      <dl>
        {groups.map((group) => (
          <div key={group.key}>
            <dt>{group.label}</dt>
            <dd>
              <ul>
                {group.links.map((link) => (
                  <li key={link.id}><Link href={link.href}>{link.label}</Link></li>
                ))}
              </ul>
              {group.moreHref && (
                <p><Link href={group.moreHref}>All {group.total.toLocaleString()} {group.label.toLowerCase()}</Link></p>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </nav>
  )
}
