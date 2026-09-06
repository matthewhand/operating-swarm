/**
 * REQ-194 — lazy WebGL pose-player (ADR-008 §2).
 *
 * This module is ONLY ever loaded through a dynamic `import()` from
 * Robot3DAvatar when the `robot3d` theme is active, so `three` is
 * code-split out of the main chat graph. Chat never waits on GL:
 * if WebGL is unavailable the component falls back to the static SVG robot
 * before this module loads.
 *
 * The robot is a **procedural, original stylised robot** built from
 * primitives (MIT, see LICENSE/NOTICE) — deliberately NOT the licensed
 * Reachy mesh. Playback is baked MiniPose sequences, not AnimationMixer.
 */

import * as THREE from 'three'
import { resolveRobot3dRig } from './catalog'
import { ROBOT3D_CLIPS } from './clips'
import { sampleClip } from './poseMath'
import type { MiniPose, Robot3dClipId, Robot3dCombo } from './types'

export class Robot3dUnavailableError extends Error {
  constructor(message = 'WebGL is not available for the 3D robot theme') {
    super(message)
    this.name = 'Robot3dUnavailableError'
  }
}

export interface Robot3dPlayer {
  play(clipId: Robot3dClipId): void
  pause(): void
  resume(): void
  dispose(): void
}

const CLIP_SEQUENCE: Robot3dClipId[] = ['idle', 'listen', 'working', 'dance', 'error']

interface Robot3dPlayerOptions {
  canvas: HTMLCanvasElement
  combo?: Robot3dCombo
  /** Motion intensity scale (0 = static). */
  amplitude?: number
}

export function createRobot3dPlayer({
  canvas,
  combo,
  amplitude = 1,
}: Robot3dPlayerOptions): Robot3dPlayer {
  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
  } catch {
    throw new Robot3dUnavailableError()
  }

  const rig = resolveRobot3dRig(combo)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 20)
  camera.position.set(0, 0.72, 1.55)
  camera.lookAt(0, 0.55, 0)

  scene.add(new THREE.AmbientLight(0xffffff, 0.75))
  const key = new THREE.DirectionalLight(0xffffff, 1.1)
  key.position.set(0.8, 1.4, 1.2)
  scene.add(key)

  const { robot, headGroup, antennaLeft, antennaRight } = buildRobot(rig.headAttachment.offset)

  const attachQuat = new THREE.Quaternion(
    rig.headAttachment.quaternion.x,
    rig.headAttachment.quaternion.y,
    rig.headAttachment.quaternion.z,
    rig.headAttachment.quaternion.w,
  )
  headGroup.quaternion.copy(attachQuat)

  scene.add(robot)

  let current: Robot3dClipId = 'idle'
  let t = 0
  let last = performance.now()
  let raf = 0
  let disposed = false
  const poseQuat = new THREE.Quaternion()

  const applyPose = (pose: MiniPose) => {
    robot.rotation.y = pose.body_yaw * amplitude
    headGroup.position.set(
      rig.headAttachment.offset.x + pose.head.pos.x,
      rig.headAttachment.offset.y + pose.head.pos.y,
      rig.headAttachment.offset.z + pose.head.pos.z,
    )
    headGroup.quaternion.copy(attachQuat)
    poseQuat.set(pose.head.quat.x, pose.head.quat.y, pose.head.quat.z, pose.head.quat.w)
    headGroup.quaternion.premultiply(poseQuat)
    antennaLeft.rotation.z = pose.antennas.left * amplitude
    antennaRight.rotation.z = -pose.antennas.right * amplitude
  }

  const frame = (now: number) => {
    if (disposed) return
    const dt = Math.min((now - last) / 1000, 0.1)
    last = now
    t += dt
    const clip = ROBOT3D_CLIPS[current]
    applyPose(sampleClip(clip, t))
    const width = canvas.clientWidth || 96
    const height = canvas.clientHeight || 96
    if (canvas.width !== width || canvas.height !== height) {
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    renderer.render(scene, camera)
    raf = requestAnimationFrame(frame)
  }

  const play = (clipId: Robot3dClipId) => {
    if (disposed) return
    const next = CLIP_SEQUENCE.includes(clipId) ? clipId : 'idle'
    if (next !== current) {
      current = next
      t = 0
    }
  }

  const start = () => {
    last = performance.now()
    raf = requestAnimationFrame(frame)
  }

  const pause = () => {
    cancelAnimationFrame(raf)
  }

  const onVisibility = () => {
    if (document.hidden) {
      pause()
    } else if (!disposed) {
      start()
    }
  }

  document.addEventListener('visibilitychange', onVisibility)
  start()

  return {
    play,
    pause,
    resume: start,
    dispose: () => {
      disposed = true
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVisibility)
      renderer.dispose()
    },
  }
}

/** Procedural original robot: pedestal + torso + head group + antenna stalks. */
function buildRobot(headOffset: { x: number; y: number; z: number }) {
  const robot = new THREE.Group()

  const slate = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.55, metalness: 0.4 })
  const indigo = new THREE.MeshStandardMaterial({ color: 0x818cf8, roughness: 0.5, metalness: 0.3 })
  const dark = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.4, metalness: 0.5 })
  const glow = new THREE.MeshStandardMaterial({
    color: 0x34d399,
    emissive: 0x34d399,
    emissiveIntensity: 0.9,
  })

  // Pedestal base
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.17, 0.06, 24), slate)
  base.position.y = 0.03
  robot.add(base)

  // Body column
  const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.11, 0.34, 24), indigo)
  torso.position.y = 0.23
  robot.add(torso)

  const shoulder = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.05, 24), dark)
  shoulder.position.y = 0.4
  robot.add(shoulder)

  // Chest light (status glow handled by clip amplitude in later phases)
  const chest = new THREE.Mesh(new THREE.SphereGeometry(0.02, 12, 12), glow)
  chest.position.y = 0.2
  chest.position.z = 0.095
  robot.add(chest)

  // Head group attaches at the published socket
  const headGroup = new THREE.Group()
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.11, 0.15), slate)
  head.position.set(headOffset.x, headOffset.y, headOffset.z)
  headGroup.add(head)

  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.045, 0.02), dark)
  visor.position.set(headOffset.x, headOffset.y - 0.012, headOffset.z + 0.076)
  headGroup.add(visor)

  const visorGlow = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.03, 0.012), glow)
  visorGlow.position.set(headOffset.x, headOffset.y - 0.012, headOffset.z + 0.082)
  headGroup.add(visorGlow)

  // Antennas on the head — rotated by MiniPose antennas.left/right
  const antennaLeft = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.1, 8), slate)
  antennaLeft.position.set(headOffset.x - 0.05, headOffset.y + 0.075, headOffset.z)
  headGroup.add(antennaLeft)
  const antennaRight = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.1, 8), slate)
  antennaRight.position.set(headOffset.x + 0.05, headOffset.y + 0.075, headOffset.z)
  headGroup.add(antennaRight)

  robot.add(headGroup)
  robot.position.y = 0.02

  return { robot, headGroup, antennaLeft, antennaRight }
}