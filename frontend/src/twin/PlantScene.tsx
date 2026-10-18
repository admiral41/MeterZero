import { Grid, Html, Text } from '@react-three/drei'
import { type ThreeEvent, useFrame } from '@react-three/fiber'
import { type MutableRefObject, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'

import type { MachineMeta, PlantSpec, Timeline } from '../lib/types'
import { Cable } from './Cable'
import { cableCurve, toScene } from './layout'
import { MachineModel } from './MachineModel'

export interface LiveSource {
  timeline: Timeline
  minute: MutableRefObject<number>    // fractional minute of the day, advanced by the player
}

interface SceneProps {
  spec: PlantSpec
  machines: MachineMeta[]
  live?: LiveSource
  labels?: boolean
  showHidden?: boolean
  selected?: string | null
  onSelect?: (id: string | null) => void
  // designer mode
  editable?: boolean
  placing?: boolean
  onFloorClick?: (x: number, y: number) => void
  onMove?: (id: string, x: number, y: number) => void
  onDragChange?: (dragging: boolean) => void
}

const OFF_KW = 0.6

function valueAt(series: number[] | undefined, minute: number) {
  if (!series || !series.length) return 0
  return series[Math.max(0, Math.min(series.length - 1, Math.floor(minute)))] ?? 0
}

/** Re-render the HTML parts (labels, states) a few times a second; the 3D parts animate every frame. */
function useTick(live: LiveSource | undefined, hz = 6) {
  const [, setTick] = useState(0)
  const last = useRef(-1)
  const timer = useRef(0)
  useFrame((_, dt) => {
    if (!live) return
    timer.current += dt
    const minute = Math.floor(live.minute.current)
    if (timer.current > 1 / hz && minute !== last.current) {
      timer.current = 0
      last.current = minute
      setTick((t) => t + 1)
    }
  })
  return live ? Math.floor(live.minute.current) : 0
}

export function PlantScene(props: SceneProps) {
  const { spec, machines, live, labels = true, showHidden, selected, onSelect, editable, placing } = props
  const minute = useTick(live)
  const [hovered, setHovered] = useState<string | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  const lightsOn = live ? valueAt(live.timeline.lights, minute) > 0 : true
  const hour = minute / 60
  const daylight = live ? Math.max(0, Math.sin(((hour - 6) / 14) * Math.PI)) : 1

  const curves = useMemo(
    () => Object.fromEntries(machines.map((m) => [m.id, cableCurve(spec, m)])),
    [spec, machines],
  )
  const alerts = live?.timeline.alerts ?? []

  const floorPoint = (e: ThreeEvent<PointerEvent | MouseEvent>) => {
    const p = e.point
    return { x: Math.round((p.x + spec.floor_w / 2) * 2) / 2, y: Math.round((p.z + spec.floor_d / 2) * 2) / 2 }
  }

  const center = toScene(spec, spec.floor_w / 2, spec.floor_d / 2)
  const panel = toScene(spec, spec.panel_x, spec.panel_y)
  const siteKw = live ? valueAt(live.timeline.meter, minute) : 0

  return (
    <>
      {/* Light: brighter by day, dim at night, room lights when people are on site */}
      <ambientLight intensity={0.55 + 0.25 * daylight} />
      <hemisphereLight args={['#ffffff', '#cfd6e0', 0.45 + 0.3 * daylight]} />
      <directionalLight position={[12, 22, 10]} intensity={0.6 + 0.8 * daylight} castShadow shadow-mapSize={[1024, 1024]}
        shadow-camera-left={-20} shadow-camera-right={20} shadow-camera-top={20} shadow-camera-bottom={-20} />

      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow
        onPointerMove={(e) => {
          if (dragging && props.onMove) {
            const { x, y } = floorPoint(e)
            props.onMove(dragging, Math.max(0.5, Math.min(spec.floor_w - 0.5, x)), Math.max(0.5, Math.min(spec.floor_d - 0.5, y)))
          }
        }}
        onPointerUp={() => { if (dragging) { setDragging(null); props.onDragChange?.(false) } }}
        onClick={(e) => {
          if (placing && props.onFloorClick) {
            e.stopPropagation()
            const { x, y } = floorPoint(e)
            props.onFloorClick(x, y)
          } else if (!dragging) onSelect?.(null)
        }}>
        <planeGeometry args={[spec.floor_w + 40, spec.floor_d + 40]} />
        <meshStandardMaterial color="#e6eaf0" roughness={0.95} />
      </mesh>
      <Grid position={[center.x, 0.001, center.z]} args={[spec.floor_w + 40, spec.floor_d + 40]} cellSize={1} cellThickness={0.5}
        cellColor="#d5dbe4" sectionSize={5} sectionThickness={1} sectionColor="#bfc8d4" fadeDistance={70} infiniteGrid={false} />

      {/* Rooms */}
      {spec.rooms.map((room, i) => {
        const c = toScene(spec, room.x + room.w / 2, room.y + room.d / 2)
        return (
          <group key={room.id}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[c.x, 0.012, c.z]} receiveShadow>
              <planeGeometry args={[room.w - 0.08, room.d - 0.08]} />
              <meshStandardMaterial color={lightsOn ? (i % 2 ? '#fdf8ec' : '#fbf5e6') : i % 2 ? '#f4f6f9' : '#f1f3f7'} roughness={0.9} />
            </mesh>
            <lineSegments position={[c.x, 0.02, c.z]}>
              <edgesGeometry args={[new THREE.BoxGeometry(room.w, 0.001, room.d)]} />
              <lineBasicMaterial color="#9aa6b6" />
            </lineSegments>
            {/* low back walls for depth */}
            <mesh position={[c.x, 0.3, c.z - room.d / 2]}>
              <boxGeometry args={[room.w, 0.6, 0.06]} />
              <meshStandardMaterial color="#d9dee6" />
            </mesh>
            <mesh position={[c.x - room.w / 2, 0.3, c.z]}>
              <boxGeometry args={[0.06, 0.6, room.d]} />
              <meshStandardMaterial color="#d9dee6" />
            </mesh>
            <Text position={[c.x - room.w / 2 + 0.35, 0.03, c.z + room.d / 2 - 0.45]} rotation={[-Math.PI / 2, 0, 0]}
              fontSize={0.42} color="#6b7280" anchorX="left" anchorY="middle" letterSpacing={0.08}>
              {room.name.toUpperCase()}
            </Text>
            {lightsOn && live && (
              <pointLight position={[c.x, 3.2, c.z]} intensity={1.2} distance={Math.max(room.w, room.d) * 1.1} color="#ffd9a0" decay={1.6} />
            )}
          </group>
        )
      })}

      {/* Main meter / distribution panel */}
      <group position={[panel.x, 0, panel.z]}>
        <mesh position={[0, 1.15, 0]} castShadow>
          <boxGeometry args={[1.2, 2.3, 0.7]} />
          <meshStandardMaterial color="#cfd5de" metalness={0.3} roughness={0.5} />
        </mesh>
        <mesh position={[0, 1.6, 0.36]}>
          <planeGeometry args={[0.8, 0.45]} />
          <meshBasicMaterial color="#2563eb" toneMapped={false} />
        </mesh>
        <mesh position={[0, 2.32, 0]}>
          <boxGeometry args={[1.22, 0.04, 0.72]} />
          <meshBasicMaterial color="#2563eb" toneMapped={false} />
        </mesh>
        <Html position={[0, 2.9, 0]} center distanceFactor={14} zIndexRange={[20, 0]}>
          <div className="pointer-events-none whitespace-nowrap rounded-lg border border-line bg-white px-2.5 py-1.5 text-center shadow-sm">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-brand">Main meter</div>
            {live && <div className="num text-[17px] font-semibold text-fg">{siteKw.toFixed(0)} kW</div>}
          </div>
        </Html>
      </group>

      {/* Cables with energy flowing to each machine */}
      {machines.map((m) => (
        <Cable key={`cable-${m.id}`} curve={curves[m.id]} color={m.color}
          power={() => (live ? valueAt(live.timeline.machines[m.id]?.kw, live.minute.current) / Math.max(m.peak_kw, 1) : 0.35)} />
      ))}

      {/* Machines */}
      {machines.map((m) => {
        const series = live?.timeline.machines[m.id]
        const kw = valueAt(series?.kw, minute)
        const state = live ? valueAt(series?.state, minute) : 2
        const off = live ? kw < OFF_KW : false
        const alert = alerts.find((a) => a.machine === m.id && minute >= a.from && minute < a.to)
        const pos = toScene(spec, m.x, m.y)
        const isSelected = selected === m.id
        const isHovered = hovered === m.id
        return (
          <group key={m.id} position={[pos.x, 0, pos.z]} rotation={[0, (m.rotation * Math.PI) / 180, 0]}
            onPointerOver={(e) => { e.stopPropagation(); setHovered(m.id); document.body.style.cursor = editable ? 'grab' : 'pointer' }}
            onPointerOut={() => { setHovered(null); document.body.style.cursor = '' }}
            onPointerDown={(e) => {
              if (!editable) return
              e.stopPropagation()
              setDragging(m.id)
              props.onDragChange?.(true)
              onSelect?.(m.id)
            }}
            onClick={(e) => { e.stopPropagation(); onSelect?.(m.id) }}>
            <MachineModel shape={m.shape} size={m.size} color={m.color} load={Math.min(kw / Math.max(m.peak_kw, 1), 1)}
              running={!off && state === 2} off={off} highlight={isHovered || isSelected} />
            {/* status ring */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
              <ringGeometry args={[Math.max(m.size[0], m.size[1]) * 0.62, Math.max(m.size[0], m.size[1]) * 0.62 + 0.08, 48]} />
              <meshBasicMaterial color={alert ? '#ef4444' : isSelected ? '#2563eb' : state === 2 ? m.color : state === 1 ? '#d97706' : '#9ca3af'}
                transparent opacity={isSelected || alert ? 1 : 0.55} toneMapped={!alert} />
            </mesh>
            {alert && <AlertBeacon radius={Math.max(m.size[0], m.size[1]) * 0.75} />}
            {(labels || isHovered || isSelected) && (
              <Html position={[0, m.size[2] + 0.75, 0]} center distanceFactor={14} zIndexRange={[10, 0]}>
                <div className={`pointer-events-none whitespace-nowrap rounded-md border px-2 py-1 text-center ${
                  alert ? 'border-red-300 bg-red-50' : isSelected ? 'border-brand-line bg-white/95' : 'border-line bg-white/95'} shadow-sm`}>
                  <div className="text-[11px] font-medium text-fg-2">{m.name}</div>
                  {live && (
                    <div className={`num text-[13px] font-semibold ${alert ? 'text-red-700' : off ? 'text-fg-3' : 'text-fg'}`}>
                      {alert ? `${alert.observed_kw.toFixed(1)} kW at night` : `${kw.toFixed(1)} kW`}
                      {showHidden && !alert && <span className="ml-1 text-[10px] font-normal text-amber-700">meter {valueAt(series?.hidden, minute).toFixed(1)}</span>}
                    </div>
                  )}
                </div>
              </Html>
            )}
          </group>
        )
      })}
    </>
  )
}

function AlertBeacon({ radius }: { radius: number }) {
  const ring = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (!ring.current) return
    const t = (clock.elapsedTime % 1.4) / 1.4
    ring.current.scale.setScalar(1 + t * 0.8)
    ;(ring.current.material as THREE.MeshBasicMaterial).opacity = 0.9 * (1 - t)
  })
  return (
    <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
      <ringGeometry args={[radius, radius + 0.12, 48]} />
      <meshBasicMaterial color="#dc2626" transparent />
    </mesh>
  )
}
