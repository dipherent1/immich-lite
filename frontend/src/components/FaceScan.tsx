"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, getMe, scanFace } from "@/lib/api";

const POSES = [
  { id: "front", label: "Front", text: "Face the camera" },
  { id: "left", label: "Left", text: "Turn head slightly left" },
  { id: "right", label: "Right", text: "Turn head slightly right" },
];

interface Capture {
  file: File;
  preview: string;
}

/**
 * Enroll the current user's face profile. Minimal flow (legacy-style):
 *   1. Dashboard shows one button ("Scan face") — camera stays OFF until clicked.
 *   2. Clicking it turns the camera on (mirrored preview).
 *   3. User taps "Capture" 3 times — guided Front → Left → Right.
 *   4. All 3 photos are uploaded, the vector is stored, and we show success.
 */
export default function FaceScan() {
  const [hasProfile, setHasProfile] = useState<boolean | null>(null);
  const [camOn, setCamOn] = useState(false);
  const [captures, setCaptures] = useState<Capture[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    getMe()
      .then((u) => setHasProfile(u.has_face_profile))
      .catch(() => setHasProfile(false));
  }, []);

  // Stop the camera when the component unmounts.
  useEffect(() => {
    return () => streamRef.current?.getTracks().forEach((t) => t.stop());
  }, []);

  // Attach the live stream to the <video> once it's mounted (camOn must be
  // true for the video element to exist).
  useEffect(() => {
    if (camOn && streamRef.current && videoRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [camOn]);

  async function startCamera() {
    console.log("[FaceScan] startCamera clicked");
    setError(null);
    setDone(false);
    setCaptures([]);
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: 640, height: 480 },
        audio: false,
      });
      console.log("[FaceScan] camera stream acquired", s.getVideoTracks().length, "video track(s)");
      streamRef.current = s;
      setCamOn(true);
    } catch (err) {
      console.error("[FaceScan] getUserMedia failed", err);
      setError("Could not access your camera. Allow camera access and try again.");
    }
  }

  function stopCamera() {
    console.log("[FaceScan] stopCamera");
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamOn(false);
  }

  async function submit(files: File[]) {
    console.log(`[FaceScan] submit ${files.length} image(s)`);
    setBusy(true);
    setError(null);
    try {
      const res = await scanFace(files);
      console.log("[FaceScan] scanFace response", res);
      setHasProfile(res.profile_upserted);
      setDone(true);
      stopCamera();
    } catch (err) {
      console.error("[FaceScan] scanFace failed", err);
      setError(err instanceof ApiError ? err.detail : "Failed to store your face. Try again.");
    } finally {
      setBusy(false);
      console.log("[FaceScan] submit finished");
    }
  }

  function capture() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) {
      console.warn("[FaceScan] capture: video/canvas not ready");
      return;
    }

    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
    ctx.restore();

    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    const parts = dataUrl.split(",");
    const mime = parts[0].match(/:(.*?);/)?.[1] ?? "image/jpeg";
    const bytes = atob(parts[1]);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: mime });
    const file = new File([blob], `face-${captures.length + 1}.jpg`, { type: mime });

    const next = [...captures, { file, preview: URL.createObjectURL(blob) }];
    console.log(`[FaceScan] captured ${next.length}/3`);
    setCaptures(next);

    if (next.length === 3) {
      console.log("[FaceScan] all 3 captured, submitting");
      submit(next.map((c) => c.file));
    }
  }

  const styles = {
    container: {
      marginTop: 24,
      border: "1px solid #ddd",
      borderRadius: 8,
      padding: 16,
      maxWidth: 520,
    } as const,
    video: {
      width: "100%",
      borderRadius: 8,
      background: "#000",
      transform: "scaleX(-1)",
    } as const,
    steps: { display: "flex", gap: 10, marginBottom: 14, justifyContent: "center" } as const,
  };

  if (done) {
    return (
      <section style={styles.container}>
        <h2 style={{ marginTop: 0 }}>Face profile</h2>
        <p style={{ color: "#1a7f37", fontWeight: 600 }}>✔ Face stored — done!</p>
        <p>
          <button onClick={() => setDone(false)}>Scan again</button>
        </p>
      </section>
    );
  }

  return (
    <section style={styles.container}>
      <h2 style={{ marginTop: 0 }}>Face profile</h2>
      {!camOn ? (
        <>
          <p>
            Status:{" "}
            {hasProfile === null ? "checking…" : hasProfile ? "✔ stored" : "✘ not stored yet"}
          </p>
          <button onClick={startCamera}>Scan face</button>
          {error ? <p style={{ color: "#cf222e" }}>{error}</p> : null}
        </>
      ) : (
        <>
          <div style={styles.steps}>
            {POSES.map((p, i) => {
              const captured = captures.length > i;
              const active = captures.length === i;
              return (
                <div
                  key={p.id}
                  style={{
                    width: 66,
                    padding: "6px 4px",
                    borderRadius: 16,
                    textAlign: "center",
                    fontSize: "0.8rem",
                    fontWeight: 600,
                    border: `2px solid ${captured ? "#22c55e" : active ? "#3b82f6" : "#ccc"}`,
                    color: captured ? "#22c55e" : active ? "#3b82f6" : "#999",
                  }}
                >
                  {p.label}
                </div>
              );
            })}
          </div>

          <div style={{ position: "relative", background: "#000", borderRadius: 8 }}>
            <video ref={videoRef} autoPlay playsInline muted style={styles.video} />
            <div
              style={{
                position: "absolute",
                bottom: 12,
                left: "50%",
                transform: "translateX(-50%)",
                background: "rgba(0,0,0,0.7)",
                color: "#fff",
                padding: "6px 16px",
                borderRadius: 20,
                fontSize: "0.95rem",
                whiteSpace: "nowrap",
              }}
            >
              {captures.length < 3
                ? `${POSES[captures.length].label}: ${POSES[captures.length].text}`
                : "All captured — storing…"}
            </div>
          </div>
          <canvas ref={canvasRef} style={{ display: "none" }} />

          <div
            style={{
              display: "flex",
              gap: 10,
              marginTop: 12,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            {captures.map((c, i) => (
              <img
                key={i}
                src={c.preview}
                alt={POSES[i].label}
                style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 8, border: "2px solid #22c55e" }}
              />
            ))}
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button onClick={capture} disabled={captures.length >= 3 || busy}>
              Capture {POSES[captures.length < 3 ? captures.length : 2].label}
            </button>
            <button onClick={stopCamera} disabled={busy}>
              Cancel
            </button>
          </div>
          {busy ? <p style={{ margin: "10px 0 0" }}>Storing your face…</p> : null}
          {error ? <p style={{ color: "#cf222e" }}>{error}</p> : null}
        </>
      )}
    </section>
  );
}
