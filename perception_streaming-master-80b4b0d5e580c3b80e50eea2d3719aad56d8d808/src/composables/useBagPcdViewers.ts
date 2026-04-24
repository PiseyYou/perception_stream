import * as THREE from 'three'
import {
  PASSABLE, labelColor, OTP_LABEL_COLOR, OTP_PASSABLE,
  createThreeScene, attachOrbitControls, updateSphCamera,
  parsePcdAscii, buildPoints,
  type SphState,
} from './usePcdRenderer'

function otpLabelColor(label: number): [number, number, number] {
  return OTP_LABEL_COLOR[label] ?? [1.0, 0.0, 0.5]
}

// ─── Online PCD viewer ───────────────────────────────────────
export function createOnlinePcdViewer() {
  let renderer: THREE.WebGLRenderer | null = null
  let scene: THREE.Scene | null = null
  let camera: THREE.PerspectiveCamera | null = null
  let points: THREE.Points | null = null
  let animId = 0
  let orbitCleanup: (() => void) | null = null
  const sph: SphState = { theta: 0.5, phi: 1.0, radius: 5 }

  function init(canvas: HTMLCanvasElement) {
    const r = createThreeScene(canvas)
    renderer = r.renderer; scene = r.scene; camera = r.camera
    updateSphCamera(camera, sph)
    orbitCleanup = attachOrbitControls(canvas, sph, () => updateSphCamera(camera!, sph))
    const loop = () => { animId = requestAnimationFrame(loop); renderer?.render(scene!, camera!) }
    loop()
  }

  async function loadPcd(fname: string) {
    if (!scene || !camera) return
    try {
      // Try /api/bag_data/pcds/ first (for pre-processed bags)
      let res = await fetch(`/api/bag_data/pcds/${fname}`)

      // If 404, try /offline/local_file with relative path (for extracted bags)
      if (!res.ok && res.status === 404) {
        console.log(`[onlinePcd] Trying /offline/local_file for: ${fname}`)
        res = await fetch(`/offline/local_file?path=${encodeURIComponent(fname)}`)
      }

      if (!res.ok) {
        console.error(`[onlinePcd] Failed to fetch PCD: ${res.status} ${res.statusText}`, fname)
        return
      }
      const { pos, col } = parsePcdAscii(await res.text(), labelColor, PASSABLE, 'online')
      if (points) scene.remove(points)
      points = buildPoints(pos, col, 0.04, points ?? undefined)
      scene.add(points)
      const n = pos.length / 3
      if (n > 0) {
        let cx = 0, cy = 0, cz = 0
        for (let i = 0; i < n; i++) { cx += pos[i*3]; cy += pos[i*3+1]; cz += pos[i*3+2] }
        const target = new THREE.Vector3(cx/n, cy/n, cz/n)
        updateSphCamera(camera, sph, target)
      }
    } catch (err) {
      console.error('[onlinePcd] Error loading PCD:', err, fname)
    }
  }

  function isReady() { return !!renderer }

  function dispose() {
    cancelAnimationFrame(animId)
    orbitCleanup?.()
    if (points) { points.geometry.dispose(); (points.material as THREE.Material).dispose() }
    renderer?.dispose()
    renderer = null; scene = null; camera = null; points = null
  }

  return { init, loadPcd, isReady, dispose }
}

// ─── Offline DSG PCD viewer ──────────────────────────────────
export function createOfflinePcdViewer() {
  let renderer: THREE.WebGLRenderer | null = null
  let scene: THREE.Scene | null = null
  let camera: THREE.PerspectiveCamera | null = null
  let points: THREE.Points | null = null
  let animId = 0
  let orbitCleanup: (() => void) | null = null
  const sph: SphState = { theta: 0.5, phi: 1.0, radius: 5 }
  const target = new THREE.Vector3(0, 0.2, 0.6)
  let statusMsg = ''

  function init(canvas: HTMLCanvasElement) {
    const r = createThreeScene(canvas)
    renderer = r.renderer; scene = r.scene; camera = r.camera
    updateSphCamera(camera, sph, target)
    orbitCleanup = attachOrbitControls(canvas, sph, () => updateSphCamera(camera!, sph, target))
    statusMsg = '已初始化'
    const loop = () => { animId = requestAnimationFrame(loop); renderer?.render(scene!, camera!) }
    loop()
  }

  async function loadPcd(fname: string): Promise<string> {
    if (!scene) return '❌scene null'
    statusMsg = '加载中...'
    try {
      // Try /api/bag_data/offline_pcds/ first (for pre-processed bags)
      let res = await fetch(`/api/bag_data/offline_pcds/${fname}`)

      // If 404, try /offline/local_file with relative path (for extracted bags)
      if (!res.ok && res.status === 404) {
        console.log(`[offlinePcd] Trying /offline/local_file for: ${fname}`)
        res = await fetch(`/offline/local_file?path=${encodeURIComponent(fname)}`)
      }

      if (!res.ok) {
        const msg = `❌HTTP ${res.status}`
        console.error(`[offlinePcd] Failed to fetch PCD: ${res.status} ${res.statusText}`, fname)
        statusMsg = msg
        return msg
      }
      const { pos, col } = parsePcdAscii(await res.text(), labelColor, PASSABLE, 'offline')
      if (points) scene.remove(points)
      points = buildPoints(pos, col, 0.04, points ?? undefined)
      scene.add(points)
      const n = pos.length / 3
      if (n > 0) {
        let cx = 0, cy = 0, cz = 0
        for (let i = 0; i < n; i++) { cx += pos[i*3]; cy += pos[i*3+1]; cz += pos[i*3+2] }
        target.set(cx/n, cy/n, cz/n)
        updateSphCamera(camera!, sph, target)
      }
      statusMsg = `✓ ${n}pts`
      return statusMsg
    } catch (err) {
      const msg = '❌加载失败'
      console.error('[offlinePcd] Error loading PCD:', err, fname)
      statusMsg = msg
      return msg
    }
  }

  function isReady() { return !!renderer }
  function getStatus() { return statusMsg }

  function dispose() {
    cancelAnimationFrame(animId)
    orbitCleanup?.()
    if (points) { points.geometry.dispose(); (points.material as THREE.Material).dispose() }
    renderer?.dispose()
    renderer = null; scene = null; camera = null; points = null
  }

  return { init, loadPcd, isReady, getStatus, dispose }
}

// ─── Offline result PCD viewer ───────────────────────────────
export function createOfflineResultPcdViewer() {
  let renderer: THREE.WebGLRenderer | null = null
  let scene: THREE.Scene | null = null
  let camera: THREE.PerspectiveCamera | null = null
  let points: THREE.Points | null = null
  let animId = 0
  let orbitCleanup: (() => void) | null = null
  const sph: SphState = { theta: 0.5, phi: 1.0, radius: 5 }

  function init(canvas: HTMLCanvasElement) {
    if (renderer) return
    const r = createThreeScene(canvas)
    renderer = r.renderer; scene = r.scene; camera = r.camera
    updateSphCamera(camera, sph)
    orbitCleanup = attachOrbitControls(canvas, sph, () => updateSphCamera(camera!, sph))
    const loop = () => { animId = requestAnimationFrame(loop); renderer?.render(scene!, camera!) }
    loop()
  }

  async function loadPcd(stem: string) {
    if (!scene) return
    try {
      const res = await fetch(`/offline/result_pcd/${stem}`)
      if (!res.ok) {
        console.error(`[offlineResultPcd] Failed to fetch PCD: ${res.status} ${res.statusText}`, stem)
        return
      }
      const { pos, col } = parsePcdAscii(await res.text(), otpLabelColor, OTP_PASSABLE, 'online')
      if (points) scene.remove(points)
      points = buildPoints(pos, col, 0.04, points ?? undefined)
      scene.add(points)
    } catch (err) {
      console.error('[offlineResultPcd] Error loading PCD:', err, stem)
    }
  }

  function isReady() { return !!renderer }

  function dispose() {
    cancelAnimationFrame(animId)
    orbitCleanup?.()
    if (points) { points.geometry.dispose(); (points.material as THREE.Material).dispose() }
    renderer?.dispose()
    renderer = null; scene = null; camera = null; points = null
  }

  return { init, loadPcd, isReady, dispose }
}
