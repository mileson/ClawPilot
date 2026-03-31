"use client";

import Image from "next/image";
import { useEffect } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "@/components/i18n/use-locale";
import { Button } from "@/components/ui/button";
import type { AgentSceneKey } from "@/lib/types";

export interface ScenePreset {
  id: string;
  name: string;
  story?: string;
  sources: Record<AgentSceneKey, string>;
  posterSrc?: string;
}

interface AgentScenePresetsDialogProps {
  open: boolean;
  onClose: () => void;
  presets: ScenePreset[];
  sceneLabels: Record<AgentSceneKey, string>;
  selectedPresetId: string | null;
  applyingPresetId: string | null;
  errorMessage: string | null;
  onSelectPreset: (preset: ScenePreset) => void;
}

const SCENE_ORDER: AgentSceneKey[] = ["working", "idle", "offline", "crashed"];

export function AgentScenePresetsDialog({
  open,
  onClose,
  presets,
  sceneLabels,
  selectedPresetId,
  applyingPresetId,
  errorMessage,
  onSelectPreset,
}: AgentScenePresetsDialogProps) {
  const { t } = useI18n();

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-[82] flex items-center justify-center bg-black/35 px-4 py-6 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={onClose} />
      <section className="relative z-[83] flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-[28px] border border-[var(--line)] bg-[var(--background)] shadow-[0_28px_80px_rgba(15,23,42,0.22)]">
        <header className="border-b border-[var(--line)] px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-[0.24em] text-[var(--muted)]">
                {t("scenePresets.eyebrow")}
              </p>
              <h2 className="mt-2 font-[var(--font-serif)] text-3xl font-semibold text-[var(--text)]">
                {t("scenePresets.title")}
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">{t("scenePresets.description")}</p>
            </div>
            <Button type="button" variant="outline" className="rounded-full" onClick={onClose}>
              {t("scenePresets.actions.close")}
            </Button>
          </div>
          {errorMessage ? (
            <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {errorMessage}
            </p>
          ) : null}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-5">
          <div className="grid gap-4 md:grid-cols-2">
            {presets.map((preset) => (
              <div
                key={preset.id}
                className="rounded-2xl border border-[var(--line)] bg-white/85 px-4 py-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    {preset.posterSrc ? (
                      <div className="h-12 w-12 shrink-0 overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)] shadow-sm">
                        <Image
                          src={preset.posterSrc}
                          alt={preset.name}
                          width={48}
                          height={48}
                          className="h-full w-full object-cover"
                          unoptimized
                        />
                      </div>
                    ) : null}
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold uppercase tracking-[0.22em] text-[var(--muted)]">
                        {preset.name}
                      </p>
                      <p className="mt-1 text-[11px] text-[var(--muted)]">
                        {preset.story || t("scenePresets.note")}
                      </p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={selectedPresetId === preset.id ? "secondary" : "outline"}
                    className="rounded-full"
                    onClick={() => onSelectPreset(preset)}
                    disabled={applyingPresetId !== null || selectedPresetId === preset.id}
                  >
                    {applyingPresetId === preset.id
                      ? t("scenePresets.actions.applying")
                      : selectedPresetId === preset.id
                        ? t("scenePresets.actions.selected")
                        : t("scenePresets.actions.select")}
                  </Button>
                </div>

                <div className="mt-4 grid w-full grid-cols-2 gap-3">
                  {SCENE_ORDER.map((sceneKey) => (
                    <div key={sceneKey} className="min-w-0">
                      <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-black/90">
                        <video
                          src={preset.sources[sceneKey]}
                          poster={preset.posterSrc}
                          className="aspect-[16/10] h-full w-full object-cover"
                          autoPlay
                          loop
                          muted
                          playsInline
                          preload="metadata"
                        />
                      </div>
                      <p className="mt-2 text-center text-[11px] text-[var(--muted)]">
                        {sceneLabels[sceneKey]}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
