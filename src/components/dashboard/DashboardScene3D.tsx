import { useEffect, useRef } from 'react'
import * as THREE from 'three'

type PulseOrb = {
  mesh: THREE.Mesh
  orbitOffset: number
  orbitRadius: number
  speed: number
  tilt: number
}

type FlareOrb = {
  mesh: THREE.Mesh
  offset: number
}

function createSphereNodes(count: number, radius: number) {
  const positions = new Float32Array(count * 3)
  const vectors: THREE.Vector3[] = []
  const phi = Math.PI * (3 - Math.sqrt(5))

  for (let index = 0; index < count; index += 1) {
    const y = 1 - (index / (count - 1)) * 2
    const radial = Math.sqrt(1 - y * y)
    const theta = phi * index
    const jitter = Math.sin(index * 1.73) * 0.07
    const pointRadius = radius + jitter

    const vector = new THREE.Vector3(
      Math.cos(theta) * radial * pointRadius,
      y * pointRadius,
      Math.sin(theta) * radial * pointRadius,
    )

    vectors.push(vector)
    positions[index * 3] = vector.x
    positions[index * 3 + 1] = vector.y
    positions[index * 3 + 2] = vector.z
  }

  return { positions, vectors }
}

function createConnectionGeometry(vectors: THREE.Vector3[], flaggedIndices: Set<number>) {
  const linePositions: number[] = []
  const lineColors: number[] = []
  const maxDistance = 0.9
  const maxConnectionsPerNode = 3
  const connectionCount = new Array(vectors.length).fill(0)

  for (let sourceIndex = 0; sourceIndex < vectors.length; sourceIndex += 1) {
    for (let targetIndex = sourceIndex + 1; targetIndex < vectors.length; targetIndex += 1) {
      if (connectionCount[sourceIndex] >= maxConnectionsPerNode || connectionCount[targetIndex] >= maxConnectionsPerNode) {
        continue
      }

      const distance = vectors[sourceIndex].distanceTo(vectors[targetIndex])
      if (distance > maxDistance) {
        continue
      }

      connectionCount[sourceIndex] += 1
      connectionCount[targetIndex] += 1

      linePositions.push(
        vectors[sourceIndex].x,
        vectors[sourceIndex].y,
        vectors[sourceIndex].z,
        vectors[targetIndex].x,
        vectors[targetIndex].y,
        vectors[targetIndex].z,
      )

      const isFlagged = flaggedIndices.has(sourceIndex) || flaggedIndices.has(targetIndex)
      const color = new THREE.Color(isFlagged ? 0xff7b66 : 0x85f6e8)

      lineColors.push(color.r, color.g, color.b, color.r, color.g, color.b)
    }
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3))
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3))

  return geometry
}

function createBackgroundPoints(count: number) {
  const positions = new Float32Array(count * 3)

  for (let index = 0; index < count; index += 1) {
    positions[index * 3] = (Math.random() - 0.5) * 16
    positions[index * 3 + 1] = (Math.random() - 0.5) * 10
    positions[index * 3 + 2] = (Math.random() - 0.5) * 10
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  return geometry
}

export function DashboardScene3D() {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current

    if (!host) {
      return
    }

    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog(0x08111a, 10, 20)

    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100)
    camera.position.set(0, 0, 8.4)
    camera.lookAt(0, 0, 0)

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance',
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.06
    host.appendChild(renderer.domElement)

    scene.add(new THREE.AmbientLight(0xe6fffa, 1.25))

    const cyanLight = new THREE.PointLight(0x71f7ea, 34, 26, 1.5)
    cyanLight.position.set(3.5, 2.6, 5.5)
    scene.add(cyanLight)

    const goldLight = new THREE.PointLight(0xffd07a, 18, 18, 1.7)
    goldLight.position.set(-4.8, -2.3, 4.8)
    scene.add(goldLight)

    const redLight = new THREE.PointLight(0xff816d, 10, 14, 1.9)
    redLight.position.set(2.2, -2.4, 4)
    scene.add(redLight)

    const backgroundPoints = new THREE.Points(
      createBackgroundPoints(260),
      new THREE.PointsMaterial({
        color: 0xe8fffb,
        opacity: 0.56,
        size: 0.03,
        transparent: true,
      }),
    )
    scene.add(backgroundPoints)

    const sphereRig = new THREE.Group()
    scene.add(sphereRig)

    const haloPrimary = new THREE.Mesh(
      new THREE.TorusGeometry(2.9, 0.05, 22, 180),
      new THREE.MeshBasicMaterial({
        color: 0x83f6e8,
        opacity: 0.32,
        transparent: true,
      }),
    )
    haloPrimary.rotation.x = 1.16
    haloPrimary.rotation.z = 0.22
    sphereRig.add(haloPrimary)

    const haloSecondary = new THREE.Mesh(
      new THREE.TorusGeometry(2.34, 0.026, 20, 160),
      new THREE.MeshBasicMaterial({
        color: 0xffd07a,
        opacity: 0.24,
        transparent: true,
      }),
    )
    haloSecondary.rotation.x = 0.92
    haloSecondary.rotation.z = -0.38
    sphereRig.add(haloSecondary)

    const sphereCore = new THREE.Mesh(
      new THREE.SphereGeometry(0.42, 32, 32),
      new THREE.MeshPhysicalMaterial({
        clearcoat: 1,
        clearcoatRoughness: 0.08,
        color: 0xa4fff6,
        emissive: 0x3fd1c3,
        emissiveIntensity: 0.74,
        metalness: 0.08,
        roughness: 0.12,
        transmission: 0.45,
      }),
    )
    sphereRig.add(sphereCore)

    const sphereGlow = new THREE.Mesh(
      new THREE.SphereGeometry(0.64, 28, 28),
      new THREE.MeshBasicMaterial({
        color: 0x83f6e8,
        opacity: 0.08,
        transparent: true,
      }),
    )
    sphereRig.add(sphereGlow)

    const flaggedNodeIndices = new Set([14, 41, 92, 137, 166])
    const { positions, vectors } = createSphereNodes(190, 1.92)

    const networkPoints = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({
        color: 0xe5fffb,
        opacity: 0.95,
        size: 0.074,
        transparent: true,
      }),
    )
    networkPoints.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    sphereRig.add(networkPoints)

    const connectionLines = new THREE.LineSegments(
      createConnectionGeometry(vectors, flaggedNodeIndices),
      new THREE.LineBasicMaterial({
        opacity: 0.34,
        transparent: true,
        vertexColors: true,
      }),
    )
    sphereRig.add(connectionLines)

    const sphereShell = new THREE.Mesh(
      new THREE.SphereGeometry(2.02, 22, 22),
      new THREE.MeshBasicMaterial({
        color: 0x9af9ec,
        opacity: 0.045,
        transparent: true,
        wireframe: true,
      }),
    )
    sphereRig.add(sphereShell)

    const pulseOrbs: PulseOrb[] = []
    const pulseMaterial = new THREE.MeshBasicMaterial({
      color: 0xc9fff8,
      opacity: 0.9,
      transparent: true,
    })

    for (const [index, orbitRadius] of [2.45, 2.8, 3.05].entries()) {
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.08, 18, 18), pulseMaterial.clone())
      sphereRig.add(mesh)
      pulseOrbs.push({
        mesh,
        orbitOffset: index * 2.1,
        orbitRadius,
        speed: 0.72 + index * 0.16,
        tilt: 0.5 + index * 0.24,
      })
    }

    const flareOrbs: FlareOrb[] = []
    for (const flareIndex of flaggedNodeIndices) {
      const vector = vectors[flareIndex]
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.11, 18, 18),
        new THREE.MeshBasicMaterial({
          color: 0xff7b66,
          opacity: 0.88,
          transparent: true,
        }),
      )

      mesh.position.copy(vector)
      sphereRig.add(mesh)
      flareOrbs.push({ mesh, offset: flareIndex * 0.13 })
    }

    const pointer = new THREE.Vector2(0, 0)
    const startTime = performance.now()

    const handlePointerMove = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1)
    }

    const handlePointerLeave = () => {
      pointer.x = 0
      pointer.y = 0
    }

    const resize = () => {
      const { clientHeight, clientWidth } = host
      camera.aspect = clientWidth / clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(clientWidth, clientHeight, false)

      sphereRig.position.x = clientWidth >= 1280 ? 1.48 : clientWidth >= 980 ? 1.16 : clientWidth >= 760 ? 0.76 : 0.4
      sphereRig.position.y = clientWidth >= 980 ? 0.08 : clientWidth >= 760 ? 0.3 : 0.54

      const scale = clientWidth >= 1280 ? 1.02 : clientWidth >= 980 ? 0.94 : clientWidth >= 760 ? 0.84 : 0.72
      sphereRig.scale.setScalar(scale)
    }

    const resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(host)
    host.addEventListener('pointermove', handlePointerMove)
    host.addEventListener('pointerleave', handlePointerLeave)
    resize()

    let frame = 0

    const animate = () => {
      const elapsed = (performance.now() - startTime) / 1000

      sphereRig.rotation.y = elapsed * 0.16 + pointer.x * 0.22
      sphereRig.rotation.x = Math.sin(elapsed * 0.42) * 0.08 + pointer.y * 0.12

      haloPrimary.rotation.z = elapsed * 0.18
      haloSecondary.rotation.z = -elapsed * 0.14
      backgroundPoints.rotation.y = elapsed * 0.012

      sphereCore.rotation.y = elapsed * 0.8
      sphereCore.rotation.x = elapsed * 0.38
      sphereCore.scale.setScalar(1 + Math.sin(elapsed * 2.2) * 0.06)
      sphereGlow.scale.setScalar(1 + Math.sin(elapsed * 1.4) * 0.08)
      sphereShell.rotation.y = -elapsed * 0.22
      sphereShell.rotation.x = elapsed * 0.11

      for (const pulse of pulseOrbs) {
        const pulseAngle = elapsed * pulse.speed + pulse.orbitOffset
        pulse.mesh.position.set(
          Math.cos(pulseAngle) * pulse.orbitRadius,
          Math.sin(pulseAngle * pulse.tilt) * 0.95,
          Math.sin(pulseAngle) * pulse.orbitRadius * 0.72,
        )
        pulse.mesh.scale.setScalar(1 + Math.sin(elapsed * 3 + pulse.orbitOffset) * 0.24)
      }

      for (const flare of flareOrbs) {
        const intensity = 1 + Math.sin(elapsed * 3.8 + flare.offset) * 0.38
        flare.mesh.scale.setScalar(intensity)
        if (flare.mesh.material instanceof THREE.MeshBasicMaterial) {
          flare.mesh.material.opacity = 0.52 + Math.sin(elapsed * 3.8 + flare.offset) * 0.18
        }
      }

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
      host.removeEventListener('pointerleave', handlePointerLeave)

      if (host.contains(renderer.domElement)) {
        host.removeChild(renderer.domElement)
      }

      scene.traverse((object) => {
        const geometry = (object as THREE.Mesh).geometry
        if (geometry?.dispose) {
          geometry.dispose()
        }

        const material = (object as THREE.Mesh).material
        if (Array.isArray(material)) {
          for (const entry of material) {
            entry?.dispose?.()
          }
        } else {
          material?.dispose?.()
        }
      })

      renderer.dispose()
    }
  }, [])

  return <div ref={hostRef} className="relative h-full w-full" />
}
