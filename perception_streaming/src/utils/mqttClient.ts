import mqtt, {
  type IClientOptions,
  type IClientPublishOptions,
  type MqttClient as IMqttClient
} from 'mqtt'

export type MessageCallback = (topic: string, message: string) => void
type EventType = 'connect' | 'disconnect' | 'reconnect' | 'error' | 'message'
type EventHandler = (...args: any[]) => void

export interface MqttConnectParams {
  brokerUrl: string
  clientId: string
  username: string
  password: string
  keepalive?: number
  clean?: boolean
  reconnectPeriod?: number
}

class MqttClient {
  private client: IMqttClient | null = null
  private brokerURL: string = ''
  private options: IClientOptions = {}
  private connectionFailed = false
  private listeners: Map<EventType, Set<EventHandler>> = new Map()
  // 统一的 topic→callback 路由表，避免多次 subscribe() 累积 message 监听器
  private topicCallbacks: Map<string, MessageCallback> = new Map()

  // ─── Event Emitter ─────────────────────────────────
  on(event: EventType, handler: EventHandler): void {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set())
    this.listeners.get(event)!.add(handler)
  }

  off(event: EventType, handler: EventHandler): void {
    this.listeners.get(event)?.delete(handler)
  }

  private emit(event: EventType, ...args: any[]): void {
    this.listeners.get(event)?.forEach(fn => fn(...args))
  }

  // ─── Lifecycle ─────────────────────────────────────
  init(params: MqttConnectParams): void {
    this.brokerURL = params.brokerUrl
    this.connectionFailed = false
    this.options = {
      clientId: params.clientId,
      username: params.username,
      password: params.password,
      keepalive: params.keepalive ?? 60,
      reconnectPeriod: params.reconnectPeriod ?? 4000,
      clean: params.clean ?? true,
    }
  }

  connect(): 'connect' | 'connected' {
    if (!this.client) {
      this.client = mqtt.connect(this.brokerURL, this.options)

      this.client.on('connect', () => {
        console.log('MQTT Connected')
        this.connectionFailed = false
        this.emit('connect')
      })
      this.client.on('reconnect', () => {
        console.log('MQTT Reconnecting...')
        this.emit('reconnect')
      })
      this.client.on('close', () => {
        console.log('MQTT Connection Closed')
        this.emit('disconnect')
      })
      this.client.on('error', (error) => {
        console.error('MQTT Error:', error)
        if (error.message?.includes('Connection refused: Not authorized')) {
          this.connectionFailed = true
          this.client?.end(true)
          this.client = null
        }
        this.emit('error', error)
      })

      // 单一 message 分发器：按 topic 路由到对应 callback，避免多次 subscribe() 累积监听器
      this.client.on('message', (receivedTopic, message) => {
        const msg = message.toString()
        const cb = this.topicCallbacks.get(receivedTopic)
        if (cb) cb(receivedTopic, msg)
        this.emit('message', receivedTopic, msg)
      })

      return 'connect'
    }
    return 'connected'
  }

  get isConnected(): boolean {
    return !!(this.client && this.client.connected)
  }

  disconnect(): string {
    if (this.client) {
      this.client.end(true, () => {
        this.client = null
        this.connectionFailed = false
        console.log('MQTT Disconnected')
      })
      this.topicCallbacks.clear()
      return 'MQTT Disconnected'
    }
    this.connectionFailed = false
    return 'MQTT Not Connected'
  }

  subscribe(topics: string | string[], callback: MessageCallback): void {
    if (!this.client) return
    const topicList = Array.isArray(topics) ? topics : [topics]

    this.client.subscribe(topicList, (err) => {
      if (!err) console.log(`Subscribed: ${topicList.join(', ')}`)
      else console.error('Subscribe failed:', err)
    })

    // 注册到路由表，不在 client 上重复添加 message 监听器
    for (const topic of topicList) {
      this.topicCallbacks.set(topic, callback)
    }
  }

  publish(topic: string, message: string): string {
    if (!this.client || !this.client.connected) return 'MQTT Not Connected'
    const options: IClientPublishOptions = { qos: 1, retain: false }
    this.client.publish(topic, message, options, (err) => {
      if (err) console.error('Publish failed:', err)
    })
    return 'success'
  }

  destroy(): void {
    if (this.client) {
      this.client.removeAllListeners()
      if (this.client.connected) this.client.end(true)
      this.client = null
    }
    this.listeners.clear()
    this.topicCallbacks.clear()
  }
}

export default MqttClient
