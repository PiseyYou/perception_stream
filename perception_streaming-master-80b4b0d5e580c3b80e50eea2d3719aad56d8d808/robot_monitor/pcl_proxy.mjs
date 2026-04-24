#!/usr/bin/env node
/**
 * PCL WebSocket Proxy
 * 本地始终监听 8766，转发到 SSH 隧道 8768（隧道目标端口）
 * 隧道断开时保持监听，重连后自动恢复
 */
import { WebSocketServer, WebSocket } from 'ws'
import net from 'net'

const LISTEN_PORT = 8766   // 浏览器连这里
const TUNNEL_PORT = 8768   // SSH 隧道转发到这里（remote:8767）

const wss = new WebSocketServer({ port: LISTEN_PORT })
console.log(`[pcl_proxy] listening on ws://localhost:${LISTEN_PORT}`)

const MAX_RETRIES = 5
const RETRY_INTERVAL_MS = 3000

wss.on('connection', (clientWs) => {
  console.log('[pcl_proxy] browser connected')

  let upstream = null
  let closed = false
  let retries = 0

  function connectUpstream() {
    if (closed) return
    upstream = new WebSocket(`ws://localhost:${TUNNEL_PORT}`)
    upstream.binaryType = 'arraybuffer'

    upstream.on('open', () => {
      retries = 0
      console.log('[pcl_proxy] upstream connected')
    })

    upstream.on('message', (data) => {
      if (clientWs.readyState === WebSocket.OPEN) {
        clientWs.send(data, { binary: true })
      }
    })

    upstream.on('close', () => {
      if (closed) return
      retries++
      if (retries <= MAX_RETRIES) {
        setTimeout(connectUpstream, RETRY_INTERVAL_MS)
      } else {
        console.log(`[pcl_proxy] upstream unreachable after ${MAX_RETRIES} retries — tunnel may be down. Reconnect browser to retry.`)
        clientWs.close(1013, 'upstream unreachable')
      }
    })

    upstream.on('error', () => {
      upstream.terminate()
    })
  }

  connectUpstream()

  clientWs.on('close', () => {
    closed = true
    upstream?.terminate()
    console.log('[pcl_proxy] browser disconnected')
  })

  clientWs.on('error', () => {
    closed = true
    upstream?.terminate()
  })
})
