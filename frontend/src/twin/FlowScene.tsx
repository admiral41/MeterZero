import { OrbitControls, Text } from '@react-three/drei'
import { Canvas, type ThreeEvent, useFrame, useThree } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'

export interface FlowData {
  nodes: { name: string; color: string; kind: string }[]
  links: { source: number; target: number; value: number }[]
}

const HEIGHT = 9          // world units for the busiest column
const GAP = 0.22
const COLUMN_X = [-7.2, -0.6, 6.0]
const NODE_W = 0.22
const MAX_DOTS = 2400       // pulse segments drawn at once

interface Placed { name: string; color: string; kind: string; col: number; y0: number; y1: number; value: number }
interface Band { source: number; target: number; value: number; s0: number; s1: number; t0: number; t1: number; color: string }

/** A Sankey laid out in 3D units: nodes stacked in three columns, links as bands between them. */
function layout(data: FlowData) {
  const col = (kind: string) => (kind === 'meter' ? 0 : kind === 'machine' ? 1 : 2)
  const inflow = data.nodes.map(() => 0)
  const outflow = data.nodes.map(() => 0)
  for (const l of data.links) { outflow[l.source] += l.value; inflow[l.target] += l.value }
  const value = data.nodes.map((_, i) => Math.max(inflow[i], outflow[i]))
  const rank = (i: number) => {
    const kind = data.nodes[i].kind
    return kind === 'building' ? -2 : kind === 'waste' ? -1 : 0
  }
  const columns: number[][] = [[], [], []]
  data.nodes.forEach((n, i) => columns[col(n.kind)].push(i))
  columns.forEach((c) => c.sort((a, b) => rank(a) - rank(b) || value[b] - value[a]))
  const tallest = Math.max(...columns.map((c) => c.reduce((s, i) => s + value[i], 0)))
  const gapsMax = Math.max(...columns.map((c) => c.length - 1)) * GAP
  const scale = (HEIGHT - gapsMax) / tallest

  const placed: Placed[] = data.nodes.map((n) => ({ ...n, col: col(n.kind), y0: 0, y1: 0, value: 0 }))
  for (const c of columns) {
    const total = c.reduce((s, i) => s + value[i] * scale, 0) + GAP * (c.length - 1)
    let y = total / 2
    for (const i of c) {
      const h = value[i] * scale
      placed[i] = { ...placed[i], y0: y, y1: y - h, value: value[i] }
      y -= h + GAP
    }
  }

  // Stack each node's links top to bottom in the order of the node at the other end, so bands don't cross needlessly.
  const outOffset = placed.map((p) => p.y0)
  const inOffset = placed.map((p) => p.y0)
  const ordered = [...data.links].sort((a, b) => placed[b.target].y0 - placed[a.target].y0 || placed[b.source].y0 - placed[a.source].y0)
  const bands: Band[] = []
  for (const l of ordered) {
    const h = l.value * scale
    const band: Band = { ...l, s0: outOffset[l.source], s1: outOffset[l.source] - h, t0: 0, t1: 0,
      color: placed[l.target].kind === 'waste' ? '#ef4444' : placed[l.source].kind === 'meter' ? placed[l.target].color : placed[l.source].color }
    outOffset[l.source] -= h
    bands.push(band)
  }
  const byTarget = [...bands].sort((a, b) => placed[b.source].y0 - placed[a.source].y0 || b.s0 - a.s0)
  for (const band of byTarget) {
    const h = band.s0 - band.s1
    band.t0 = inOffset[band.target]
    band.t1 = inOffset[band.target] - h
    inOffset[band.target] -= h
  }
  return { placed, bands }
}

const ease = (t: number) => t * t * (3 - 2 * t)

/** A flat ribbon from one node's right edge to the next node's left edge. */
function ribbonGeometry(x0: number, x1: number, top0: number, bot0: number, top1: number, bot1: number) {
  const steps = 48
  const positions: number[] = []
  const index: number[] = []
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const e = ease(t)
    const x = x0 + (x1 - x0) * t
    positions.push(x, top0 + (top1 - top0) * e, 0, x, bot0 + (bot1 - bot0) * e, 0)
    if (i < steps) {
      const a = i * 2
      index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(index)
  return geometry
}

export function FlowScene({ data, className, unit = 'kWh' }: { data: FlowData; className?: string; unit?: string }) {
  const [hover, setHover] = useState<{ band?: number; node?: number } | null>(null)
  const { placed, bands } = useMemo(() => layout(data), [data])
  const total = useMemo(() => data.links.filter((l) => placed[l.source].kind === 'meter').reduce((s, l) => s + l.value, 0), [data, placed])

  const info = hover?.band !== undefined
    ? `${placed[bands[hover.band].source].name} → ${placed[bands[hover.band].target].name}: ${Math.round(bands[hover.band].value).toLocaleString()} ${unit}`
    : hover?.node !== undefined
      ? `${placed[hover.node].name}: ${Math.round(placed[hover.node].value).toLocaleString()} ${unit} (${Math.round((placed[hover.node].value / total) * 100)}%)`
      : null

  return (
    <div className={className} style={{ position: 'relative' }}>
      <Canvas dpr={[1, 2]} camera={{ fov: 30, position: [0, 0, 30], near: 0.1, far: 200 }} gl={{ antialias: true }}
        onPointerMissed={() => setHover(null)}>
        <color attach="background" args={['#ffffff']} />
        <ambientLight intensity={0.9} />
        <directionalLight position={[4, 6, 10]} intensity={0.6} />
        <Fit />
        <group rotation={[-0.08, 0.12, 0]}>
          {bands.map((b, i) => (
            <Ribbon key={i} band={b} from={placed[b.source]} to={placed[b.target]}
              active={hover === null || hover.band === i || hover.node === b.source || hover.node === b.target}
              onHover={(on) => setHover(on ? { band: i } : null)} />
          ))}
          <Current bands={bands} placed={placed} />
          {placed.map((n, i) => (
            <group key={n.name}>
              <mesh position={[COLUMN_X[n.col], (n.y0 + n.y1) / 2, 0.06]}
                onPointerOver={(e) => { e.stopPropagation(); setHover({ node: i }) }} onPointerOut={() => setHover(null)}>
                <boxGeometry args={[NODE_W, Math.max(n.y0 - n.y1, 0.04), 0.24]} />
                <meshStandardMaterial color={n.color} roughness={0.6} />
              </mesh>
              <Text position={[COLUMN_X[n.col] + NODE_W / 2 + 0.18, (n.y0 + n.y1) / 2, 0.2]} fontSize={0.3} anchorX="left" anchorY="middle"
                color={n.kind === 'waste' ? '#b91c1c' : '#1f2937'} outlineWidth={0.05} outlineColor="#ffffff">
                {n.name}
              </Text>
            </group>
          ))}
        </group>
        <OrbitControls enablePan={false} enableZoom={false} enableDamping rotateSpeed={0.4}
          minAzimuthAngle={-0.6} maxAzimuthAngle={0.6} minPolarAngle={Math.PI / 2 - 0.45} maxPolarAngle={Math.PI / 2 + 0.3} />
      </Canvas>
      <div className="pointer-events-none absolute right-3 top-3 rounded-md border border-line bg-white/95 px-3 py-1.5 text-[12.5px] text-fg-2 shadow-sm">
        {info ?? 'Hover a stream or a machine · drag to tilt'}
      </div>
    </div>
  )
}

/** Keep the whole diagram in view whatever the card's shape. */
function Fit() {
  const { camera, size } = useThree()
  useLayoutEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const width = 18.5
    const height = HEIGHT + 1.2
    const fov = (cam.fov * Math.PI) / 180
    const aspect = size.width / size.height
    const byHeight = height / 2 / Math.tan(fov / 2)
    const byWidth = width / 2 / Math.tan(fov / 2) / aspect
    cam.position.set(0.6, 0, Math.max(byHeight, byWidth) * 1.04)
    cam.lookAt(0.6, 0, 0)
    cam.updateProjectionMatrix()
  }, [camera, size])
  return null
}

function Ribbon({ band, from, to, active, onHover }: { band: Band; from: Placed; to: Placed; active: boolean; onHover: (on: boolean) => void }) {
  const geometry = useMemo(
    () => ribbonGeometry(COLUMN_X[from.col] + NODE_W / 2, COLUMN_X[to.col] - NODE_W / 2, band.s0, band.s1, band.t0, band.t1),
    [band, from.col, to.col],
  )
  const material = useRef<THREE.MeshBasicMaterial>(null)
  useFrame((_, dt) => {
    if (!material.current) return
    const target = active ? (to.kind === 'waste' ? 0.42 : 0.3) : 0.06
    material.current.opacity += (target - material.current.opacity) * Math.min(1, dt * 10)
  })
  return (
    <mesh geometry={geometry}
      onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); onHover(true); document.body.style.cursor = 'pointer' }}
      onPointerOut={() => { onHover(false); document.body.style.cursor = '' }}>
      <meshBasicMaterial ref={material} color={band.color} transparent opacity={0.3} side={THREE.DoubleSide} depthWrite={false} />
    </mesh>
  )
}

/** Where a band's centre line is at t (0 = source, 1 = target), between two lanes. */
function pointOn(b: Band, x0: number, x1: number, t: number, lane: number) {
  const e = ease(t)
  const top = b.s0 + (b.t0 - b.s0) * e
  const bottom = b.s1 + (b.t1 - b.s1) * e
  return { x: x0 + (x1 - x0) * t, y: top + (bottom - top) * lane }
}

const TAIL = 6              // segments per pulse: a bright head fading into its tail
const TAIL_STEP = 0.011     // spacing of tail segments, as a share of the band's length
const SPEED = 0.28          // band lengths per second: fast, like current

/**
 * Current running along every band: a thin conductor line, and bright pulses with fading tails moving
 * in even trains from the meter to each machine and on to each product. Bigger flows carry more pulses.
 */
function Current({ bands, placed }: { bands: Band[]; placed: Placed[] }) {
  const mesh = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const ends = (b: Band) => [COLUMN_X[placed[b.source].col] + NODE_W / 2, COLUMN_X[placed[b.target].col] - NODE_W / 2]

  const pulses = useMemo(() => {
    const total = bands.reduce((s, b) => s + b.value, 0)
    const list: { band: number; phase: number; lane: number; width: number }[] = []
    bands.forEach((b, i) => {
      const thickness = b.s0 - b.s1
      const lanes = thickness > 0.5 ? [0.3, 0.7] : [0.5]
      const perLane = Math.max(1, Math.min(6, Math.round((b.value / total) * 60)))
      lanes.forEach((lane, l) => {
        for (let k = 0; k < perLane; k++) {
          list.push({ band: i, lane, phase: (k + l / lanes.length) / perLane, width: Math.min(0.06, Math.max(0.03, thickness * 0.2)) })
        }
      })
    })
    return list.slice(0, Math.floor(MAX_DOTS / TAIL))
  }, [bands])

  // Head segments in a strong shade of the band's colour, the tail fading towards the pale band.
  useLayoutEffect(() => {
    if (!mesh.current) return
    const strong = new THREE.Color()
    const pale = new THREE.Color()
    pulses.forEach((p, i) => {
      strong.set(bands[p.band].color).multiplyScalar(0.62)
      pale.set(bands[p.band].color).lerp(new THREE.Color('#ffffff'), 0.55)
      for (let j = 0; j < TAIL; j++) mesh.current!.setColorAt(i * TAIL + j, strong.clone().lerp(pale, j / TAIL))
    })
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true
  }, [pulses, bands])

  useFrame(({ clock }) => {
    if (!mesh.current) return
    const time = clock.elapsedTime
    pulses.forEach((p, i) => {
      const b = bands[p.band]
      const [x0, x1] = ends(b)
      const head = (p.phase + time * SPEED) % 1
      for (let j = 0; j < TAIL; j++) {
        const t = head - j * TAIL_STEP
        const index = i * TAIL + j
        if (t < 0) {
          dummy.scale.setScalar(0)
        } else {
          const here = pointOn(b, x0, x1, t, p.lane)
          const ahead = pointOn(b, x0, x1, Math.min(1, t + 0.004), p.lane)
          dummy.position.set(here.x, here.y, 0.05 + j * 0.0005)
          dummy.rotation.set(0, 0, Math.atan2(ahead.y - here.y, ahead.x - here.x))
          dummy.scale.set(0.42 * (1 - j / (TAIL * 1.6)), p.width * (1 - j / (TAIL * 2)), 1)
        }
        dummy.updateMatrix()
        mesh.current!.setMatrixAt(index, dummy.matrix)
      }
    })
    mesh.current.instanceMatrix.needsUpdate = true
  })

  return (
    <>
      {bands.map((b, i) => <Conductor key={i} band={b} ends={ends(b)} />)}
      <instancedMesh ref={mesh} args={[undefined, undefined, pulses.length * TAIL]} frustumCulled={false}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial />
      </instancedMesh>
    </>
  )
}

/** The thin wire through the middle of a band, so the flow reads as a circuit. */
function Conductor({ band, ends: [x0, x1] }: { band: Band; ends: number[] }) {
  const line = useMemo(() => {
    const points = Array.from({ length: 40 }, (_, k) => {
      const p = pointOn(band, x0, x1, k / 39, 0.5)
      return new THREE.Vector3(p.x, p.y, 0.03)
    })
    const color = new THREE.Color(band.color).multiplyScalar(0.75)
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.45 }))
  }, [band, x0, x1])
  return <primitive object={line} />
}
