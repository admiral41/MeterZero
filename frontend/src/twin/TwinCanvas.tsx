import { GizmoHelper, GizmoViewport, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { type ComponentProps, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'

import type { PlantSpec } from '../lib/types'
import { PlantScene } from './PlantScene'

export type View = 'perspective' | 'top' | 'front' | 'side'

export interface CameraCommand {
  view?: View
  focus?: [number, number]   // scene x, z to frame
  id: number                 // change it to run the command again
}

type Props = ComponentProps<typeof PlantScene> & { className?: string; camera?: CameraCommand; gizmo?: boolean }

/**
 * The 3D viewport. Navigates like a game-engine scene view: left-drag orbits, right-drag pans,
 * the wheel zooms, W A S D (and Q E) fly the camera, Shift goes faster. The axis gizmo in the
 * corner snaps to a side when clicked.
 */
export function TwinCanvas({ className, camera, gizmo, ...scene }: Props) {
  const [dragging, setDragging] = useState(false)
  const { floor_w: w, floor_d: d } = scene.spec
  return (
    <div className={className}>
      <Canvas shadows dpr={[1, 2]} camera={{ position: [w * 0.15, Math.max(w, d) * 0.85, d * 1.25], fov: 42, near: 0.1, far: 300 }}
        gl={{ antialias: true }} onPointerMissed={() => scene.onSelect?.(null)}>
        <color attach="background" args={['#eef1f5']} />
        <fog attach="fog" args={['#eef1f5', 60, 130]} />
        <PlantScene {...scene} onDragChange={(v) => { setDragging(v); scene.onDragChange?.(v) }} />
        <OrbitControls makeDefault enabled={!dragging} enableDamping dampingFactor={0.1} maxPolarAngle={Math.PI / 2.05}
          minDistance={3} maxDistance={90} target={[0, 0, 0]} screenSpacePanning={false} />
        <CameraRig spec={scene.spec} command={camera} />
        {gizmo && (
          <GizmoHelper alignment="top-right" margin={[56, 56]}>
            <GizmoViewport axisColors={['#e5484d', '#30a46c', '#3e63dd']} labelColor="white" />
          </GizmoHelper>
        )}
      </Canvas>
    </div>
  )
}

function viewPose(spec: PlantSpec, view: View): { pos: THREE.Vector3; target: THREE.Vector3 } {
  const { floor_w: w, floor_d: d } = spec
  const size = Math.max(w, d)
  const target = new THREE.Vector3(0, 0, 0)
  const pos = {
    perspective: new THREE.Vector3(w * 0.15, size * 0.85, d * 1.25),
    top: new THREE.Vector3(0, size * 1.45, 0.01),
    front: new THREE.Vector3(0, size * 0.32, d * 0.5 + size * 0.95),
    side: new THREE.Vector3(w * 0.5 + size * 0.95, size * 0.32, 0),
  }[view]
  return { pos, target }
}

const FLY_KEYS = new Set(['w', 'a', 's', 'd', 'q', 'e'])

function CameraRig({ spec, command }: { spec: PlantSpec; command?: CameraCommand }) {
  const { camera, controls } = useThree() as unknown as { camera: THREE.PerspectiveCamera; controls: OrbitControlsImpl | null }
  const goal = useRef<{ pos: THREE.Vector3; target: THREE.Vector3 } | null>(null)
  const keys = useRef(new Set<string>())
  const fast = useRef(false)

  useEffect(() => {
    if (!command) return
    if (command.focus) {
      const [x, z] = command.focus
      const target = new THREE.Vector3(x, 0.8, z)
      const offset = camera.position.clone().sub(controls?.target ?? new THREE.Vector3()).setLength(9)
      offset.y = Math.max(offset.y, 4)
      goal.current = { target, pos: target.clone().add(offset) }
    } else if (command.view) {
      goal.current = viewPose(spec, command.view)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [command?.id])

  useEffect(() => {
    const typing = (e: KeyboardEvent) => e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)
    const down = (e: KeyboardEvent) => {
      fast.current = e.shiftKey
      if (typing(e) || e.ctrlKey || e.metaKey) return
      const key = e.key.toLowerCase()
      if (FLY_KEYS.has(key)) keys.current.add(key)
    }
    const up = (e: KeyboardEvent) => {
      fast.current = e.shiftKey
      keys.current.delete(e.key.toLowerCase())
    }
    const clear = () => keys.current.clear()
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', clear)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', clear)
    }
  }, [])

  useFrame((_, dt) => {
    if (!controls) return
    const step = Math.min(dt, 0.05)
    if (goal.current) {
      const t = 1 - Math.exp(-step * 7)
      camera.position.lerp(goal.current.pos, t)
      controls.target.lerp(goal.current.target, t)
      if (camera.position.distanceTo(goal.current.pos) < 0.02) goal.current = null
      controls.update()
    }
    if (keys.current.size) {
      goal.current = null
      const k = keys.current
      const forward = controls.target.clone().sub(camera.position).setY(0)
      if (forward.lengthSq() < 1e-6) forward.set(0, 0, -1)
      forward.normalize()
      const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize()
      const move = new THREE.Vector3()
        .addScaledVector(forward, (k.has('w') ? 1 : 0) - (k.has('s') ? 1 : 0))
        .addScaledVector(right, (k.has('d') ? 1 : 0) - (k.has('a') ? 1 : 0))
        .addScaledVector(camera.up, (k.has('e') ? 1 : 0) - (k.has('q') ? 1 : 0))
      if (move.lengthSq()) {
        move.setLength(Math.max(spec.floor_w, spec.floor_d) * 0.55 * step * (fast.current ? 2.5 : 1))
        camera.position.add(move)
        controls.target.add(move)
        controls.update()
      }
    }
  })
  return null
}
