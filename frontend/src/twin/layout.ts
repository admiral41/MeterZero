import * as THREE from 'three'

import type { MachineMeta, PlantSpec } from '../lib/types'

/** Plant coordinates (x across, y deep, in metres) to the 3D scene (x, z), centred on the floor. */
export function toScene(spec: Pick<PlantSpec, 'floor_w' | 'floor_d'>, x: number, y: number, height = 0): THREE.Vector3 {
  return new THREE.Vector3(x - spec.floor_w / 2, height, y - spec.floor_d / 2)
}

function cableY(spec: PlantSpec): number {
  return spec.cable_y ?? spec.floor_d / 2
}

const CABLE_HEIGHT = 0.06

/** Panel → along to the cable tray → along the tray → into the machine. Rounded at the corners. */
export function cableCurve(spec: PlantSpec, machine: Pick<MachineMeta, 'x' | 'y' | 'size'>): THREE.CurvePath<THREE.Vector3> {
  const tray = cableY(spec)
  const edge = machine.y < tray ? machine.y + machine.size[1] / 2 : machine.y - machine.size[1] / 2
  const raw: [number, number][] = [
    [spec.panel_x, spec.panel_y],
    [spec.panel_x, tray],
    [machine.x, tray],
    [machine.x, edge],
  ]
  const points = raw
    .filter((p, i) => i === 0 || Math.hypot(p[0] - raw[i - 1][0], p[1] - raw[i - 1][1]) > 0.01)
    .map(([x, y]) => toScene(spec, x, y, CABLE_HEIGHT))
  const path = new THREE.CurvePath<THREE.Vector3>()
  if (points.length < 2) {
    path.add(new THREE.LineCurve3(points[0], points[0].clone().add(new THREE.Vector3(0.01, 0, 0))))
    return path
  }
  const radius = 0.4
  let start = points[0]
  for (let i = 1; i < points.length; i++) {
    const corner = points[i]
    const next = points[i + 1]
    if (!next) {
      path.add(new THREE.LineCurve3(start, corner))
      break
    }
    const inDir = corner.clone().sub(start).normalize()
    const outDir = next.clone().sub(corner).normalize()
    const r = Math.min(radius, corner.distanceTo(start) / 2, next.distanceTo(corner) / 2)
    const a = corner.clone().sub(inDir.clone().multiplyScalar(r))
    const b = corner.clone().add(outDir.clone().multiplyScalar(r))
    if (a.distanceTo(start) > 0.001) path.add(new THREE.LineCurve3(start, a))
    path.add(new THREE.QuadraticBezierCurve3(a, corner, b))
    start = b
  }
  return path
}
