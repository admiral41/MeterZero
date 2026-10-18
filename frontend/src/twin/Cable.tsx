import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

const MAX_PARTICLES = 40

/**
 * A cable on the floor with electricity flowing along it. Each moving dot is a "packet" of
 * energy: more power means more particles moving faster, so you can see a machine's load at a glance.
 */
export function Cable({ curve, color, power }: {
  curve: THREE.CurvePath<THREE.Vector3>
  color: string
  power: () => number          // 0..1 of the cable's busiest moment, read every frame
}) {
  const particles = useRef<THREE.InstancedMesh>(null)
  const phase = useRef<number | null>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const samples = useMemo(() => curve.getSpacedPoints(240), [curve])
  const tube = useMemo(() => new THREE.TubeGeometry(curve as unknown as THREE.Curve<THREE.Vector3>, 160, 0.035, 6, false), [curve])
  const sheath = useMemo(() => new THREE.MeshStandardMaterial({ color: '#9aa3b0', emissive: new THREE.Color(color), emissiveIntensity: 0, roughness: 0.7 }), [color])
  const spark = useMemo(() => new THREE.MeshBasicMaterial({ color: new THREE.Color(color) }), [color])

  useFrame((_, dt) => {
    const load = Math.max(0, Math.min(1, power()))
    const alive = load > 0.02
    sheath.emissiveIntensity += ((alive ? 0.1 + 0.3 * load : 0) - sheath.emissiveIntensity) * Math.min(1, dt * 5)
    const mesh = particles.current
    if (!mesh) return
    const count = alive ? Math.max(3, Math.round(MAX_PARTICLES * (0.2 + 0.8 * load))) : 0
    phase.current = ((phase.current ?? Math.random()) + dt * (0.08 + 0.45 * load)) % 1
    for (let i = 0; i < MAX_PARTICLES; i++) {
      if (i < count) {
        const t = (phase.current + i / count) % 1
        const point = samples[Math.floor(t * (samples.length - 1))]
        dummy.position.set(point.x, point.y + 0.02, point.z)
        dummy.scale.setScalar(0.75 + 0.6 * load)
      } else {
        dummy.scale.setScalar(0)
      }
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <group>
      <mesh geometry={tube} material={sheath} />
      <instancedMesh ref={particles} args={[undefined, undefined, MAX_PARTICLES]} material={spark} frustumCulled={false}>
        <sphereGeometry args={[0.07, 10, 10]} />
      </instancedMesh>
    </group>
  )
}
