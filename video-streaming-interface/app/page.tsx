'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

type ConnectionState = 'idle' | 'connecting' | 'live' | 'error'

export default function Page() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const peerRef = useRef<RTCPeerConnection | null>(null)
  const [draftEndpoint, setDraftEndpoint] = useState('http://10.50.1.1:9000/camera/whep')
  const [status, setStatus] = useState<ConnectionState>('idle')
  const [error, setError] = useState('')
  const [muted, setMuted] = useState(true)

  const disconnect = useCallback(() => {
    peerRef.current?.close()
    peerRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const connect = useCallback(async () => {
    disconnect()
    setError('')
    setStatus('connecting')

    try {
      const peer = new RTCPeerConnection()
      peerRef.current = peer
      peer.addTransceiver('video', { direction: 'recvonly' })
      peer.addTransceiver('audio', { direction: 'recvonly' })
      peer.ontrack = (event) => {
        if (videoRef.current && event.streams[0]) videoRef.current.srcObject = event.streams[0]
      }
      peer.onconnectionstatechange = () => {
        if (peer.connectionState === 'connected') setStatus('live')
        if (['failed', 'disconnected', 'closed'].includes(peer.connectionState)) setStatus('error')
      }

      const offer = await peer.createOffer()
      await peer.setLocalDescription(offer)
      await new Promise<void>((resolve) => {
        if (peer.iceGatheringState === 'complete') return resolve()
        peer.onicegatheringstatechange = () => {
          if (peer.iceGatheringState === 'complete') resolve()
        }
      })

      const response = await fetch(draftEndpoint.trim(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp', Accept: 'application/sdp' },
        body: peer.localDescription?.sdp,
      })
      if (!response.ok) throw new Error(`Gateway returned ${response.status}`)
      await peer.setRemoteDescription({ type: 'answer', sdp: await response.text() })
    } catch (connectionError) {
      disconnect()
      setStatus('error')
      setError(connectionError instanceof Error ? connectionError.message : 'Unable to reach the gateway')
    }
  }, [disconnect, draftEndpoint])

  useEffect(() => () => disconnect(), [disconnect])

  const statusLabel = { idle: 'Ready to connect', connecting: 'Connecting to gateway', live: 'Live now', error: 'Connection interrupted' }[status]

  return (
    <main className="stream-app">
      <header className="topbar">
        <div className="brand-lockup"><span className="brand-mark" aria-hidden="true">◉</span><div><p className="eyebrow">FIELD MONITOR</p><h1>Signal View</h1></div></div>
        <div className={`status-pill status-${status}`}><span className="status-dot" />{statusLabel}</div>
      </header>

      <section className="workspace">
        <div className="viewer-column">
          <div className="viewer-frame">
            <video ref={videoRef} autoPlay playsInline muted={muted} aria-label="Live device video stream" />
            {status !== 'live' && <div className="viewer-empty"><span className="empty-glyph" aria-hidden="true">◌</span><h2>{status === 'error' ? 'Stream unavailable' : 'No signal yet'}</h2><p>{status === 'error' ? error : 'Enter a WebRTC gateway endpoint to begin viewing.'}</p></div>}
            <div className="viewer-meta"><span>H.264 / WebRTC</span><span>{status === 'live' ? 'Receiving video' : 'Waiting for source'}</span></div>
          </div>
          <div className="controls"><button className="control-button" onClick={() => setMuted((value) => !value)} aria-label={muted ? 'Unmute stream' : 'Mute stream'}>{muted ? 'UNMUTE' : 'MUTE'}</button><button className="control-button" onClick={() => videoRef.current?.requestFullscreen()} aria-label="Enter fullscreen">FULLSCREEN</button></div>
        </div>

        <aside className="settings-panel"><div><p className="eyebrow">SOURCE CONFIGURATION</p><h2>Connect a device</h2><p className="panel-copy">Your device sends H.264 over UDP to a media gateway. The gateway exposes a WHEP endpoint for browser playback.</p></div><label className="field-label" htmlFor="endpoint">WebRTC gateway endpoint</label><input id="endpoint" value={draftEndpoint} onChange={(event) => setDraftEndpoint(event.target.value)} placeholder="https://gateway.example.com/camera/whep" spellCheck={false} /><button className="connect-button" onClick={connect} disabled={!draftEndpoint.trim() || status === 'connecting'}>{status === 'connecting' ? 'CONNECTING…' : status === 'live' ? 'RECONNECT' : 'CONNECT STREAM'}<span aria-hidden="true">→</span></button><div className="helper"><span className="helper-dot" />WHEP / WebRTC endpoint required</div><div className="technical"><div><span>Transport</span><strong>UDP → WebRTC</strong></div><div><span>Video codec</span><strong>H.264</strong></div><div><span>Audio</span><strong>Optional</strong></div></div></aside>
      </section>
      <footer><span>LOCAL DEVICE MONITORING</span><span>Secure playback via WebRTC</span></footer>
    </main>
  )
}
