"use client"

import { useRouter } from "next/navigation"
import { useEffect, useRef, type ReactNode } from "react"

type RecordModalProps = {
  children: ReactNode
  closeHref: string
  titleId: string
}

type ModalCloseButtonProps = {
  children?: ReactNode
  className: string
  closeHref: string
  label: string
  tabIndex?: number
}

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",")

export function ModalCloseButton({ children, className, closeHref, label, tabIndex }: ModalCloseButtonProps) {
  const router = useRouter()
  return (
    <button
      aria-label={label}
      className={className}
      onClick={() => router.replace(closeHref, { scroll: false })}
      tabIndex={tabIndex}
      type="button"
    >
      {children}
    </button>
  )
}

export function RecordModal({ children, closeHref, titleId }: RecordModalProps) {
  const dialogRef = useRef<HTMLElement>(null)
  const router = useRouter()

  useEffect(() => {
    const dialog = dialogRef.current
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    dialog?.focus()

    function containFocus(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault()
        router.replace(closeHref, { scroll: false })
        return
      }
      if (event.key !== "Tab" || !dialog) return

      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        .filter((element) => element.getClientRects().length > 0)
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === dialog || active === first || !dialog.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener("keydown", containFocus)
    return () => {
      document.removeEventListener("keydown", containFocus)
      document.body.style.overflow = previousOverflow
      previous?.focus()
    }
  }, [closeHref, router])

  return (
    <div className="modal-layer">
      <ModalCloseButton
        className="modal-scrim"
        closeHref={closeHref}
        label="Close record details"
        tabIndex={-1}
      />
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className="record-modal"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        {children}
      </section>
    </div>
  )
}
