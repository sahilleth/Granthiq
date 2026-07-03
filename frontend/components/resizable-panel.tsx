"use client"

import type React from "react"
import { useState, useRef, useCallback, useEffect } from "react"

interface ResizablePanelProps {
  children: React.ReactNode
  defaultWidth: number
  minWidth: number
  maxWidth: number
  side: "left" | "right"
  className?: string
  onResize?: (width: number) => void
}

export function ResizablePanel({
  children,
  defaultWidth,
  minWidth,
  maxWidth,
  side,
  className = "",
  onResize,
}: ResizablePanelProps) {
  const [width, setWidth] = useState(defaultWidth)
  const [isResizing, setIsResizing] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setWidth(defaultWidth)
  }, [defaultWidth])

  const startResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }, [])

  const stopResize = useCallback(() => {
    setIsResizing(false)
  }, [])

  const resize = useCallback(
    (e: MouseEvent) => {
      if (!isResizing || !panelRef.current) return

      const rect = panelRef.current.getBoundingClientRect()
      let newWidth: number

      if (side === "left") {
        newWidth = e.clientX - rect.left
      } else {
        newWidth = rect.right - e.clientX
      }

      newWidth = Math.max(minWidth, Math.min(maxWidth, newWidth))
      setWidth(newWidth)
      onResize?.(newWidth)
    },
    [isResizing, minWidth, maxWidth, side, onResize],
  )

  useEffect(() => {
    if (isResizing) {
      document.addEventListener("mousemove", resize)
      document.addEventListener("mouseup", stopResize)
      document.body.style.cursor = "col-resize"
      document.body.style.userSelect = "none"
    }

    return () => {
      document.removeEventListener("mousemove", resize)
      document.removeEventListener("mouseup", stopResize)
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }
  }, [isResizing, resize, stopResize])

  return (
    <div ref={panelRef} className={`relative flex-shrink-0 h-full ${className}`} style={{ width }}>
      {children}

      {/* Resize Handle - wide invisible hit area with a visible grip */}
      <div
        onMouseDown={startResize}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
        title="Drag to resize"
        className={`
          group absolute top-0 bottom-0 z-20 flex items-center justify-center
          w-4 cursor-col-resize
          ${side === "left" ? "-right-3" : "-left-3"}
        `}
      >
        {/* Track line that brightens on hover / while dragging */}
        <div
          className={`
            h-full w-[3px] rounded-full transition-colors duration-150
            ${isResizing ? "bg-primary" : "bg-border group-hover:bg-primary/60"}
          `}
        />
        {/* Center grip pill */}
        <div
          className={`
            absolute top-1/2 -translate-y-1/2 h-10 w-[5px] rounded-full
            transition-all duration-150
            ${isResizing ? "bg-primary" : "bg-muted-foreground/40 opacity-0 group-hover:opacity-100"}
          `}
        />
      </div>
    </div>
  )
}
