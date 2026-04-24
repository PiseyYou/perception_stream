import AgoraRTC, { type IAgoraRTCClient } from 'agora-rtc-sdk-ng'
import { ref } from 'vue'

const VIDEO_CONTAINER_ID = 'video-container'

let agoraClient: IAgoraRTCClient | null = null
let joined = false
const remoteMap = new Map<number | string, any>()

const isConnected = ref(false)
const connectionState = ref<string>('DISCONNECTED')

// ─── Event Handlers ──────────────────────────────────

async function handleUserPublished(user: any, mediaType: 'audio' | 'video') {
    if (!joined) return
    await doSubscribe(user, mediaType)
}

function handleUserUnpublished(user: any) {
    console.log('Remote user unpublished:', user.uid)
    cleanupRemote(user.uid)
}

async function doSubscribe(user: any, mediaType: 'audio' | 'video') {
    if (!agoraClient) return
    const uid = user.uid
    await agoraClient.subscribe(user, mediaType)

    const rec = remoteMap.get(uid) || { user, containerId: VIDEO_CONTAINER_ID }

    if (mediaType === 'video') {
        user.videoTrack.play(rec.containerId)
        rec.videoTrack = user.videoTrack
    }
    if (mediaType === 'audio') {
        user.audioTrack.play()
        rec.audioTrack = user.audioTrack
    }
    remoteMap.set(uid, rec)
}

function cleanupRemote(uid: number | string) {
    const rec = remoteMap.get(uid)
    if (!rec) return
    try { rec.videoTrack?.stop() } catch { /* ignore */ }
    try { rec.audioTrack?.stop() } catch { /* ignore */ }
    remoteMap.delete(uid)
}

// ─── Public API ──────────────────────────────────────

export async function joinChannel(appid: string, channel: string) {
    if (agoraClient) {
        console.warn('Agora already connected')
        return
    }

    agoraClient = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' })
    agoraClient.on('user-published', handleUserPublished)
    agoraClient.on('user-unpublished', handleUserUnpublished)
    agoraClient.on('connection-state-change', (cur, prev) => {
        console.log(`[Agora] ${prev} => ${cur}`)
        connectionState.value = cur
    })

    await agoraClient.join(appid, channel, null, null)
    joined = true
    isConnected.value = true
    console.log(`Joined Agora channel: ${channel}`)
}

export async function leaveChannel() {
    if (!agoraClient) return
    try {
        joined = false

        for (const [uid, rec] of remoteMap) {
            try {
                if (rec.videoTrack) {
                    rec.videoTrack.stop()
                    await agoraClient.unsubscribe(rec.user, 'video').catch(() => { })
                }
                if (rec.audioTrack) {
                    rec.audioTrack.stop()
                    await agoraClient.unsubscribe(rec.user, 'audio').catch(() => { })
                }
            } catch (e) {
                console.warn('cleanup error:', uid, e)
            }
        }
        remoteMap.clear()

        agoraClient.removeAllListeners()

        await agoraClient.leave()
        agoraClient = null
        isConnected.value = false
        connectionState.value = 'DISCONNECTED'
        console.log('Left Agora channel')
    } catch (e) {
        console.error('leaveChannel error:', e)
    }
}

export function useAgoraRTC() {
    return {
        isConnected,
        connectionState,
        joinChannel,
        leaveChannel,
    }
}
