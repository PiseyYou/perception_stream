import type { IAgoraRTCClient } from 'agora-rtc-sdk-ng'
import { ref } from 'vue'

const VIDEO_CONTAINER_ID = 'video-container'

let agoraClient: IAgoraRTCClient | null = null
let joined = false
const remoteMap = new Map<number | string, any>()

const isConnected = ref(false)
const connectionState = ref<string>('DISCONNECTED')
const remoteUserCount = ref(0)

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
    console.log(`[Agora] subscribed ${mediaType}:`, uid)

    const rec = remoteMap.get(uid) || { user, containerId: VIDEO_CONTAINER_ID }

    if (mediaType === 'video' && user.videoTrack) {
        user.videoTrack.play(rec.containerId)
        rec.videoTrack = user.videoTrack
    }
    if (mediaType === 'audio' && user.audioTrack) {
        user.audioTrack.play()
        rec.audioTrack = user.audioTrack
    }
    remoteMap.set(uid, rec)
    remoteUserCount.value = remoteMap.size
}

async function subscribeExistingRemoteUsers() {
    if (!agoraClient) return
    for (const user of agoraClient.remoteUsers) {
        if (user.hasVideo) await doSubscribe(user, 'video')
        if (user.hasAudio) await doSubscribe(user, 'audio')
    }
}

function cleanupRemote(uid: number | string) {
    const rec = remoteMap.get(uid)
    if (!rec) return
    try { rec.videoTrack?.stop() } catch { /* ignore */ }
    try { rec.audioTrack?.stop() } catch { /* ignore */ }
    remoteMap.delete(uid)
    remoteUserCount.value = remoteMap.size
}

// ─── Public API ──────────────────────────────────────

export async function joinChannel(appid: string, channel: string) {
    if (agoraClient) {
        console.warn('Agora already connected')
        return
    }

    const { default: AgoraRTC } = await import('agora-rtc-sdk-ng')
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
    await subscribeExistingRemoteUsers()
    console.log(`Joined Agora channel: ${channel}, remote users: ${agoraClient.remoteUsers.length}`)
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
        remoteUserCount.value = 0

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
        remoteUserCount,
        joinChannel,
        leaveChannel,
    }
}
