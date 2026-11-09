"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui";
import { ApiError, getMe, scanFace } from "@/lib/api";

const POSES = [
  { id: "front", label: "Front", title: "First, look straight ahead", text: "Hold still" },
  { id: "left", label: "Left", title: "Next, look to your left", text: "Turn your head slowly" },
  { id: "right", label: "Right", title: "Now look to your right", text: "Turn your head slowly" },
] as const;

// Progress ring geometry (SVG units).
const RING_R = 48;
const RING_C = 2 * Math.PI * RING_R;

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

  if (done) {
    return (
      <section className="card">
        <div className="scan-status">
          <span className="scan-ring ready">
            <Icon.Check size={30} />
          </span>
          <div style={{ flex: 1 }}>
            <span className="eyebrow" style={{ color: "var(--ok)" }}>
              Face profile
            </span>
            <h2 className="h2" style={{ marginTop: 6 }}>
              You&apos;re all set
            </h2>
            <p className="muted small">Face stored. New event photos will be matched to you.</p>
          </div>
        </div>
        <button className="btn btn-sm" style={{ marginTop: 18 }} onClick={() => setDone(false)}>
          Scan again
        </button>
      </section>
    );
  }

  if (!camOn) {
    const ready = hasProfile === true;
    return (
      <section className="card">
        <div className="scan-status">
          <span className={`scan-ring ${hasProfile === null ? "" : ready ? "ready" : "missing"}`}>
            {hasProfile === null ? <span className="spinner" /> : <Icon.Face size={32} />}
          </span>
          <div style={{ flex: 1 }}>
            <span className="eyebrow" style={ready ? { color: "var(--ok)" } : undefined}>
              Face profile
            </span>
            <h2 className="h2" style={{ marginTop: 6 }}>
              {hasProfile === null
                ? "Checking…"
                : ready
                  ? "Profile stored"
                  : "Scan your face to get matched"}
            </h2>
            <p className="muted small">
              {ready
                ? "You can rescan any time to refresh it."
                : "Three quick poses — front, left, right. Takes about 20 seconds."}
            </p>
          </div>
        </div>
        <button
          className={`btn ${ready ? "" : "btn-primary"} btn-block`}
          style={{ marginTop: 18 }}
          onClick={startCamera}
        >
          <Icon.Face /> {ready ? "Rescan face" : "Start face scan"}
        </button>
        {error ? (
          <p className="alert alert-error" style={{ marginTop: 14 }}>
            {error}
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="h2">Face scan</h2>
        <span className="muted small">{Math.min(captures.length, 3)} / 3</span>
      </div>

      <div className="face-scan">
        <div className="face-circle">
          <video ref={videoRef} autoPlay playsInline muted />

          {/* Direction cue for the current pose (left / right only). */}
          {captures.length < 3 && POSES[captures.length].id !== "front" && (
            <svg
              key={POSES[captures.length].id}
              className={`face-arrow ${POSES[captures.length].id}`}
              viewBox="0 0 100 20"
              aria-hidden
            >
              <path d="M88 10H12M24 2 12 10l12 8" />
            </svg>
          )}

          <svg className="face-ring" viewBox="0 0 100 100" aria-hidden>
            <circle cx="50" cy="50" r={RING_R} className="track" />
            <circle
              cx="50"
              cy="50"
              r={RING_R}
              className="progress"
              strokeDasharray={RING_C}
              strokeDashoffset={RING_C * (1 - Math.min(captures.length, 3) / 3)}
            />
          </svg>
        </div>

        <div className="face-copy" aria-live="polite">
          <strong>
            {captures.length < 3 ? POSES[captures.length].title : "All set — saving your face…"}
          </strong>
          <span>{captures.length < 3 ? POSES[captures.length].text : "This takes a second"}</span>
        </div>

        <div className="face-dots" aria-hidden>
          {POSES.map((p, i) => (
            <span
              key={p.id}
              className={captures.length > i ? "done" : captures.length === i ? "active" : ""}
            />
          ))}
        </div>
      </div>
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {captures.length > 0 && (
        <div className="thumbs">
          {captures.map((c, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={i} src={c.preview} alt={POSES[i].label} />
          ))}
        </div>
      )}

      <div className="row" style={{ marginTop: 14 }}>
        <button
          className="btn btn-primary"
          style={{ flex: 1 }}
          onClick={capture}
          disabled={captures.length >= 3 || busy}
        >
          {busy ? (
            <>
              <span className="spinner" /> Storing your face…
            </>
          ) : (
            <>Capture {POSES[captures.length < 3 ? captures.length : 2].label}</>
          )}
        </button>
        <button className="btn" onClick={stopCamera} disabled={busy}>
          Cancel
        </button>
      </div>
      {error ? (
        <p className="alert alert-error" style={{ marginTop: 14 }}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
