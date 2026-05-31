import { useEffect, useState, type CSSProperties } from 'react'

const defaultPointer = { x: 62, y: 18 }

export function AmbientBackdrop() {
  const [pointer, setPointer] = useState(defaultPointer)

  useEffect(() => {
    let frame = 0

    const handlePointerMove = (event: PointerEvent) => {
      if (frame) {
        cancelAnimationFrame(frame)
      }

      frame = requestAnimationFrame(() => {
        setPointer({
          x: (event.clientX / window.innerWidth) * 100,
          y: (event.clientY / window.innerHeight) * 100,
        })
      })
    }

    window.addEventListener('pointermove', handlePointerMove)

    return () => {
      if (frame) {
        cancelAnimationFrame(frame)
      }

      window.removeEventListener('pointermove', handlePointerMove)
    }
  }, [])

  const style = {
    '--pointer-x': `${pointer.x}%`,
    '--pointer-y': `${pointer.y}%`,
  } as CSSProperties

  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true" style={style}>
      <div className="ambient-grid absolute inset-0 opacity-55 dark:opacity-70" />
      <div className="ambient-vignette absolute inset-0" />
      <div className="ambient-spotlight absolute inset-0" />
      <div className="ambient-orb ambient-orb-a" />
      <div className="ambient-orb ambient-orb-b" />
      <div className="ambient-orb ambient-orb-c" />
      <div className="ambient-scanline absolute inset-x-0 top-20 h-px" />
    </div>
  )
}
