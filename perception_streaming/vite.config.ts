import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { spawn, execSync, execFileSync, type ChildProcess } from 'child_process'
import { fileURLToPath } from 'url'
import path from 'path'
import fs from 'fs'
import os from 'os'
import { isIP } from 'net'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const VENV_PYTHON = path.resolve(__dirname, '.venv/bin/python')
const PYTHON = process.env.PYTHON || (fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python3')
const SSH_KEY = path.resolve(__dirname, 'data/conf/bestmow_rsa_202606')
const REMOTE_HOST = '120.25.121.3'
const REMOTE_PORT = '10015'
const LOCAL_PCL_PORT = 8768   // SSH tunnel local end (pcl_proxy.mjs connects here)
const REMOTE_PCL_PORT = 8767  // pcl_ws_bridge.py port

const SSH_BASE = ['-i', SSH_KEY, `root@${REMOTE_HOST}`, '-p', REMOTE_PORT, '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5']
const DEV_SERVER_HOST = process.env.VITE_DEV_SERVER_HOST || '192.168.55.247'
const DEV_CERT_DIR = path.resolve(__dirname, '.cert')
const DEV_CERT_KEY = path.join(DEV_CERT_DIR, 'localhost-key.pem')
const DEV_CERT_CERT = path.join(DEV_CERT_DIR, 'localhost-cert.pem')
const DEV_CERT_SAN = path.join(DEV_CERT_DIR, 'subject-alt-name.txt')

function getDevCertificateSubjectAltName() {
  const hosts = new Set([DEV_SERVER_HOST, 'localhost', '127.0.0.1', '::1'])
  for (const iface of Object.values(os.networkInterfaces())) {
    for (const addr of iface ?? []) {
      if (addr.family === 'IPv4' && !addr.internal) hosts.add(addr.address)
    }
  }
  return [...hosts].map((host) => isIP(host) ? `IP:${host}` : `DNS:${host}`).join(',')
}

function ensureDevCertificate() {
  const san = getDevCertificateSubjectAltName()
  const shouldCreate = !fs.existsSync(DEV_CERT_KEY)
    || !fs.existsSync(DEV_CERT_CERT)
    || !fs.existsSync(DEV_CERT_SAN)
    || fs.readFileSync(DEV_CERT_SAN, 'utf8') !== san

  if (shouldCreate) {
    fs.mkdirSync(DEV_CERT_DIR, { recursive: true })
    execFileSync('openssl', [
      'req',
      '-x509',
      '-newkey',
      'rsa:2048',
      '-sha256',
      '-nodes',
      '-days',
      '3650',
      '-keyout',
      DEV_CERT_KEY,
      '-out',
      DEV_CERT_CERT,
      '-subj',
      '/CN=localhost',
      '-addext',
      `subjectAltName=${san}`,
    ], { stdio: 'ignore' })
    fs.writeFileSync(DEV_CERT_SAN, san)
  }

  return {
    key: fs.readFileSync(DEV_CERT_KEY),
    cert: fs.readFileSync(DEV_CERT_CERT),
  }
}

function killPort(port: number) {
  try { execSync(`fuser -k ${port}/tcp`, { stdio: 'ignore' }) } catch { /* ignore */ }
}

function stripViteClientScript(html: string) {
  return html.replace(/\s*<script type="module" src="\/@vite\/client"><\/script>\s*/g, '\n')
}

function disableViteLiveReloadPlugin() {
  return {
    name: 'disable-vite-live-reload',
    apply: 'serve' as const,
    configureServer(server: import('vite').ViteDevServer) {
      server.middlewares.use(async (req, res, next) => {
        const pathname = (req.url || '/').split('?')[0]
        const accept = req.headers.accept || ''
        const wantsHtml = accept.includes('text/html') || accept.includes('*/*')
        if (req.method !== 'GET' || !wantsHtml || (pathname !== '/' && pathname !== '/index.html')) {
          next()
          return
        }

        try {
          const rawHtml = fs.readFileSync(path.resolve(__dirname, 'index.html'), 'utf8')
          const transformedHtml = await server.transformIndexHtml(req.url || '/', rawHtml)
          const html = stripViteClientScript(transformedHtml)
          res.statusCode = 200
          res.setHeader('Content-Type', 'text/html')
          res.end(html)
        } catch (error) {
          next(error)
        }
      })
    },
  }
}

function offlineServerPlugin() {
  let proc: ChildProcess | null = null
  let restartTimer: ReturnType<typeof setTimeout> | null = null
  let restartDelayMs = 1000
  let shuttingDown = false

  function scheduleRestart(start: () => void) {
    if (restartTimer || shuttingDown) return
    const delay = restartDelayMs
    restartTimer = setTimeout(() => {
      restartTimer = null
      start()
    }, delay)
    restartDelayMs = Math.min(restartDelayMs * 2, 30000)
    console.log(`[offline] restarting in ${delay}ms`)
  }

  return {
    name: 'offline-server',
    configureServer() {
      killPort(8769)
      const script = path.resolve(__dirname, 'robot_monitor/offline_server.py')
      const start = () => {
        if (proc || shuttingDown) return
        const startedAt = Date.now()
        proc = spawn(PYTHON, [script], { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, BAG_DATA_DIR } })
        proc.stdout?.on('data', (d) => process.stdout.write(`[offline] ${d}`))
        proc.stderr?.on('data', (d) => process.stderr.write(`[offline] ${d}`))
        proc.on('error', (error) => {
          console.error(`[offline] failed to start: ${error.message}`)
          proc = null
          scheduleRestart(start)
        })
        proc.on('exit', (code, signal) => {
          console.log(`[offline] exited ${code ?? signal}`)
          proc = null
          if (Date.now() - startedAt > 10000) restartDelayMs = 1000
          scheduleRestart(start)
        })
      }
      const stop = () => {
        shuttingDown = true
        if (restartTimer) clearTimeout(restartTimer)
        proc?.kill()
        proc = null
      }
      start()
      process.once('exit', stop)
      process.once('SIGINT', () => { stop(); process.exit() })
    },
  }
}

function sshBridgePlugin() {
  let bridge: ChildProcess | null = null
  let bridgeRestartTimer: ReturnType<typeof setTimeout> | null = null
  let bridgeRestartDelayMs = 1000
  let pclTunnel: ChildProcess | null = null
  let pclProxy: ChildProcess | null = null
  let cleanupRegistered = false
  let shuttingDown = false

  function scheduleBridgeRestart(start: () => void) {
    if (bridgeRestartTimer || shuttingDown) return
    const delay = bridgeRestartDelayMs
    bridgeRestartTimer = setTimeout(() => {
      bridgeRestartTimer = null
      start()
    }, delay)
    bridgeRestartDelayMs = Math.min(bridgeRestartDelayMs * 2, 30000)
    console.log(`[bridge] restarting in ${delay}ms`)
  }

  return {
    name: 'ssh-bridge',
    configureServer() {
      // ── 1. ssh_bridge.py (log streaming) ──
      killPort(8765)
      const script = path.resolve(__dirname, 'robot_monitor/ssh_bridge.py')
      const startBridge = () => {
        if (bridge || shuttingDown) return
        const startedAt = Date.now()
        bridge = spawn(PYTHON, [script], { stdio: ['ignore', 'pipe', 'pipe'] })
        bridge.stdout?.on('data', (d) => process.stdout.write(`[bridge] ${d}`))
        bridge.stderr?.on('data', (d) => process.stderr.write(`[bridge] ${d}`))
        bridge.on('error', (error) => {
          console.error(`[bridge] failed to start: ${error.message}`)
          bridge = null
          scheduleBridgeRestart(startBridge)
        })
        bridge.on('exit', (code, signal) => {
          console.log(`[bridge] exited ${code ?? signal}`)
          bridge = null
          if (Date.now() - startedAt > 10000) bridgeRestartDelayMs = 1000
          scheduleBridgeRestart(startBridge)
        })
      }
      startBridge()

      // ── 2. Deploy & start pcl_ws_bridge.py on robot (async, non-blocking) ──
      const pclScript = path.resolve(__dirname, 'robot_monitor/pcl_ws_bridge.py')
      setTimeout(() => {
        const scpProc = spawn('scp', [
          '-i', SSH_KEY, '-P', String(REMOTE_PORT),
          '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5',
          pclScript, `root@${REMOTE_HOST}:/tmp/pcl_ws_bridge.py`
        ], { stdio: 'ignore' })
        scpProc.on('close', (code) => {
          if (code !== 0) { console.warn('[pcl-bridge] scp failed'); return }
          const killProc = spawn('ssh', [
            ...SSH_BASE, '-o', 'ConnectTimeout=5',
            `kill $(fuser ${REMOTE_PCL_PORT}/tcp 2>/dev/null) 2>/dev/null; true`
          ], { stdio: 'ignore' })
          killProc.on('close', () => {
            const startCmd = `export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp FASTRTPS_DEFAULT_PROFILES_FILE=/opt/ros/fastdds.xml ROS_LOG_DIR=/userdata/log_dir/ros2_log && source /opt/ros/humble/setup.bash && source /app/BestMow/install/setup.bash && setsid python3 /tmp/pcl_ws_bridge.py >/tmp/pcl_bridge.log 2>&1 &`
            const startProc = spawn('ssh', [...SSH_BASE, '-o', 'ConnectTimeout=5', startCmd], { stdio: 'ignore' })
            startProc.on('close', (c) => {
              if (c === 0) console.log('[pcl-bridge] deployed and started on robot')
              else console.warn('[pcl-bridge] start failed')
            })
          })
        })
      }, 0)

      // ── 3. SSH tunnel: localhost:8768 → robot:8767 ──
      killPort(LOCAL_PCL_PORT)

      let tunnelFails = 0
      const MAX_TUNNEL_FAILS = 3
      function startPclTunnel() {
        pclTunnel = spawn('ssh', [
          ...SSH_BASE,
          '-o', 'ConnectTimeout=5',
          '-o', 'ServerAliveInterval=10',
          '-o', 'ServerAliveCountMax=3',
          '-N',
          '-L', `${LOCAL_PCL_PORT}:localhost:${REMOTE_PCL_PORT}`,
        ], { stdio: ['ignore', 'ignore', 'ignore'] })
        pclTunnel.on('exit', () => {
          tunnelFails++
          if (tunnelFails >= MAX_TUNNEL_FAILS) {
            console.warn(`[pcl-tunnel] 连接失败 ${tunnelFails} 次，已停止自动重连。如需点云功能，请确认机器在线后重启。`)
            return
          }
          setTimeout(startPclTunnel, 5000)
        })
        console.log(`[pcl-tunnel] localhost:${LOCAL_PCL_PORT} → robot:${REMOTE_PCL_PORT}`)
      }
      startPclTunnel()

      // ── 4. PCL proxy: browser:8766 → tunnel:8768 ──
      killPort(8766)
      const pclProxyScript = path.resolve(__dirname, 'robot_monitor/pcl_proxy.mjs')
      pclProxy = spawn(process.execPath, [pclProxyScript], { stdio: ['ignore', 'pipe', 'pipe'] })
      pclProxy.stdout?.on('data', (d) => process.stdout.write(`[pcl-proxy] ${d}`))
      pclProxy.stderr?.on('data', (d) => process.stderr.write(`[pcl-proxy] ${d}`))
      pclProxy.on('exit', (code) => console.log(`[pcl-proxy] exited ${code}`))

      const stop = () => {
        shuttingDown = true
        if (bridgeRestartTimer) clearTimeout(bridgeRestartTimer)
        bridge?.kill()
        pclTunnel?.kill()
        pclProxy?.kill()
      }

      if (!cleanupRegistered) {
        cleanupRegistered = true
        process.on('exit', stop)
        process.on('SIGINT', () => { stop(); process.exit() })
      }
    },
  }
}

// ── Bag file server plugin ──────────────────────────
// Serves local .db3/.mcap bag files from BAG_DIR via:
//   GET /api/bags          → JSON list of {name, size, mtime}
//   GET /api/bags/:file    → raw file download (for drag-free loading)
const BAG_DIR = process.env.BAG_DIR ?? path.resolve(__dirname, 'bags')

function bagFilePlugin() {
  return {
    name: 'bag-file-server',
    configureServer(server: import('vite').ViteDevServer) {
      server.middlewares.use('/api/bags', (req, res) => {
        const url = req.url ?? '/'
        // List endpoint
        if (url === '/' || url === '') {
          if (!fs.existsSync(BAG_DIR)) {
            res.writeHead(200, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify([]))
            return
          }
          const files = fs.readdirSync(BAG_DIR)
            .filter(f => f.endsWith('.db3') || f.endsWith('.mcap') || f.endsWith('.bag'))
            .map(f => {
              const stat = fs.statSync(path.join(BAG_DIR, f))
              return { name: f, size: stat.size, mtime: stat.mtimeMs }
            })
            .sort((a, b) => b.mtime - a.mtime)
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify(files))
          return
        }
        // File download endpoint: /api/bags/filename.db3
        const fileName = decodeURIComponent(url.replace(/^\//, ''))
        const filePath = path.join(BAG_DIR, path.basename(fileName))
        if (!fs.existsSync(filePath)) {
          res.writeHead(404)
          res.end('Not found')
          return
        }
        const stat = fs.statSync(filePath)
        res.writeHead(200, {
          'Content-Type': 'application/octet-stream',
          'Content-Length': stat.size,
          'Content-Disposition': `attachment; filename="${path.basename(filePath)}"`,
        })
        fs.createReadStream(filePath).pipe(res)
      })
    },
  }
}

// ── Bag offline data plugin ─────────────────────────
// Serves extracted rosbag images/PCDs from BAG_DATA_DIR via:
//   GET /api/bag_data/images/:file   → JPEG image
//   GET /api/bag_data/images/dsg/:file → DSG JPEG
//   GET /api/bag_data/pcds/:file     → PCD text file
const BAG_DATA_DIR = process.env.BAG_DATA_DIR ?? path.resolve(__dirname, 'data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059')

function bagDataPlugin() {
  return {
    name: 'bag-data-server',
    configureServer(server: import('vite').ViteDevServer) {
      server.middlewares.use('/api/bag_data', (req, res) => {
        const url = decodeURIComponent(req.url ?? '/')
        let filePath: string | null = null
        let contentType = 'application/octet-stream'

        if (url.startsWith('/images/dsg/')) {
          const fname = path.basename(url)
          // For DSG images, try multiple possible locations
          const possiblePaths = [
            path.join(BAG_DATA_DIR, 'images', 'dsg_7_205_0319_nighttime_432', fname),
            path.join(BAG_DATA_DIR, 'bag_extract_camera', 'images', 'dsg_7_205_0319_nighttime_432', fname)
          ]
          for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
              filePath = p
              break
            }
          }
          contentType = 'image/jpeg'
        } else if (url.startsWith('/images/')) {
          const fname = path.basename(url)
          // For camera bags: bag_extract_camera/bag_extract_stereo/
          // For pre-processed bags: images/
          const possiblePaths = [
            path.join(BAG_DATA_DIR, 'bag_extract_camera', 'bag_extract_stereo', fname),
            path.join(BAG_DATA_DIR, 'images', fname)
          ]
          for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
              filePath = p
              break
            }
          }
          contentType = 'image/jpeg'
        } else if (url.startsWith('/pcds/')) {
          const fname = path.basename(url)
          // For camera bags: bag_extract_camera/bag_extract_pcd/
          // For pre-processed bags: pointclouds/
          const possiblePaths = [
            path.join(BAG_DATA_DIR, 'bag_extract_camera', 'bag_extract_pcd', fname),
            path.join(BAG_DATA_DIR, 'pointclouds', fname)
          ]
          for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
              filePath = p
              break
            }
          }
          contentType = 'text/plain'
        } else if (url.startsWith('/offline_pcds/')) {
          const fname = path.basename(url)
          const possiblePaths = [
            path.join(BAG_DATA_DIR, 'bag_extract_camera', 'offline_pointclouds', fname),
            path.join(BAG_DATA_DIR, 'offline_pointclouds', fname)
          ]
          for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
              filePath = p
              break
            }
          }
          contentType = 'text/plain'
        } else if (url === '/manifest.json') {
          // manifest.json is in the bag root directory
          filePath = path.join(BAG_DATA_DIR, 'manifest.json')
          contentType = 'application/json'
        }

        if (!filePath || !fs.existsSync(filePath)) {
          res.writeHead(404); res.end('Not found'); return
        }
        const stat = fs.statSync(filePath)
        res.writeHead(200, { 'Content-Type': contentType, 'Content-Length': stat.size })
        fs.createReadStream(filePath).pipe(res)
      })
    },
  }
}

export default defineConfig(({ command }) => ({
  plugins: [disableViteLiveReloadPlugin(), vue(), offlineServerPlugin(), sshBridgePlugin(), bagFilePlugin(), bagDataPlugin()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    https: command === 'serve' ? ensureDevCertificate() : undefined,
    open: `https://${DEV_SERVER_HOST}:5173/`,
    strictPort: true,
    watch: {
      ignored: [
        '**/data/**',
        '**/node_modules/**',
        '**/.git/**',
        '**/.venv/**',
        '**/build/**',
        '**/cmake-build-*/**',
        '**/CMakeFiles/**',
        '**/lib/**',
        '**/include/**',
        '**/dist/**',
        '**/vite.config.ts.timestamp-*.mjs',
      ],
      usePolling: true,
      interval: 1000,
    },
    hmr: false,
    proxy: {
      '/bridge-ws': {
        target: 'ws://localhost:8765',
        ws: true,
        changeOrigin: true,
      },
      '/pcl-ws': {
        target: 'ws://localhost:8766',
        ws: true,
        changeOrigin: true,
      },
      '/offline': {
        target: 'http://localhost:8769',
        changeOrigin: true,
        timeout: 300000, // 5 minutes timeout for long operations
        proxyTimeout: 300000,
      },
      '/ros2deploy': {
        target: 'http://localhost:8769',
        changeOrigin: true,
      },
      '/api/extract': {
        target: 'http://localhost:8769',
        changeOrigin: true,
      },
    },
  },
}))
