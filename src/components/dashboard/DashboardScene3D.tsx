import { useEffect, useRef } from 'react'
import * as THREE from 'three'

function createRoundedRectShape(width: number, height: number, radius: number) {
  const shape = new THREE.Shape()
  const x = -width / 2
  const y = -height / 2

  shape.moveTo(x + radius, y)
  shape.lineTo(x + width - radius, y)
  shape.quadraticCurveTo(x + width, y, x + width, y + radius)
  shape.lineTo(x + width, y + height - radius)
  shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  shape.lineTo(x + radius, y + height)
  shape.quadraticCurveTo(x, y + height, x, y + height - radius)
  shape.lineTo(x, y + radius)
  shape.quadraticCurveTo(x, y, x + radius, y)

  return shape
}

function createPlate(material: THREE.Material, scale = 1) {
  const shape = createRoundedRectShape(3.8 * scale, 2.4 * scale, 0.34 * scale)
  const geometry = new THREE.ExtrudeGeometry(shape, {
    bevelEnabled: true,
    bevelSegments: 10,
    bevelSize: 0.06 * scale,
    bevelThickness: 0.06 * scale,
    curveSegments: 24,
    depth: 0.24 * scale,
    steps: 1,
  })

  geometry.center()

  return new THREE.Mesh(geometry, material)
}

export function DashboardScene3D() {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current

    if (!host) {
      return
    }

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100)
    camera.position.set(0, 0.35, 6.6)
    camera.lookAt(0, 0, 0)

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance',
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.24
    host.appendChild(renderer.domElement)

    const rootGroup = new THREE.Group()
    rootGroup.scale.setScalar(1.12)
    scene.add(rootGroup)
    scene.fog = new THREE.Fog(0x07101a, 9, 16)

    const ambientLight = new THREE.AmbientLight(0xd7f6ff, 1.3)
    scene.add(ambientLight)

    const keyLight = new THREE.PointLight(0x4ff9d5, 28, 22, 1.6)
    keyLight.position.set(4.5, 4, 6)
    scene.add(keyLight)

    const rimLight = new THREE.PointLight(0xffdf86, 16, 18, 1.9)
    rimLight.position.set(-5, -2, 4)
    scene.add(rimLight)

    const baseMaterial = new THREE.MeshPhysicalMaterial({
      clearcoat: 1,
      clearcoatRoughness: 0.16,
      color: 0x1f4566,
      emissive: 0x0e314b,
      emissiveIntensity: 0.85,
      metalness: 0.6,
      roughness: 0.18,
      sheen: 0.7,
      sheenColor: new THREE.Color(0x74e7d4),
      transmission: 0.1,
    })
    const glassMaterial = new THREE.MeshPhysicalMaterial({
      clearcoat: 1,
      clearcoatRoughness: 0.08,
      color: 0xbafdf2,
      emissive: 0x2fd0bc,
      emissiveIntensity: 0.26,
      metalness: 0.18,
      opacity: 0.34,
      roughness: 0.1,
      transparent: true,
      transmission: 0.78,
    })

    const basePlate = createPlate(baseMaterial, 1)
    basePlate.rotation.x = -0.95
    basePlate.rotation.z = 0.22
    basePlate.position.set(0, -1.05, 0)
    rootGroup.add(basePlate)

    const topPlate = createPlate(glassMaterial, 0.92)
    topPlate.rotation.x = -0.95
    topPlate.rotation.z = -0.18
    topPlate.position.set(0.18, 1.05, 0.2)
    rootGroup.add(topPlate)

    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(2.2, 0.05, 24, 140),
      new THREE.MeshBasicMaterial({
        color: 0x74e7d4,
        opacity: 0.48,
        transparent: true,
      }),
    )
    ring.rotation.x = 1.35
    ring.rotation.z = 0.4
    ring.position.set(0, 0.2, -0.4)
    rootGroup.add(ring)

    const wireframe = new THREE.LineSegments(
      new THREE.EdgesGeometry(topPlate.geometry),
      new THREE.LineBasicMaterial({
        color: 0xe7fbff,
        opacity: 0.75,
        transparent: true,
      }),
    )
    wireframe.position.copy(topPlate.position)
    wireframe.rotation.copy(topPlate.rotation)
    rootGroup.add(wireframe)

    const barGroup = new THREE.Group()
    const barColors = [0x74e7d4, 0xb0fff1, 0xffd07a, 0x6fd9ff]

    for (const [index, color] of barColors.entries()) {
      const bar = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, 0.48 + index * 0.2, 0.18),
        new THREE.MeshStandardMaterial({
          color,
          emissive: color,
          emissiveIntensity: 0.95,
          metalness: 0.45,
          roughness: 0.2,
        }),
      )

      bar.position.set(-0.65 + index * 0.42, 0.15 + index * 0.08, 1.06)
      barGroup.add(bar)
    }

    barGroup.rotation.x = -0.92
    barGroup.rotation.z = 0.2
    barGroup.position.set(-0.2, -0.3, 0)
    rootGroup.add(barGroup)

    const pointCount = 180
    const pointPositions = new Float32Array(pointCount * 3)

    for (let index = 0; index < pointCount; index += 1) {
      const angle = (index / pointCount) * Math.PI * 2
      const radius = 1.4 + Math.sin(index * 0.37) * 0.55
      pointPositions[index * 3] = Math.cos(angle) * radius
      pointPositions[index * 3 + 1] = (Math.random() - 0.5) * 2.4
      pointPositions[index * 3 + 2] = Math.sin(angle) * radius
    }

    const pointsGeometry = new THREE.BufferGeometry()
    pointsGeometry.setAttribute('position', new THREE.BufferAttribute(pointPositions, 3))
    const points = new THREE.Points(
      pointsGeometry,
      new THREE.PointsMaterial({
        color: 0xc5fff4,
        size: 0.072,
        transparent: true,
        opacity: 0.82,
      }),
    )
    points.rotation.x = 0.5
    rootGroup.add(points)

    const signalCore = new THREE.Mesh(
      new THREE.SphereGeometry(0.18, 24, 24),
      new THREE.MeshBasicMaterial({
        color: 0x89fff0,
        transparent: true,
        opacity: 0.9,
      }),
    )
    signalCore.position.set(0.05, 0.25, 1.15)
    rootGroup.add(signalCore)

    const pointer = new THREE.Vector2(0, 0)
    const clock = new THREE.Clock()

    const handlePointerMove = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
    }

    const resize = () => {
      const { clientHeight, clientWidth } = host
      camera.aspect = clientWidth / clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(clientWidth, clientHeight, false)
    }

    const resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(host)
    host.addEventListener('pointermove', handlePointerMove)
    resize()

    let frame = 0

    const animate = () => {
      const elapsed = clock.getElapsedTime()
      rootGroup.rotation.y = elapsed * 0.18 + pointer.x * 0.18
      rootGroup.rotation.x = Math.sin(elapsed * 0.7) * 0.05 + pointer.y * 0.12
      ring.rotation.z = elapsed * 0.36
      points.rotation.y = -elapsed * 0.11
      signalCore.scale.setScalar(1 + Math.sin(elapsed * 2.3) * 0.14)
      topPlate.position.y = 1.05 + Math.sin(elapsed * 1.25) * 0.08
      basePlate.position.y = -1.05 + Math.cos(elapsed * 0.85) * 0.05
      wireframe.position.y = topPlate.position.y
      barGroup.position.y = Math.sin(elapsed * 1.8) * 0.08 - 0.3

      renderer.render(scene, camera)
      frame = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      if (frame) {
        cancelAnimationFrame(frame)
      }

      resizeObserver.disconnect()
      host.removeEventListener('pointermove', handlePointerMove)
      host.removeChild(renderer.domElement)
      pointsGeometry.dispose()
      signalCore.geometry.dispose()
      signalCore.material.dispose()
      renderer.dispose()
      basePlate.geometry.dispose()
      topPlate.geometry.dispose()
      ring.geometry.dispose()
      wireframe.geometry.dispose()
    }
  }, [])

  return <div ref={hostRef} className="relative h-[25rem] w-full" />
}
