import { useEffect, useRef, useState, type CSSProperties } from 'react'

const defaultPointer = { x: 62, y: 18 }

export function AmbientBackdrop() {
  const [pointer, setPointer] = useState({
    focusX: defaultPointer.x,
    focusY: defaultPointer.y,
    trailX: defaultPointer.x - 8,
    trailY: defaultPointer.y + 6,
  })
  const focusTargetRef = useRef(defaultPointer)
  const trailTargetRef = useRef({ x: defaultPointer.x - 8, y: defaultPointer.y + 6 })

  useEffect(() => {
    let frame = 0

    const handlePointerMove = (event: PointerEvent) => {
      const x = (event.clientX / window.innerWidth) * 100
      const y = (event.clientY / window.innerHeight) * 100

      focusTargetRef.current = { x, y }
      trailTargetRef.current = {
        x: Math.max(0, Math.min(100, x - 9)),
        y: Math.max(0, Math.min(100, y + 7)),
      }
    }

    const animate = () => {
      setPointer((current) => {
        const nextFocusX = current.focusX + (focusTargetRef.current.x - current.focusX) * 0.16
        const nextFocusY = current.focusY + (focusTargetRef.current.y - current.focusY) * 0.16
        const nextTrailX = current.trailX + (trailTargetRef.current.x - current.trailX) * 0.1
        const nextTrailY = current.trailY + (trailTargetRef.current.y - current.trailY) * 0.1

        return {
          focusX: nextFocusX,
          focusY: nextFocusY,
          trailX: nextTrailX,
          trailY: nextTrailY,
        }
      })

      frame = requestAnimationFrame(animate)
    }

    frame = requestAnimationFrame(animate)
    window.addEventListener('pointermove', handlePointerMove)

    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('pointermove', handlePointerMove)
    }
  }, [])

  const style = {
    '--pointer-x': `${pointer.focusX}%`,
    '--pointer-y': `${pointer.focusY}%`,
    '--pointer-x-unit': pointer.focusX,
    '--pointer-y-unit': pointer.focusY,
    '--pointer-trail-x': `${pointer.trailX}%`,
    '--pointer-trail-y': `${pointer.trailY}%`,
    '--pointer-trail-x-unit': pointer.trailX,
    '--pointer-trail-y-unit': pointer.trailY,
  } as CSSProperties

  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true" style={style}>
      <div className="ambient-grid absolute inset-0 opacity-55 dark:opacity-70" />
      <div className="ambient-tech-lines absolute inset-0 opacity-65 dark:opacity-80" />
      <div className="ambient-vignette absolute inset-0" />
      <div className="ambient-spotlight absolute inset-0" />
      <div className="ambient-neural absolute inset-0" />
      <div className="ambient-pointer-ring absolute inset-0" />
      <div className="ambient-orb ambient-orb-a" />
      <div className="ambient-orb ambient-orb-b" />
      <div className="ambient-orb ambient-orb-c" />
      <div className="ambient-scanline absolute inset-x-0 top-20 h-px" />
    </div>
  )
}
