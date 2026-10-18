import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

/**
 * A recognisable, low-poly model for each machine type. `load` (0..1) drives how alive it looks:
 * emissive glow, spinning fans and mixers, a glowing oven door, parcels on a conveyor.
 */
export interface ModelProps {
  shape: string
  size: [number, number, number]
  color: string
  load: number        // 0..1 share of the machine's busiest moment
  running: boolean
  off: boolean
  highlight: boolean
}

const METAL = '#c3cad4'
const DARK = '#7b8594'

function useMaterials(color: string) {
  return useMemo(() => {
    const body = new THREE.MeshStandardMaterial({ color: METAL, metalness: 0.35, roughness: 0.5 })
    const accent = new THREE.MeshStandardMaterial({ color, metalness: 0.3, roughness: 0.4, emissive: new THREE.Color(color), emissiveIntensity: 0 })
    const dark = new THREE.MeshStandardMaterial({ color: DARK, metalness: 0.4, roughness: 0.6 })
    const glow = new THREE.MeshBasicMaterial({ color, toneMapped: false })
    return { body, accent, dark, glow }
  }, [color])
}

export function MachineModel({ shape, size, color, load, running, off, highlight }: ModelProps) {
  const [w, d, h] = size
  const m = useMaterials(color)
  const spin = useRef<THREE.Group>(null)
  const parcels = useRef<THREE.Group>(null)

  useFrame((_, dt) => {
    const target = off ? 0 : 0.05 + 0.35 * load + (highlight ? 0.2 : 0)
    m.accent.emissiveIntensity += (target - m.accent.emissiveIntensity) * Math.min(1, dt * 6)
    m.accent.color.set(off ? '#a7afbb' : color)
    m.glow.color.set(off ? '#b8bfc9' : color)
    if (spin.current && running) spin.current.rotation.y += dt * (2 + 10 * load)
    if (parcels.current && running) {
      parcels.current.children.forEach((child) => {
        child.position.x += dt * (0.4 + load)
        if (child.position.x > w / 2 - 0.2) child.position.x = -w / 2 + 0.2
      })
    }
  })

  const base = <mesh position={[0, 0.04, 0]} material={m.dark}><boxGeometry args={[w + 0.15, 0.08, d + 0.15]} /></mesh>

  switch (shape) {
    case 'press':
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.35, 0]} material={m.body} castShadow><boxGeometry args={[w, h * 0.55, d * 0.8]} /></mesh>
          <mesh position={[0, h * 0.68, 0]} material={m.accent} castShadow><boxGeometry args={[w * 0.92, h * 0.12, d * 0.7]} /></mesh>
          <mesh position={[w * 0.32, h * 0.95, 0]} material={m.body} castShadow><cylinderGeometry args={[d * 0.22, d * 0.12, h * 0.5, 20]} /></mesh>
          <mesh position={[-w * 0.3, h * 0.82, 0]} material={m.dark}><boxGeometry args={[w * 0.25, h * 0.3, d * 0.5]} /></mesh>
        </group>
      )
    case 'tower':
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.45, 0]} material={m.body} castShadow><cylinderGeometry args={[w * 0.42, w * 0.42, h * 0.8, 28]} /></mesh>
          <mesh position={[0, h * 0.62, 0]} material={m.accent}><cylinderGeometry args={[w * 0.44, w * 0.44, h * 0.08, 28]} /></mesh>
          <mesh position={[0, h * 0.95, 0]} material={m.body}><coneGeometry args={[w * 0.42, h * 0.2, 28]} /></mesh>
        </group>
      )
    case 'oven':
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.45, 0]} material={m.body} castShadow><boxGeometry args={[w, h * 0.85, d]} /></mesh>
          <mesh position={[0, h * 0.42, d / 2 + 0.01]} material={m.glow}><planeGeometry args={[w * 0.7, h * 0.18]} /></mesh>
          <mesh position={[0, h * 0.89, 0]} material={m.accent}><boxGeometry args={[w * 1.01, h * 0.06, d * 1.01]} /></mesh>
          <mesh position={[w * 0.32, h * 1.05, -d * 0.2]} material={m.dark}><cylinderGeometry args={[0.18, 0.18, h * 0.5, 16]} /></mesh>
        </group>
      )
    case 'compressor':
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.35, -d * 0.12]} rotation={[0, 0, Math.PI / 2]} material={m.body} castShadow>
            <cylinderGeometry args={[d * 0.32, d * 0.32, w * 0.9, 24]} />
          </mesh>
          <mesh position={[0, h * 0.75, d * 0.18]} material={m.accent} castShadow><boxGeometry args={[w * 0.6, h * 0.5, d * 0.45]} /></mesh>
        </group>
      )
    case 'chiller':
    case 'hvac':
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.45, 0]} material={m.body} castShadow><boxGeometry args={[w, h * 0.85, d]} /></mesh>
          <mesh position={[0, h * 0.89, 0]} material={m.accent}><boxGeometry args={[w * 1.01, 0.05, d * 1.01]} /></mesh>
          <group ref={spin} position={[0, h * 0.93, 0]}>
            {[0, 1, 2, 3].map((i) => (
              <mesh key={i} rotation={[0, (i * Math.PI) / 2, 0]} position={[0, 0, 0]} material={m.dark}>
                <boxGeometry args={[Math.min(w, d) * 0.75, 0.03, 0.12]} />
              </mesh>
            ))}
          </group>
          <mesh position={[0, h * 0.92, 0]} rotation={[-Math.PI / 2, 0, 0]} material={m.dark}>
            <ringGeometry args={[Math.min(w, d) * 0.38, Math.min(w, d) * 0.42, 32]} />
          </mesh>
        </group>
      )
    case 'room':
      return (
        <group>
          {base}
          <mesh position={[0, h / 2, 0]} material={m.body} castShadow><boxGeometry args={[w, h, d]} /></mesh>
          <mesh position={[w * 0.15, h * 0.4, d / 2 + 0.01]} material={m.accent}><planeGeometry args={[w * 0.3, h * 0.75]} /></mesh>
          <mesh position={[-w * 0.3, h * 0.85, d / 2 + 0.01]} material={m.glow}><planeGeometry args={[0.25, 0.12]} /></mesh>
        </group>
      )
    case 'pump':
      return (
        <group>
          {base}
          <mesh position={[-w * 0.15, h * 0.45, 0]} rotation={[0, 0, Math.PI / 2]} material={m.accent} castShadow>
            <cylinderGeometry args={[h * 0.32, h * 0.32, w * 0.55, 20]} />
          </mesh>
          <mesh position={[w * 0.28, h * 0.45, 0]} material={m.body}><sphereGeometry args={[h * 0.36, 20, 16]} /></mesh>
        </group>
      )
    case 'lights':
      return (
        <group>
          <mesh position={[0, 2.9, 0]} material={m.glow}><boxGeometry args={[w * 1.6, 0.05, d * 0.4]} /></mesh>
          <mesh position={[0, 1.5, 0]} material={m.dark}><cylinderGeometry args={[0.02, 0.02, 2.8, 6]} /></mesh>
        </group>
      )
    case 'desk':
      return (
        <group>
          <mesh position={[0, h * 0.7, 0]} material={m.body} castShadow><boxGeometry args={[w, 0.06, d]} /></mesh>
          {[-1, 1].map((s) => (
            <mesh key={s} position={[s * w * 0.42, h * 0.35, 0]} material={m.dark}><boxGeometry args={[0.06, h * 0.7, d * 0.9]} /></mesh>
          ))}
          {[-0.25, 0.25].map((s) => (
            <mesh key={s} position={[s * w, h * 0.7 + 0.28, -d * 0.2]} material={m.glow}><boxGeometry args={[0.55, 0.36, 0.03]} /></mesh>
          ))}
        </group>
      )
    case 'conveyor':
      return (
        <group>
          <mesh position={[0, h * 0.75, 0]} material={m.dark} castShadow><boxGeometry args={[w, 0.08, d]} /></mesh>
          <mesh position={[0, h * 0.8, d / 2]} material={m.accent}><boxGeometry args={[w, 0.06, 0.05]} /></mesh>
          {[-0.42, 0, 0.42].map((s) => (
            <mesh key={s} position={[s * w, h * 0.37, 0]} material={m.body}><boxGeometry args={[0.08, h * 0.75, d * 0.9]} /></mesh>
          ))}
          <group ref={parcels} position={[0, h * 0.95, 0]}>
            {[-0.35, -0.05, 0.25].map((s) => (
              <mesh key={s} position={[s * w, 0, 0]} material={m.body}><boxGeometry args={[0.45, 0.32, d * 0.55]} /></mesh>
            ))}
          </group>
        </group>
      )
    case 'tank':
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.42, 0]} material={m.body} castShadow><cylinderGeometry args={[w * 0.42, w * 0.36, h * 0.75, 28]} /></mesh>
          <mesh position={[0, h * 0.8, 0]} material={m.accent}><cylinderGeometry args={[w * 0.44, w * 0.44, 0.08, 28]} /></mesh>
          <group ref={spin} position={[0, h * 0.95, 0]}>
            <mesh material={m.dark}><boxGeometry args={[w * 0.7, 0.05, 0.1]} /></mesh>
          </group>
          <mesh position={[0, h * 1.02, 0]} material={m.dark}><boxGeometry args={[0.35, 0.3, 0.35]} /></mesh>
        </group>
      )
    default: // cabinet: CNC machines, welders, washers
      return (
        <group>
          {base}
          <mesh position={[0, h * 0.48, 0]} material={m.body} castShadow><boxGeometry args={[w, h * 0.92, d]} /></mesh>
          <mesh position={[-w * 0.15, h * 0.55, d / 2 + 0.01]} material={m.dark}><planeGeometry args={[w * 0.5, h * 0.45]} /></mesh>
          <mesh position={[w * 0.32, h * 0.68, d / 2 + 0.012]} material={m.glow}><planeGeometry args={[w * 0.18, h * 0.16]} /></mesh>
          <mesh position={[0, h * 0.94, 0]} material={m.accent}><boxGeometry args={[w * 1.01, 0.05, d * 1.01]} /></mesh>
        </group>
      )
  }
}
