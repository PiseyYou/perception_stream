import * as THREE from 'three'

// ─── Label color LUT — matches C++ initColorMap() ───
export const LABEL_COLOR: Record<number, [number, number, number]> = {
  0:   [0,         0,         0      ],  // ignore 黑色
  1:   [0,         0,         200/255],  // background 蓝色
  2:   [100/255,   255/255,   102/255],  // grass 绿色
  3:   [118/255,    89/255,   0      ],  // road 褐色
  4:   [255/255,   255/255,   0      ],  // dynamic 黄色
  5:   [255/255,   0,         0      ],  // static_obstacle 红色
  6:   [255/255,   165/255,   0      ],
  7:   [255/255,    20/255,   147/255],
  8:   [0,         255/255,   255/255],
  9:   [245/255,   130/255,    48/255],
  10:  [0,          64/255,   128/255],
  11:  [ 34/255,   139/255,    34/255],
  12:  [255/255,   192/255,   203/255],
  13:  [138/255,    43/255,   226/255],
  100: [255/255,   0,         0      ],  // pole
  101: [255/255,   0,         0      ],  // obst
  102: [255/255,   0,         0      ],  // fixo
  103: [255/255,   0,         255/255],  // car
  104: [255/255,   0,         0      ],  // stat
  105: [255/255,   255/255,   0      ],  // dyna
  106: [0,         255/255,   255/255],  // charge_station
  107: [0,         255/255,   0      ],  // person/small_ball
}
export const PASSABLE = new Set([2, 3])

export function labelColor(label: number): [number, number, number] {
  return LABEL_COLOR[label] ?? [1.0, 0.0, 0.5]
}

// Offline-test panel uses the same reference palette as the C++ point-cloud view.
export const OTP_LABEL_COLOR = LABEL_COLOR
export const OTP_PASSABLE = PASSABLE

// ─── Spherical camera state ───────────────────────────────────
export interface SphState { theta: number; phi: number; radius: number }

export function updateSphCamera(
  camera: THREE.PerspectiveCamera,
  sph: SphState,
  target: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
) {
  const { theta, phi, radius } = sph
  camera.position.set(
    target.x + radius * Math.sin(phi) * Math.sin(theta),
    target.y + radius * Math.cos(phi),
    target.z + radius * Math.sin(phi) * Math.cos(theta),
  )
  camera.lookAt(target)
}

// ─── Generic Three.js canvas setup ───────────────────────────
export function createThreeScene(canvas: HTMLCanvasElement, W = 640, H = 480) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setClearColor(0x1e1e2e)
  renderer.setSize(W, H, false)
  const scene = new THREE.Scene()
  scene.add(new THREE.AxesHelper(1))
  scene.add(new THREE.GridHelper(6, 12, 0x333355, 0x222244))
  const camera = new THREE.PerspectiveCamera(60, W / H, 0.01, 100)
  return { renderer, scene, camera }
}

export function attachOrbitControls(
  canvas: HTMLCanvasElement,
  sph: SphState,
  onUpdate: () => void
): () => void {
  let dragging = false
  let last = { x: 0, y: 0 }
  const onMouseDown = (e: MouseEvent) => { dragging = true; last = { x: e.clientX, y: e.clientY } }
  const onMouseUp = () => { dragging = false }
  const onMouseLeave = () => { dragging = false }
  const onMouseMove = (e: MouseEvent) => {
    if (!dragging) return
    sph.theta -= (e.clientX - last.x) * 0.01
    sph.phi = Math.max(0.1, Math.min(Math.PI - 0.1, sph.phi + (e.clientY - last.y) * 0.01))
    last = { x: e.clientX, y: e.clientY }
    onUpdate()
  }
  const onWheel = (e: WheelEvent) => {
    sph.radius = Math.max(0.5, sph.radius + e.deltaY * 0.005)
    onUpdate()
  }
  canvas.addEventListener('mousedown', onMouseDown)
  canvas.addEventListener('mouseup', onMouseUp)
  canvas.addEventListener('mouseleave', onMouseLeave)
  canvas.addEventListener('mousemove', onMouseMove)
  canvas.addEventListener('wheel', onWheel)
  // 返回 cleanup 函数，供组件卸载时调用
  return () => {
    canvas.removeEventListener('mousedown', onMouseDown)
    canvas.removeEventListener('mouseup', onMouseUp)
    canvas.removeEventListener('mouseleave', onMouseLeave)
    canvas.removeEventListener('mousemove', onMouseMove)
    canvas.removeEventListener('wheel', onWheel)
  }
}

// ─── Parse PCD text → positions + colors ─────────────────────
export function parsePcdAscii(
  text: string,
  colorFn: (label: number) => [number, number, number],
  passableSet: Set<number>,
  coordRemap: 'online' | 'offline' = 'online'
): { pos: Float32Array; col: Float32Array } {
  const lines = text.split('\n')
  let inData = false
  const pos: number[] = [], col: number[] = []
  let skipped = 0
  for (const line of lines) {
    if (line.startsWith('DATA')) { inData = true; continue }
    if (!inData) continue
    const parts = line.trim().split(/\s+/)
    if (parts.length < 5) { skipped++; continue }
    const x = parseFloat(parts[0]), y = parseFloat(parts[1]), z = parseFloat(parts[2])
    const label = parseInt(parts[4])
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) { skipped++; continue }
    if (coordRemap === 'online') {
      pos.push(x, z, -y)
    } else {
      pos.push(x, y, z)
    }
    const [r, g, b] = colorFn(label)
    const dim = passableSet.has(label) ? 0.35 : 1.0
    col.push(r * dim, g * dim, b * dim)
  }
  console.log('[parsePcdAscii] parsed', pos.length / 3, 'points, skipped', skipped, 'lines')
  return { pos: new Float32Array(pos), col: new Float32Array(col) }
}

export function buildPoints(
  pos: Float32Array,
  col: Float32Array,
  pointSize = 0.04,
  existing?: THREE.Points
): THREE.Points {
  // dispose 旧对象，防止 GPU 内存泄漏
  if (existing) {
    existing.geometry.dispose();
    (existing.material as THREE.Material).dispose()
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  geo.computeBoundingSphere()
  return new THREE.Points(geo, new THREE.PointsMaterial({ size: pointSize, vertexColors: true, sizeAttenuation: true }))
}

// dispose 场景中所有 Points 对象的 GPU 资源
export function disposeScenePoints(scene: THREE.Scene) {
  const toRemove: THREE.Points[] = []
  scene.traverse(obj => {
    if (obj instanceof THREE.Points) toRemove.push(obj)
  })
  for (const pts of toRemove) {
    scene.remove(pts)
    pts.geometry.dispose();
    (pts.material as THREE.Material).dispose()
  }
}

// ─── Stereo canvas draw ────────────────────────────────────────
function loadImg(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

export async function drawStereoCanvas(
  canvas: HTMLCanvasElement,
  imgLeft: string | null,
  imgRight: string | null,
  baseUrl = '/api/bag_data/images'
) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  try {
    const [lImg, rImg] = await Promise.all([
      imgLeft  ? loadImg(`${baseUrl}/${imgLeft}`)  : Promise.resolve(null),
      imgRight ? loadImg(`${baseUrl}/${imgRight}`) : Promise.resolve(null),
    ])
    const w = (lImg?.naturalWidth ?? 0) + (rImg?.naturalWidth ?? 0)
    const h = Math.max(lImg?.naturalHeight ?? 0, rImg?.naturalHeight ?? 0)
    canvas.width  = w || 640
    canvas.height = h || 200
    ctx.fillStyle = '#1e1e2e'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    if (lImg) ctx.drawImage(lImg, 0, 0)
    if (rImg) ctx.drawImage(rImg, lImg?.naturalWidth ?? 0, 0)
  } catch (err) {
    console.error('[drawStereoCanvas] Failed to load images:', err, { imgLeft, imgRight, baseUrl })
    ctx.fillStyle = '#1e1e2e'
    ctx.fillRect(0, 0, canvas.width || 640, canvas.height || 200)
  }
}

export async function stitchToBlob(
  imgLeft: string | null,
  imgRight: string | null,
  baseUrl = '/api/bag_data/images'
): Promise<Blob | null> {
  try {
    const [lImg, rImg] = await Promise.all([
      imgLeft  ? loadImg(`${baseUrl}/${imgLeft}`)  : Promise.resolve(null),
      imgRight ? loadImg(`${baseUrl}/${imgRight}`) : Promise.resolve(null),
    ])
    const w = (lImg?.naturalWidth ?? 0) + (rImg?.naturalWidth ?? 0) || 640
    const h = Math.max(lImg?.naturalHeight ?? 0, rImg?.naturalHeight ?? 0) || 200
    const c = document.createElement('canvas')
    c.width = w; c.height = h
    const ctx = c.getContext('2d')!
    ctx.fillStyle = '#1e1e2e'
    ctx.fillRect(0, 0, w, h)
    if (lImg) ctx.drawImage(lImg, 0, 0)
    if (rImg) ctx.drawImage(rImg, lImg?.naturalWidth ?? 0, 0)
    return await new Promise(resolve => c.toBlob(resolve, 'image/jpeg', 0.92))
  } catch { return null }
}
