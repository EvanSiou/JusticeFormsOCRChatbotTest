import { useState, useRef, useCallback } from 'react'

/**
 * Image component with hover-to-magnify lens.
 * Shows a circular magnifier that follows the cursor over the image.
 */
function MagnifyImage({ src, alt = 'Document', className = '' }) {
  const containerRef = useRef(null)
  const imgRef = useRef(null)
  const [showLens, setShowLens] = useState(false)
  const [lensStyle, setLensStyle] = useState({})

  const LENS_SIZE = 180
  const ZOOM = 2.5

  const handleMouseEnter = useCallback(() => setShowLens(true), [])
  const handleMouseLeave = useCallback(() => setShowLens(false), [])

  const handleMouseMove = useCallback((e) => {
    const img = imgRef.current
    if (!img) return

    const rect = img.getBoundingClientRect()
    // Cursor position relative to the image element
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    // Fraction across the image (0 to 1)
    const fx = x / rect.width
    const fy = y / rect.height

    // Zoomed background size (based on displayed size, not natural)
    const bgW = rect.width * ZOOM
    const bgH = rect.height * ZOOM

    // Background position: center the zoomed point in the lens
    const bgX = -(fx * bgW - LENS_SIZE / 2)
    const bgY = -(fy * bgH - LENS_SIZE / 2)

    setLensStyle({
      position: 'absolute',
      left: `${x - LENS_SIZE / 2}px`,
      top: `${y - LENS_SIZE / 2}px`,
      width: `${LENS_SIZE}px`,
      height: `${LENS_SIZE}px`,
      borderRadius: '50%',
      border: '3px solid rgba(59, 130, 246, 0.7)',
      boxShadow: '0 0 0 1px rgba(0,0,0,0.1), 0 4px 12px rgba(0,0,0,0.3)',
      backgroundImage: `url(${src})`,
      backgroundRepeat: 'no-repeat',
      backgroundSize: `${bgW}px ${bgH}px`,
      backgroundPosition: `${bgX}px ${bgY}px`,
      pointerEvents: 'none',
      zIndex: 50,
    })
  }, [src, ZOOM, LENS_SIZE])

  return (
    <div
      ref={containerRef}
      className={`relative ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onMouseMove={handleMouseMove}
    >
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        className="max-w-full border rounded"
      />
      {showLens && <div style={lensStyle} />}
    </div>
  )
}

export default MagnifyImage
