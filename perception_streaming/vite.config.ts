import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { spawn, execSync, type ChildProcess } from 'child_process'
import { fileURLToPath } from 'url'
import path from 'path'
import fs from 'fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Use environment variable or fallback to system python3
const PYTHON = process.env.PYTHON || 'python3'
const FRONTEND_PORT = Number(process.env.PERCEPTION_STREAMING_PORT || '5173')
const OFFLINE_SERVER_PORT = Number(process.env.OFFLINE_SERVER_PORT || '8769')
const ENABLE_ROBOT_BRIDGE = process.env.ENABLE_ROBOT_BRIDGE !== '0'
// Use SSH key from project data/conf directory
const SSH_KEY = path.resolve(__dirname, 'data/conf/bestmow_rsa_202604')
const REMOTE_HOST = '120.25.121.3'
const REMOTE_PORT = '10015'
const LOCAL_PCL_PORT = 8768   // SSH tunnel local end (pcl_proxy.mjs connects here)
const REMOTE_PCL_PORT = 8767  // pcl_ws_bridge.py port

const SSH_BASE = ['-i', SSH_KEY, `root@${REMOTE_HOST}`, '-p', REMOTE_PORT, '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5']

function offlineServerPlugin() {
  let proc: ChildProcess | null = null
  return {
    name: 'offline-server',
    configureServer() {
      try { execSync(`lsof -ti:${OFFLINE_SERVER_PORT} | xargs kill -9`, { stdio: 'ignore' }) } catch { /* ignore */ }
      const script = path.resolve(__dirname, 'robot_monitor/offline_server.py')
      proc = spawn(PYTHON, [script], { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, BAG_DATA_DIR } })
      proc.stdout?.on('data', (d) => process.stdout.write(`[offline] ${d}`))
      proc.stderr?.on('data', (d) => process.stderr.write(`[offline] ${d}`))
      proc.on('exit', (code) => console.log(`[offline] exited ${code}`))
      process.on('exit', () => proc?.kill())
      process.on('SIGINT', () => { proc?.kill(); process.exit() })
    },
  }
}

function sshBridgePlugin() {
  let bridge: ChildProcess | null = null
  let pclTunnel: ChildProcess | null = null
  let pclProxy: ChildProcess | null = null
  let cleanupRegistered = false

  return {
    name: 'ssh-bridge',
    configureServer() {
      // ── 1. ssh_bridge.py (log streaming) ──
      try { execSync('lsof -ti:8765 | xargs kill -9', { stdio: 'ignore' }) } catch { /* ignore */ }
      const script = path.resolve(__dirname, 'robot_monitor/ssh_bridge.py')
      bridge = spawn(PYTHON, [script], { stdio: ['ignore', 'pipe', 'pipe'] })
      bridge.stdout?.on('data', (d) => process.stdout.write(`[bridge] ${d}`))
      bridge.stderr?.on('data', (d) => process.stderr.write(`[bridge] ${d}`))
      bridge.on('exit', (code) => console.log(`[bridge] exited ${code}`))

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
      try { execSync(`lsof -ti:${LOCAL_PCL_PORT} | xargs kill -9`, { stdio: 'ignore' }) } catch { /* ignore */ }

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
        pclTunnel.on('exit', (code) => {
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
      try { execSync('lsof -ti:8766 | xargs kill -9', { stdio: 'ignore' }) } catch { /* ignore */ }
      const pclProxyScript = path.resolve(__dirname, 'robot_monitor/pcl_proxy.mjs')
      pclProxy = spawn(process.execPath, [pclProxyScript], { stdio: ['ignore', 'pipe', 'pipe'] })
      pclProxy.stdout?.on('data', (d) => process.stdout.write(`[pcl-proxy] ${d}`))
      pclProxy.stderr?.on('data', (d) => process.stderr.write(`[pcl-proxy] ${d}`))
      pclProxy.on('exit', (code) => console.log(`[pcl-proxy] exited ${code}`))

      if (!cleanupRegistered) {
        cleanupRegistered = true
        process.on('exit', () => { bridge?.kill(); pclTunnel?.kill(); pclProxy?.kill() })
        process.on('SIGINT', () => { bridge?.kill(); pclTunnel?.kill(); pclProxy?.kill(); process.exit() })
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
      server.middlewares.use('/api/bags', (req, res, next) => {
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
      server.middlewares.use('/api/bag_data', (req, res, next) => {
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

export default defineConfig({
  plugins: [vue(), offlineServerPlugin(), ...(ENABLE_ROBOT_BRIDGE ? [sshBridgePlugin()] : []), bagFilePlugin(), bagDataPlugin()],
  server: {
    host: '0.0.0.0',
    port: FRONTEND_PORT,
    open: true,
    watch: {
      ignored: ['**/data/**', '**/node_modules/**', '**/.git/**'],
      usePolling: false,
    },
    hmr: {
      overlay: false,
    },
    proxy: {
      '/offline': {
        target: `http://localhost:${OFFLINE_SERVER_PORT}`,
        changeOrigin: true,
        timeout: 300000, // 5 minutes timeout for long operations
        proxyTimeout: 300000,
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            // Enable streaming for SSE
            if (req.url?.includes('/analyze_avoiding')) {
              proxyReq.setHeader('Connection', 'keep-alive');
            }
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // Disable buffering for SSE responses
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              res.writeHead(proxyRes.statusCode || 200, proxyRes.headers);
              proxyRes.pipe(res);
            }
          });
        },
      },
      '/prelabel': {
        target: `http://localhost:${OFFLINE_SERVER_PORT}`,
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
      '/ros2deploy': {
        target: `http://localhost:${OFFLINE_SERVER_PORT}`,
        changeOrigin: true,
      },
      '/api/extract': {
        target: `http://localhost:${OFFLINE_SERVER_PORT}`,
        changeOrigin: true,
      },
    },
  },
})
