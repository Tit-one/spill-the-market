import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowSquareOut,
  Camera,
  CheckCircle,
  DeviceMobile,
  DownloadSimple,
  Eye,
  Info,
  Monitor,
  Pause,
  Play,
  Plus,
  SpinnerGap,
  Trash,
  WarningCircle,
  ArrowClockwise,
} from "@phosphor-icons/react";
import type { Lang, Study } from "./types";
import type {
  PageAudit,
  PageAuditSpec,
  PageProviders,
  PageVariantInput,
  ProviderId,
  PageSnapshot,
  ScreenshotInput,
  Viewport,
  GroundedObservation,
  PageAuditReport,
} from "./pageAnalysisTypes";
import { api } from "./api";
import { WorkspaceRequests } from "./workspaceRequests";
import type { OperationTicket } from "./workspaceRequests";
import { money, percent, plain } from "./utils";
import "./PageAnalysis.css";
import PageOverview from "./PageOverview";
export interface PageAnalysisProps {
  study: Study | null;
  lang: Lang;
  onOpenBrief: () => void;
  onPendingChange?: (pending: boolean) => void;
}
const active = (audit: PageAudit | null) =>
  !!audit && ["queued", "capturing", "analyzing"].includes(audit.status);
const variant = (id: "A" | "B"): PageVariantInput => ({
  id,
  label: `Page ${id}`,
  source: "demo",
  url: null,
  html: null,
  screenshots: [],
});
const defaults = (): PageAuditSpec => ({
  schema_version: "1.0",
  variants: [variant("A")],
  viewports: ["desktop", "mobile"],
  max_sections: 3,
  persona_count: 8,
  direct_vision_count: 2,
  advertisement_context: "",
});
const imagePath = (s: PageSnapshot, auditId: string) =>
  `/api/v1/page-audits/${encodeURIComponent(auditId)}/images/${encodeURIComponent(s.id)}`;
const sourceName = (source: string, t: (en: string, fr: string) => string) =>
  ({
    demo: t("Fictional demo", "Démo fictive"),
    public_url: t("Public URL", "URL publique"),
    html_render: t("Local HTML", "HTML local"),
    screenshot_import: t("Imported screenshot", "Capture importée"),
  })[source] ?? source;
export async function readScreenshot(
  file: File,
  viewport: Viewport,
): Promise<ScreenshotInput> {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
    throw new Error("Use PNG, JPEG or WebP screenshots.");
  if (file.size > 6_000_000)
    throw new Error(
      "Each screenshot must be at most 8 MB encoded (about 6 MB on disk).",
    );
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () =>
      reject(new Error("The screenshot could not be read."));
    reader.readAsDataURL(file);
  });
  if (data.length > 8_000_000)
    throw new Error("Each screenshot must be at most 8 MB encoded.");
  return {
    name: file.name.slice(0, 150),
    data_base64: data,
    viewport,
    scroll_y: 0,
  };
}
export function validatePageSpec(spec: PageAuditSpec): string | null {
  if (
    !Number.isInteger(spec.max_sections) ||
    spec.max_sections < 1 ||
    spec.max_sections > 6
  )
    return "Sections must be between 1 and 6.";
  if (
    !Number.isInteger(spec.persona_count) ||
    spec.persona_count < 1 ||
    spec.persona_count > 24
  )
    return "Choose 1 to 24 representative personas.";
  if (
    !Number.isInteger(spec.direct_vision_count) ||
    spec.direct_vision_count < 0 ||
    spec.direct_vision_count > 4
  )
    return "Choose 0 to 4 direct-image controls.";
  if (!spec.viewports.length) return "Select at least one viewport.";
  if (spec.direct_vision_count > spec.persona_count)
    return "Direct controls cannot exceed the persona sample.";
  if (spec.variants.some((v) => !v.label.trim()))
    return "Give each variant a label.";
  if (
    spec.variants.some(
      (v) => v.source === "url" && !/^https?:\/\//i.test(v.url ?? ""),
    )
  )
    return "Enter a public HTTP or HTTPS URL for each URL source.";
  if (spec.variants.some((v) => v.source === "html" && !v.html?.trim()))
    return "Paste HTML for each HTML source.";
  if (
    spec.variants.some(
      (v) => v.source === "screenshots" && !v.screenshots.length,
    )
  )
    return "Import at least one screenshot for each image source.";
  if (spec.variants.some((v) => v.screenshots.length > 12))
    return "Maximum 12 screenshots per variant.";
  if (
    spec.variants
      .flatMap((v) => v.screenshots)
      .reduce((n, s) => n + s.data_base64.length, 0) > 24_000_000
  )
    return "Combined screenshots exceed 24 MB encoded.";
  return null;
}
export default function PageAnalysis({
  study,
  lang,
  onOpenBrief,
  onPendingChange,
}: PageAnalysisProps) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en);
  const [spec, setSpec] = useState<PageAuditSpec>(defaults),
    [providers, setProviders] = useState<PageProviders | null>(null),
    [audits, setAudits] = useState<PageAudit[]>([]),
    [audit, setAudit] = useState<PageAudit | null>(null),
    [selectedSnapshot, setSelectedSnapshot] = useState(""),
    [providerId, setProviderId] = useState<ProviderId>("demo"),
    [allowRemote, setAllowRemote] = useState(false),
    [busy, setBusy] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [draftChanged, setDraftChanged] = useState(false);
  const gate = useRef(new WorkspaceRequests()),
    scope = useRef(0),
    currentAudit = useRef<string | null>(null),
    pendingCallback = useRef(onPendingChange);
  pendingCallback.current = onPendingChange;
  const apply = (next: PageAudit) => {
    currentAudit.current = next.id;
    setAudit(next);
    setAudits((old) => [next, ...old.filter((a) => a.id !== next.id)]);
    setSelectedSnapshot((old) =>
      next.snapshots.some((s) => s.id === old)
        ? old
        : (next.snapshots[0]?.id ?? ""),
    );
  };
  useEffect(() => {
    const epoch = ++scope.current,
      controller = new AbortController();
    gate.current.invalidate();
    currentAudit.current = null;
    setAudit(null);
    setAudits([]);
    setSpec(defaults());
    setSelectedSnapshot("");
    setProviderId("demo");
    setAllowRemote(false);
    setError("");
    setBusy("");
    setDraftChanged(false);
    setLoading(true);
    pendingCallback.current?.(false);
    if (!study) {
      setLoading(false);
      return () => controller.abort();
    }
    void Promise.all([
      api<PageProviders>(
        "/page-audit/providers",
        "GET",
        undefined,
        controller.signal,
      ),
      api<{ audits: PageAudit[] }>(
        `/studies/${study.id}/page-audits`,
        "GET",
        undefined,
        controller.signal,
      ),
    ])
      .then(([p, saved]) => {
        if (epoch !== scope.current || controller.signal.aborted) return;
        setProviders(p);
        setAudits(saved.audits);
        if (saved.audits[0]) {
          apply(saved.audits[0]);
          setProviderId(saved.audits[0].provider_id ?? "demo");
        }
      })
      .catch((e) => {
        if (epoch === scope.current && !controller.signal.aborted)
          setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (epoch === scope.current) setLoading(false);
      });
    return () => {
      controller.abort();
      scope.current++;
      gate.current.invalidate();
      pendingCallback.current?.(false);
    };
  }, [study?.id]);
  useEffect(() => {
    if (!active(audit) || !study) return;
    const controller = new AbortController(),
      epoch = scope.current,
      id = audit!.id;
    let timer: ReturnType<typeof setTimeout>;
    const valid = () =>
      !controller.signal.aborted &&
      scope.current === epoch &&
      currentAudit.current === id;
    const poll = async () => {
      if (gate.current.pending) {
        timer = setTimeout(poll, 250);
        return;
      }
      try {
        const next = await api<PageAudit>(
          `/page-audits/${id}`,
          "GET",
          undefined,
          controller.signal,
        );
        if (!valid()) return;
        if (gate.current.pending) {
          timer = setTimeout(poll, 250);
          return;
        }
        apply(next);
        if (active(next)) timer = setTimeout(poll, 800);
      } catch (e) {
        if (valid()) {
          setError(e instanceof Error ? e.message : String(e));
          timer = setTimeout(poll, 3000);
        }
      }
    };
    timer = setTimeout(poll, 650);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [audit?.id, audit?.status, study?.id]);
  async function operate(
    name: string,
    fn: (ticket: OperationTicket, valid: () => boolean) => Promise<void>,
  ) {
    const ticket = gate.current.begin();
    if (!ticket) return;
    const epoch = scope.current;
    const valid = () => ticket.current() && scope.current === epoch;
    setBusy(name);
    setError("");
    pendingCallback.current?.(true);
    try {
      await fn(ticket, valid);
    } catch (e) {
      if (valid()) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (ticket.finish()) {
        setBusy("");
        pendingCallback.current?.(false);
      }
    }
  }
  const edit = (next: PageAuditSpec) => {
    if (gate.current.pending) return;
    setSpec(next);
    setAllowRemote(false);
    setDraftChanged(true);
  };
  const editVariant = (id: string, changes: Partial<PageVariantInput>) =>
    edit({
      ...spec,
      variants: spec.variants.map((v) =>
        v.id === id ? { ...v, ...changes } : v,
      ),
    });
  const capture = () =>
    void operate("capture", async (_ticket, valid) => {
      if (!study) return;
      const invalid = validatePageSpec(spec);
      if (invalid) throw new Error(invalid);
      const response = await api<PageAudit | { audit: PageAudit }>(
        `/studies/${study.id}/page-audits`,
        "POST",
        spec,
      );
      if (!valid()) return;
      apply("audit" in response ? response.audit : response);
      setAllowRemote(false);
      setProviderId("demo");
      setDraftChanged(false);
    });
  const selectedProvider = providers?.providers.find(
      (p) => p.id === providerId,
    ),
    isRemote = selectedProvider?.scope === "remote",
    allDemo =
      !!audit?.snapshots.length &&
      audit.snapshots.every((s) => s.provenance === "demo");
  const analyzingBlocked =
    !audit ||
    audit.status !== "captured" ||
    draftChanged ||
    !selectedProvider?.available ||
    (providerId === "demo" && !allDemo) ||
    (!!isRemote && (!allowRemote || (study?.spec.api_budget_usd ?? 0) <= 0));
  const analyze = () =>
    void operate("analyze", async (_ticket, valid) => {
      if (!audit || analyzingBlocked) return;
      const next = await api<PageAudit>(
        `/page-audits/${audit.id}/analyze`,
        "POST",
        { provider_id: providerId, allow_remote: !!isRemote && allowRemote },
      );
      if (valid()) {
        apply(next);
        setAllowRemote(false);
      }
    });
  const action = (what: "cancel" | "resume") =>
    void operate(what, async (_ticket, valid) => {
      if (!audit) return;
      const next = await api<PageAudit>(
        `/page-audits/${audit.id}/${what}`,
        "POST",
      );
      if (valid()) {
        apply(next);
        setAllowRemote(false);
      }
    });
  const refresh = () =>
    void operate("refresh", async (_ticket, valid) => {
      if (!audit) return;
      const next = await api<PageAudit>(`/page-audits/${audit.id}`);
      if (valid()) apply(next);
    });
  const openAudit = (id: string) =>
    void operate("open", async (_ticket, valid) => {
      const next = await api<PageAudit>(`/page-audits/${id}`);
      if (valid()) {
        apply(next);
        setAllowRemote(false);
        setProviderId(next.provider_id ?? "demo");
        setDraftChanged(false);
      }
    });
  const addFiles = (id: string, files: FileList | null) => {
    if (!files?.length) return;
    void operate("files", async (_ticket, valid) => {
      const target = spec.variants.find((v) => v.id === id)!;
      if (target.screenshots.length + files.length > 12)
        throw new Error(
          t(
            "Maximum 12 screenshots per variant.",
            "12 captures au maximum par variante.",
          ),
        );
      const images = await Promise.all(
        Array.from(files).map((f) =>
          readScreenshot(f, spec.viewports[0] ?? "desktop"),
        ),
      );
      if (!valid()) return;
      const next = {
        ...spec,
        variants: spec.variants.map((v) =>
          v.id === id
            ? { ...v, screenshots: [...v.screenshots, ...images] }
            : v,
        ),
      };
      const total = next.variants
        .flatMap((v) => v.screenshots)
        .reduce((sum, s) => sum + s.data_base64.length, 0);
      if (total > 24_000_000)
        throw new Error(
          t(
            "Combined screenshots exceed 24 MB encoded.",
            "Les captures dépassent 24 Mo encodés au total.",
          ),
        );
      setSpec(next);
      setAllowRemote(false);
      setDraftChanged(true);
    });
  };
  if (!study)
    return (
      <div className="empty">
        <Camera size={32} />
        <h2>
          {t("Give the page an audience.", "Donnez un public à la page.")}
        </h2>
        <p>
          {t(
            "Prepare the brief to reuse its bounded synthetic personas, age range and real API cap.",
            "Préparez le brief pour réutiliser ses personas synthétiques limités, sa tranche d’âge et son plafond API réel.",
          )}
        </p>
        <button className="button" onClick={onOpenBrief}>
          {t("Open the brief", "Ouvrir le brief")}
          <ArrowRight />
        </button>
      </div>
    );
  const pending = !!busy || loading,
    snapshot =
      audit?.snapshots.find((s) => s.id === selectedSnapshot) ??
      audit?.snapshots[0],
    observation = audit?.report?.observations.find(
      (o) => o.snapshot_id === snapshot?.id,
    ),
    jobActive = active(audit),
    anotherActive = audits.some(active);
  return (
    <div className="page-analysis">
      <div className="page-phase-line">
        <span>
          <Camera />1 · {t("Capture locally", "Capturer localement")}
        </span>
        <ArrowRight />
        <span>
          <Eye />2 · {t("Choose an analysis", "Choisir une analyse")}
        </span>
        <span className="chip">
          {t("Separate from virtual sales", "Distinct des ventes virtuelles")}
        </span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <WarningCircle />
          <div>
            <strong>
              {t(
                "Page analysis needs your attention.",
                "L’analyse de page requiert votre attention.",
              )}
            </strong>
            <p>{error}</p>
            <p className="small">
              {t(
                "No paid request is retried automatically. Inspect the job and its reserved costs before continuing.",
                "Aucun appel payant n’est relancé automatiquement. Examinez le travail et ses coûts réservés avant de continuer.",
              )}
            </p>
          </div>
        </div>
      )}
      {audit?.report && (
        <PageOverview
          report={audit.report}
          lang={lang}
          onInspect={(id) => {
            if (id && audit.snapshots.some((s) => s.id === id))
              setSelectedSnapshot(id);
            document
              .querySelector(".page-evidence")
              ?.scrollIntoView?.({ block: "start" });
          }}
        />
      )}
      <fieldset disabled={pending}>
        <legend className="sr-only">
          {t("Page capture and analysis", "Capture et analyse de page")}
        </legend>
        <details className="page-capture-editor" open={!audit?.report}>
          <summary>
            {t(
              "Create or configure a page capture",
              "Créer ou configurer une capture de page",
            )}
          </summary>
          <section className="worksheet page-capture-form">
            <div className="sheet-header">
              <h2>{t("A page to look at", "Une page à observer")}</h2>
              <span className="chip">
                {t("New capture draft", "Nouvelle capture")}
              </span>
            </div>
            <div className="padded">
              <p className="page-local-note">
                <CheckCircle size={19} />
                {t(
                  "Capturing and importing keep screenshots local. Analysis is a separate, explicit action.",
                  "La capture et l’import conservent les images localement. L’analyse est une action distincte et explicite.",
                )}
              </p>
              <div
                className={`page-variants ${spec.variants.length === 2 ? "paired" : ""}`}
              >
                {spec.variants.map((v) => (
                  <section key={v.id} className="page-variant">
                    <div className="page-variant-heading">
                      <strong>
                        {t("Variant", "Variante")} {v.id}
                      </strong>
                      {v.id === "B" && (
                        <button
                          className="icon-button danger"
                          aria-label={t(
                            "Remove variant B",
                            "Retirer la variante B",
                          )}
                          onClick={() =>
                            edit({
                              ...spec,
                              variants: spec.variants.filter(
                                (x) => x.id !== "B",
                              ),
                            })
                          }
                        >
                          <Trash />
                        </button>
                      )}
                    </div>
                    <label className="field">
                      <span>
                        {t(
                          `Variant ${v.id} label`,
                          `Libellé de la variante ${v.id}`,
                        )}
                      </span>
                      <input
                        maxLength={150}
                        required
                        value={v.label}
                        onChange={(e) =>
                          editVariant(v.id, { label: e.target.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>
                        {t(
                          `Variant ${v.id} source`,
                          `Source de la variante ${v.id}`,
                        )}
                      </span>
                      <select
                        value={v.source}
                        onChange={(e) =>
                          editVariant(v.id, {
                            source: e.target
                              .value as PageVariantInput["source"],
                            url: null,
                            html: null,
                            screenshots: [],
                          })
                        }
                      >
                        <option value="demo">
                          {t("Fictional demo", "Démo fictive")}
                        </option>
                        <option value="url">
                          {t("Public URL", "URL publique")}
                        </option>
                        <option value="html">
                          {t("Import HTML", "Importer du HTML")}
                        </option>
                        <option value="screenshots">
                          {t("Import screenshots", "Importer des captures")}
                        </option>
                      </select>
                    </label>
                    {v.source === "url" && (
                      <>
                        <label className="field">
                          <span>
                            {t(
                              `Variant ${v.id} public URL`,
                              `URL publique de la variante ${v.id}`,
                            )}
                          </span>
                          <input
                            type="url"
                            maxLength={2048}
                            placeholder="https://example.org/product"
                            value={v.url ?? ""}
                            onChange={(e) =>
                              editVariant(v.id, { url: e.target.value })
                            }
                          />
                        </label>
                        <p className="page-source-warning">
                          {t(
                            "Static capture: JavaScript is disabled. Dynamic content may be missing. For a single-page app, import screenshots you captured yourself.",
                            "Capture statique : JavaScript est désactivé. Des contenus dynamiques peuvent manquer. Pour une application web dynamique, importez vos propres captures.",
                          )}
                        </p>
                      </>
                    )}
                    {v.source === "html" && (
                      <>
                        <label className="field">
                          <span>
                            {t(
                              `Variant ${v.id} HTML`,
                              `HTML de la variante ${v.id}`,
                            )}
                          </span>
                          <textarea
                            rows={6}
                            maxLength={500000}
                            value={v.html ?? ""}
                            onChange={(e) =>
                              editVariant(v.id, { html: e.target.value })
                            }
                            placeholder="<main>…</main>"
                          />
                        </label>
                        <p className="page-source-warning">
                          {t(
                            "HTML is rendered locally with scripts and network disabled. External images and fonts may be absent.",
                            "Le HTML est rendu localement, sans scripts ni réseau. Des images et polices externes peuvent être absentes.",
                          )}
                        </p>
                      </>
                    )}
                    {v.source === "screenshots" && (
                      <>
                        <label className="field">
                          <span>
                            {t(
                              `Variant ${v.id} screenshot files`,
                              `Fichiers de capture de la variante ${v.id}`,
                            )}
                          </span>
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            multiple
                            onChange={(e) => addFiles(v.id, e.target.files)}
                          />
                          <small>
                            {t(
                              "PNG/JPEG/WebP. 12 images per variant; 8 MB encoded each, 24 MB total.",
                              "PNG/JPEG/WebP. 12 images par variante ; 8 Mo encodés par image, 24 Mo au total.",
                            )}
                          </small>
                        </label>
                        <div className="page-upload-list">
                          {v.screenshots.map((image, i) => (
                            <div key={`${image.name}-${i}`}>
                              <strong>{image.name}</strong>
                              <label>
                                <span>{t("Viewport", "Vue")}</span>
                                <select
                                  aria-label={`${v.id} ${image.name} ${t("viewport", "vue")}`}
                                  value={image.viewport}
                                  onChange={(e) =>
                                    editVariant(v.id, {
                                      screenshots: v.screenshots.map((s, j) =>
                                        j === i
                                          ? {
                                              ...s,
                                              viewport: e.target
                                                .value as Viewport,
                                            }
                                          : s,
                                      ),
                                    })
                                  }
                                >
                                  <option value="desktop">
                                    {t("Desktop", "Ordinateur")}
                                  </option>
                                  <option value="mobile">Mobile</option>
                                </select>
                              </label>
                              <label>
                                <span>
                                  {t("Scroll offset (px)", "Défilement (px)")}
                                </span>
                                <input
                                  aria-label={`${v.id} ${image.name} ${t("scroll offset", "défilement")}`}
                                  type="number"
                                  min={0}
                                  max={200000}
                                  value={image.scroll_y}
                                  onChange={(e) =>
                                    editVariant(v.id, {
                                      screenshots: v.screenshots.map((s, j) =>
                                        j === i
                                          ? {
                                              ...s,
                                              scroll_y: Number(e.target.value),
                                            }
                                          : s,
                                      ),
                                    })
                                  }
                                />
                              </label>
                              <button
                                className="icon-button danger"
                                aria-label={t(
                                  `Remove ${image.name}`,
                                  `Retirer ${image.name}`,
                                )}
                                onClick={() =>
                                  editVariant(v.id, {
                                    screenshots: v.screenshots.filter(
                                      (_, j) => j !== i,
                                    ),
                                  })
                                }
                              >
                                <Trash size={18} />
                              </button>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                    {v.source === "demo" && (
                      <p className="muted small">
                        {t(
                          "A visibly fictional product page. Demo reactions are illustrative, with no model call.",
                          "Une page produit explicitement fictive. Les réactions de démonstration sont illustratives, sans appel de modèle.",
                        )}
                      </p>
                    )}
                  </section>
                ))}
              </div>
              {spec.variants.length === 1 && (
                <button
                  className="button secondary compact page-add-variant"
                  onClick={() =>
                    edit({
                      ...spec,
                      variants: [...spec.variants, variant("B")],
                    })
                  }
                >
                  <Plus />
                  {t("Add paired variant B", "Ajouter la variante B appariée")}
                </button>
              )}
              <div className="page-capture-options">
                <div>
                  <span className="page-field-title">
                    {t("Capture viewports", "Vues à capturer")}
                  </span>
                  <div className="button-row">
                    {(["desktop", "mobile"] as const).map((v) => (
                      <label className="checkbox" key={v}>
                        <input
                          type="checkbox"
                          checked={spec.viewports.includes(v)}
                          onChange={(e) =>
                            edit({
                              ...spec,
                              viewports: e.target.checked
                                ? [...spec.viewports, v]
                                : spec.viewports.filter((x) => x !== v),
                            })
                          }
                        />
                        {v === "desktop" ? (
                          <Monitor size={17} />
                        ) : (
                          <DeviceMobile size={17} />
                        )}{" "}
                        {v === "desktop"
                          ? t("Desktop", "Ordinateur")
                          : t("Mobile", "Mobile")}
                      </label>
                    ))}
                  </div>
                </div>
                <label className="field">
                  <span>{t("Sections per viewport", "Sections par vue")}</span>
                  <input
                    type="number"
                    min={1}
                    max={6}
                    value={spec.max_sections}
                    onChange={(e) =>
                      edit({ ...spec, max_sections: Number(e.target.value) })
                    }
                  />
                </label>
                <label className="field">
                  <span>
                    {t("Representative personas", "Personas représentatifs")}
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={24}
                    value={spec.persona_count}
                    onChange={(e) =>
                      edit({ ...spec, persona_count: Number(e.target.value) })
                    }
                  />
                </label>
                <label className="field">
                  <span>
                    {t("Direct-image controls", "Contrôles par image directe")}
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={Math.min(4, spec.persona_count)}
                    value={spec.direct_vision_count}
                    onChange={(e) =>
                      edit({
                        ...spec,
                        direct_vision_count: Number(e.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <label className="field">
                <span>
                  {t(
                    "Advertisement that led to the page",
                    "Publicité ayant conduit à la page",
                  )}
                </span>
                <textarea
                  rows={2}
                  maxLength={2000}
                  value={spec.advertisement_context}
                  onChange={(e) =>
                    edit({ ...spec, advertisement_context: e.target.value })
                  }
                  placeholder={t(
                    "Preserve the promise and expectations from the ad…",
                    "Conservez la promesse et les attentes créées par la publicité…",
                  )}
                />
              </label>
              <div className="page-capture-submit">
                <p>
                  {t(
                    "The first viewport is retained separately. Personas see sections progressively; later information is not included in their first impression.",
                    "Le premier écran est conservé séparément. Les personas découvrent les sections progressivement ; leur première impression n’inclut pas les informations suivantes.",
                  )}
                </p>
                <button
                  className="button"
                  disabled={
                    !providers?.capture.available || anotherActive || jobActive
                  }
                  onClick={capture}
                >
                  {busy === "capture" ? (
                    <SpinnerGap className="spin" />
                  ) : (
                    <Camera />
                  )}
                  {t("Capture locally", "Capturer localement")}
                </button>
              </div>
              {providers && !providers.capture.available && (
                <p className="inline-warning">{providers.capture.reason}</p>
              )}
            </div>
          </section>
        </details>
        {audits.length > 0 && (
          <label className="field page-history">
            <span>
              {t(
                "Saved page captures & analyses",
                "Captures et analyses enregistrées",
              )}
            </span>
            <select
              value={audit?.id ?? ""}
              onChange={(e) => openAudit(e.target.value)}
            >
              {audits.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.spec.variants.map((v) => v.label).join(" / ")} · {a.status}{" "}
                  · {new Date(a.created_at).toLocaleString(lang)}
                </option>
              ))}
            </select>
          </label>
        )}
        {audit && (
          <>
            <section className="worksheet page-job">
              <div className="sheet-header">
                <div>
                  <h2>
                    {jobActive
                      ? t("Work in progress", "Travail en cours")
                      : audit.status === "completed"
                        ? t("Analysis completed", "Analyse terminée")
                        : t("Capture status", "État de la capture")}
                  </h2>
                  <p>{audit.progress.message}</p>
                </div>
                <span className="chip">{audit.status}</span>
                <strong>{Math.round(audit.progress.percent)}%</strong>
              </div>
              <progress
                max={100}
                value={audit.progress.percent}
                aria-label={t(
                  "Page audit progress",
                  "Progression de l’analyse de page",
                )}
              />
              <div className="padded button-row">
                <button className="button secondary compact" onClick={refresh}>
                  <ArrowClockwise />
                  {t("Refresh status", "Actualiser")}
                </button>
                {jobActive && (
                  <button
                    className="button secondary compact"
                    onClick={() => action("cancel")}
                  >
                    <Pause />
                    {t("Cancel safely", "Annuler proprement")}
                  </button>
                )}
                {["cancelled", "interrupted", "failed"].includes(
                  audit.status,
                ) &&
                  audit.error_code !== "uncertain_provider_dispatch" && (
                    <button
                      className="button compact"
                      disabled={
                        providers?.providers.find(
                          (p) => p.id === audit.provider_id,
                        )?.scope === "remote" && !allowRemote
                      }
                      onClick={() => action("resume")}
                    >
                      <Play />
                      {t(
                        "Resume saved work",
                        "Reprendre le travail sauvegardé",
                      )}
                    </button>
                  )}
                <span className="small muted">
                  {t(
                    "Capture ≠ analysis ≠ functional navigation.",
                    "Capture ≠ analyse ≠ navigation fonctionnelle.",
                  )}
                </span>
              </div>
              {audit.error && (
                <p className="inline-error padded">{audit.error}</p>
              )}
            </section>
            {audit.snapshots.length > 0 && (
              <section className="worksheet page-evidence">
                <div className="sheet-header">
                  <h2>{t("Captured evidence", "Éléments capturés")}</h2>
                  <span className="chip">
                    {audit.snapshots.length}{" "}
                    {t("local images", "images locales")}
                  </span>
                </div>
                <div
                  className="page-snapshot-tabs"
                  role="group"
                  aria-label={t("Captured sections", "Sections capturées")}
                >
                  {audit.snapshots.map((s) => (
                    <button
                      key={s.id}
                      className={snapshot?.id === s.id ? "selected" : ""}
                      onClick={() => setSelectedSnapshot(s.id)}
                      aria-pressed={snapshot?.id === s.id}
                    >
                      {s.variant_id} ·{" "}
                      {s.viewport === "desktop"
                        ? t("Desktop", "Ordinateur")
                        : "Mobile"}{" "}
                      · {t("Section", "Section")} {s.section_index + 1}
                    </button>
                  ))}
                </div>
                {snapshot && (
                  <SnapshotEvidence
                    auditId={audit.id}
                    snapshot={snapshot}
                    observation={observation}
                    lang={lang}
                    label={
                      audit.spec.variants.find(
                        (v) => v.id === snapshot.variant_id,
                      )?.label ?? `Page ${snapshot.variant_id}`
                    }
                  />
                )}
              </section>
            )}
            <details className="page-analysis-settings" open={!audit.report}>
              <summary>
                {t(
                  "Analysis model, permissions and real costs",
                  "Modèle, autorisations et coûts réels de l’analyse",
                )}
              </summary>
              <section className="worksheet page-analysis-choice">
                <div className="sheet-header">
                  <h2>
                    {t("Choose how to analyse", "Choisissez comment analyser")}
                  </h2>
                  <span className="chip">
                    {t("Explicit dispatch", "Envoi explicite")}
                  </span>
                </div>
                <div className="padded">
                  <div className="form-grid">
                    <label className="field">
                      <span>
                        {t(
                          "Analysis provider / model",
                          "Fournisseur / modèle d’analyse",
                        )}
                      </span>
                      <select
                        value={providerId}
                        disabled={
                          jobActive ||
                          ["cancelled", "interrupted", "failed"].includes(
                            audit.status,
                          )
                        }
                        onChange={(e) => {
                          setProviderId(e.target.value as ProviderId);
                          setAllowRemote(false);
                        }}
                      >
                        {providers?.providers.map((p) => (
                          <option
                            key={p.id}
                            value={p.id}
                            disabled={!p.available}
                          >
                            {p.name} · {p.model ?? "—"} ·{" "}
                            {p.scope === "remote"
                              ? t("remote", "distant")
                              : t("local", "local")}
                            {!p.available
                              ? ` · ${t("unavailable", "indisponible")}`
                              : ""}
                          </option>
                        ))}
                      </select>
                      <small>{selectedProvider?.reason}</small>
                    </label>
                    <div className="page-cost-cap">
                      <span>
                        {t("Saved real API cap", "Plafond API réel enregistré")}
                      </span>
                      <strong>
                        {money(study.spec.api_budget_usd * 100, "USD", lang)}
                      </strong>
                      <button className="text-button" onClick={onOpenBrief}>
                        {t(
                          "Edit in a new brief",
                          "Modifier dans un nouveau brief",
                        )}
                      </button>
                      <small>
                        {t(
                          "Shared study ledger. Virtual media spending is separate.",
                          "Registre partagé de l’étude. Le budget média virtuel est distinct.",
                        )}
                      </small>
                    </div>
                  </div>
                  {providerId === "demo" && !allDemo && (
                    <p className="inline-warning">
                      {t(
                        "Demo analysis only accepts fictional captures. Choose an available vision provider for this page.",
                        "L’analyse de démonstration accepte uniquement les captures fictives. Choisissez un fournisseur visuel disponible pour cette page.",
                      )}
                    </p>
                  )}
                  {isRemote && (
                    <label className="checkbox page-remote-consent">
                      <input
                        type="checkbox"
                        checked={allowRemote}
                        disabled={jobActive}
                        onChange={(e) => setAllowRemote(e.target.checked)}
                      />
                      <span>
                        {t(
                          `Send the selected screenshots, visible page evidence and sampled persona context to ${selectedProvider?.name} / ${selectedProvider?.model}.`,
                          `Envoyer les captures choisies, les éléments visibles et le contexte des personas échantillonnés à ${selectedProvider?.name} / ${selectedProvider?.model}.`,
                        )}
                        <small>
                          {t(
                            "This authorizes this analysis within the saved real cap. It does not grant unlimited calls. Consent resets when the provider, capture or study changes.",
                            "Cette autorisation concerne cette analyse dans le plafond réel enregistré. Elle n’autorise pas des appels illimités. Le consentement est réinitialisé au changement de fournisseur, capture ou étude.",
                          )}
                        </small>
                      </span>
                    </label>
                  )}
                  {isRemote && study.spec.api_budget_usd <= 0 && (
                    <p className="inline-warning">
                      {t(
                        "Prepare a brief with a positive real API cap before remote analysis.",
                        "Préparez un brief avec un plafond API réel positif avant l’analyse distante.",
                      )}
                    </p>
                  )}
                  {draftChanged && (
                    <p className="inline-warning">
                      {t(
                        "The capture draft changed. Capture it locally before analysing those changes.",
                        "Le brouillon de capture a changé. Capturez-le localement avant d’analyser ces changements.",
                      )}
                    </p>
                  )}
                  <p className="page-analysis-explanation">
                    {t(
                      "The observer describes visible evidence first. Synthetic personas then receive only the section they have reached, preserving the advertisement context. A bounded direct-image sample checks information lost or added by the shared observer.",
                      "L’observateur décrit d’abord les éléments visibles. Les personas synthétiques ne reçoivent ensuite que la section atteinte, avec le contexte publicitaire. Un échantillon limité voit directement les images pour contrôler les pertes et ajouts de l’observateur commun.",
                    )}
                  </p>
                  <button
                    className="button"
                    disabled={analyzingBlocked}
                    onClick={analyze}
                  >
                    {busy === "analyze" ? (
                      <SpinnerGap className="spin" />
                    ) : (
                      <Eye />
                    )}
                    {t("Analyse captured page", "Analyser la page capturée")}
                  </button>
                  <details className="page-pricing">
                    <summary>
                      {t(
                        "Model prices, limits & actual cost record",
                        "Prix du modèle, limites et coûts réels",
                      )}
                    </summary>
                    <h3>
                      {t("Configured pricing assumptions", "Tarifs configurés")}
                    </h3>
                    <pre>{plain(selectedProvider?.pricing ?? {})}</pre>
                    <h3>
                      {t(
                        "Shared study cost ledger",
                        "Registre des coûts partagé de l’étude",
                      )}
                    </h3>
                    <pre>{plain(audit.cost)}</pre>
                  </details>
                </div>
              </section>
            </details>
            {audit.report && (
              <PageReport
                onSelectSnapshot={(id) => {
                  if (audit.snapshots.some((s) => s.id === id)) {
                    setSelectedSnapshot(id);
                    document
                      .querySelector(".page-evidence")
                      ?.scrollIntoView?.({ block: "start" });
                  }
                }}
                report={audit.report}
                snapshot={snapshot}
                study={study}
                lang={lang}
              />
            )}
            {audit.report && (
              <div className="page-downloads">
                <span>{t("Export this audit", "Exporter cette analyse")}</span>
                {(["json", "html", "md", "csv"] as const).map((format) => (
                  <a
                    key={format}
                    className="export-link"
                    href={`/api/v1/page-audits/${audit.id}/export?format=${format}`}
                    download
                  >
                    <DownloadSimple size={16} />
                    {format.toUpperCase()}
                  </a>
                ))}
              </div>
            )}
          </>
        )}
      </fieldset>
      <div className="notice page-functional-limit">
        <Info size={19} />
        <p>
          {t(
            "Visual reading cannot prove that a button, navigation path or checkout works. Buying intentions are synthetic, conditional reactions, not observed demand. Autonomous functional browsing remains future work.",
            "La lecture visuelle ne prouve pas le fonctionnement d’un bouton, d’un parcours ou d’un paiement. Les intentions d’achat sont des réactions synthétiques conditionnelles, pas une demande observée. La navigation fonctionnelle autonome reste ultérieure.",
          )}
        </p>
      </div>
    </div>
  );
}

function SnapshotEvidence({
  auditId,
  snapshot: s,
  observation: o,
  lang,
  label,
}: {
  auditId: string;
  snapshot: PageSnapshot;
  observation?: GroundedObservation;
  lang: Lang;
  label: string;
}) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en),
    [region, setRegion] = useState("");
  useEffect(() => setRegion(""), [s.id]);
  const selected = o?.regions.find((r) => r.id === region) ?? o?.regions[0];
  return (
    <div className="page-evidence-content">
      <div>
        <div className="page-image-wrap">
          <img
            src={imagePath(s, auditId)}
            alt={`${label} · ${s.viewport} · ${t("Section", "Section")} ${s.section_index + 1}`}
          />
          {o?.regions.map((r, i) => (
            <button
              key={r.id}
              className={`page-region ${selected?.id === r.id ? "selected" : ""}`}
              style={{
                left: `${(100 * r.box.x) / s.width}%`,
                top: `${(100 * r.box.y) / s.height}%`,
                width: `${Math.min(100, (100 * r.box.width) / s.width)}%`,
                height: `${Math.min(100, (100 * r.box.height) / s.height)}%`,
              }}
              aria-label={t(
                `Inspect region ${i + 1}: ${r.literal_text || r.kind}`,
                `Examiner la région ${i + 1} : ${r.literal_text || r.kind}`,
              )}
              onClick={() => setRegion(r.id)}
            >
              <span>{i + 1}</span>
            </button>
          ))}
        </div>
        <div className="page-image-caption">
          <span>
            {sourceName(s.provenance, t)} · {s.width}×{s.height} · y=
            {s.scroll_y}px
          </span>
          <a href={imagePath(s, auditId)} target="_blank" rel="noreferrer">
            {t("Open full image", "Ouvrir l’image entière")}
            <ArrowSquareOut size={14} />
          </a>
        </div>
        {s.warnings.map((w, i) => (
          <p className="page-source-warning" key={i}>
            {w}
          </p>
        ))}
        <details className="page-capture-details">
          <summary>
            {t("Capture provenance & visible DOM", "Provenance et DOM visible")}
          </summary>
          <p>{new Date(s.captured_at).toLocaleString(lang)}</p>
          <p className="hash">SHA-256 {s.content_hash}</p>
          <p className="muted small">
            {t(
              "DOM text is supplementary evidence, not a substitute for observing the image.",
              "Le texte DOM est une preuve complémentaire, pas un substitut à l’observation de l’image.",
            )}
          </p>
          {s.dom.map((el) => (
            <div className="page-dom-line" key={el.id}>
              <strong>{el.tag}</strong>
              <span>{el.text}</span>
              <small>{el.id}</small>
            </div>
          ))}
        </details>
      </div>
      <aside className="page-observation">
        <h3>
          {t("Objective visual description", "Description visuelle objective")}
        </h3>
        {o ? (
          <>
            <span
              className={`chip ${o.mode === "demo" ? "assumption" : "observed"}`}
            >
              {o.mode === "demo"
                ? t("Fictional demonstration", "Démonstration fictive")
                : t(
                    "Image-grounded observation",
                    "Observation fondée sur l’image",
                  )}
            </span>
            <p>{o.summary}</p>
            {selected && (
              <section className="page-region-description">
                <label className="field">
                  <span>{t("Observed region", "Région observée")}</span>
                  <select
                    value={selected.id}
                    onChange={(e) => setRegion(e.target.value)}
                  >
                    {o.regions.map((r, i) => (
                      <option key={r.id} value={r.id}>
                        {i + 1} · {r.kind} · {r.literal_text.slice(0, 70)}
                      </option>
                    ))}
                  </select>
                </label>
                {selected.literal_text && (
                  <blockquote>{selected.literal_text}</blockquote>
                )}
                <p>{selected.description}</p>
                {selected.uncertainty && (
                  <p className="page-source-warning">
                    <strong>{t("Uncertainty", "Incertitude")}: </strong>
                    {selected.uncertainty}
                  </p>
                )}
                <small className="muted">
                  {selected.id} · x={selected.box.x}, y={selected.box.y},{" "}
                  {selected.box.width}×{selected.box.height}
                </small>
              </section>
            )}
            <h4>{t("Unknown / not established", "Inconnu / non établi")}</h4>
            {o.unknowns.length ? (
              <ul>
                {o.unknowns.map((v, i) => (
                  <li key={i}>{v}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                {t(
                  "No additional unknowns supplied.",
                  "Aucun élément inconnu supplémentaire fourni.",
                )}
              </p>
            )}
            <details className="page-interpretations">
              <summary>
                {t(
                  "Interpretations — separate from observations",
                  "Interprétations — distinctes des observations",
                )}
              </summary>
              <ul>
                {o.interpretations.map((v, i) => (
                  <li key={i}>{v}</li>
                ))}
              </ul>
            </details>
          </>
        ) : (
          <p className="muted">
            {t(
              "Captured locally. No observer analysis has been performed for this section.",
              "Capture locale. Aucune analyse par observateur n’a encore été effectuée pour cette section.",
            )}
          </p>
        )}
      </aside>
    </div>
  );
}
function PageReport({
  onSelectSnapshot,
  report: r,
  snapshot,
  study,
  lang,
}: {
  onSelectSnapshot: (id: string) => void;
  report: PageAuditReport;
  snapshot?: PageSnapshot;
  study: Study;
  lang: Lang;
}) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en),
    reviews = r.reviews.filter((v) => v.snapshot_id === snapshot?.id),
    action = (value: string) =>
      ({
        scroll: t(
          "Scroll to the next section",
          "Faire défiler vers la section suivante",
        ),
        seek_information: t("Seek information", "Rechercher une information"),
        consider_purchase: t("Consider purchasing", "Envisager un achat"),
        leave: t("Leave", "Quitter"),
      })[value] ?? value;
  return (
    <div className="page-report">
      <section className="worksheet">
        <div className="sheet-header">
          <div>
            <h2>
              {t(
                "Reactions at the current section",
                "Réactions à la section actuelle",
              )}
            </h2>
            <p>
              {t(
                "Select a captured section above to follow the next step.",
                "Sélectionnez une section capturée ci-dessus pour suivre l’étape suivante.",
              )}
            </p>
          </div>
          <span className="chip">
            {reviews.length} {t("reviews", "réactions")}
          </span>
        </div>
        <div className="padded">
          <p className="page-score-note">
            {t(
              "These are synthetic persona reactions. Trust and intention scores describe this simulated reading, not real customer conversion. Age is context alongside needs, means and prior expectations.",
              "Ces réactions proviennent de personas synthétiques. Les scores de confiance et d’intention décrivent cette lecture simulée, pas la conversion de clients réels. L’âge intervient avec les besoins, les moyens et les attentes initiales.",
            )}
          </p>
          <div className="page-persona-reviews">
            {reviews.map((review, i) => {
              const persona = study.personas.find(
                (p) => p.id === review.persona_id,
              );
              return (
                <article key={`${review.persona_id}-${review.mode}-${i}`}>
                  <details className="page-persona-disclosure" open={i === 0}>
                    <summary className="page-persona-toggle">
                      <div className="page-review-heading">
                        <h3>
                          {persona?.name ?? review.persona_id}{" "}
                          <span>
                            · {review.age} {t("years", "ans")}
                          </span>
                        </h3>
                        <span
                          className={`chip ${review.mode === "direct_vision" ? "inferred" : review.mode === "demo" ? "assumption" : ""}`}
                        >
                          {review.mode === "direct_vision"
                            ? t(
                                "Direct image control",
                                "Contrôle par image directe",
                              )
                            : review.mode === "demo"
                              ? t("Fictional reaction", "Réaction fictive")
                              : t(
                                  "Structured observation",
                                  "Observation structurée",
                                )}
                        </span>
                        <span className="small muted">
                          {t("Step", "Étape")} {review.step + 1} ·{" "}
                          {review.variant_id} · {review.viewport}
                        </span>
                      </div>
                    </summary>
                    <p className="page-understanding">{review.understanding}</p>
                    <div className="page-reaction-columns">
                      <section>
                        <h4>{t("Questions", "Questions")}</h4>
                        <ul>
                          {review.questions.map((q, j) => (
                            <li key={j}>{q}</li>
                          ))}
                        </ul>
                      </section>
                      <section>
                        <h4>{t("Friction", "Freins")}</h4>
                        <ul>
                          {review.frictions.map((q, j) => (
                            <li key={j}>{q}</li>
                          ))}
                        </ul>
                      </section>
                    </div>
                    {review.positives.length > 0 && (
                      <p className="small">
                        <strong>
                          {t("Positive signals", "Points positifs")}:{" "}
                        </strong>
                        {review.positives.join(" · ")}
                      </p>
                    )}
                    <dl className="page-reaction-scores">
                      <div>
                        <dt>{t("Confidence", "Certitude")}</dt>
                        <dd>{percent(review.confidence, lang)}</dd>
                      </div>
                      <div>
                        <dt>{t("Trust", "Confiance")}</dt>
                        <dd>{percent(review.trust, lang)}</dd>
                      </div>
                      <div>
                        <dt>
                          {t(
                            "Conditional intention",
                            "Intention conditionnelle",
                          )}
                        </dt>
                        <dd>
                          {percent(review.intention_before, lang)} →{" "}
                          {percent(review.intention_after, lang)}
                        </dd>
                      </div>
                      <div>
                        <dt>
                          {t(
                            "Intended next action",
                            "Action suivante envisagée",
                          )}
                        </dt>
                        <dd>{action(review.intended_action)}</dd>
                      </div>
                    </dl>
                    <details>
                      <summary>
                        {t(
                          "Visible information & evidence trace",
                          "Informations visibles et traces de preuve",
                        )}
                      </summary>
                      <p className="small">
                        {review.visible_information_ids.join(", ") || "—"}
                      </p>
                      <p className="small">
                        {review.evidence_ids.join(", ") || "—"}
                      </p>
                      <p className="hash">
                        {review.persona_id} · {review.snapshot_id}
                      </p>
                    </details>
                  </details>
                </article>
              );
            })}
            {!reviews.length && (
              <p className="muted">
                {t(
                  "No persona review was returned for the selected section.",
                  "Aucune réaction de persona n’a été renvoyée pour la section sélectionnée.",
                )}
              </p>
            )}
          </div>
        </div>
      </section>
      <details className="page-diagnostic-details">
        <summary>
          {t(
            "Comparisons, controls and provenance",
            "Comparaisons, contrôles et traçabilité",
          )}
        </summary>
        <AuditRecords
          onSelectSnapshot={onSelectSnapshot}
          title={t("Section findings", "Constats par section")}
          records={r.findings}
          lang={lang}
        />
        <AuditRecords
          onSelectSnapshot={onSelectSnapshot}
          title={t("Paired A/B comparison", "Comparaison A/B appariée")}
          records={r.comparisons}
          lang={lang}
        />
        <AuditRecords
          onSelectSnapshot={onSelectSnapshot}
          title={t(
            "Direct-image control comparison",
            "Comparaison du contrôle par image directe",
          )}
          records={r.direct_vision_controls}
          lang={lang}
        />
        <section className="worksheet">
          <div className="sheet-header">
            <h2>
              {t("Coverage, limits & receipts", "Couverture, limites et reçus")}
            </h2>
            <span className="chip">{r.mode}</span>
          </div>
          <div className="padded">
            <ul>
              {r.limitations.map((v, i) => (
                <li key={i}>{v}</li>
              ))}
            </ul>
            <details>
              <summary>
                {t("Audience coverage", "Couverture du public")}
              </summary>
              <pre>{plain(r.audience_coverage)}</pre>
            </details>
            <details>
              <summary>
                {t("Actual inference receipts", "Reçus d’inférence réels")}
              </summary>
              <pre>{plain(r.cost)}</pre>
            </details>
          </div>
        </section>
      </details>
    </div>
  );
}
function AuditRecords({
  title,
  records,
  lang,
  onSelectSnapshot,
}: {
  title: string;
  records: Record<string, unknown>[];
  lang: Lang;
  onSelectSnapshot: (id: string) => void;
}) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en);
  const delta = (v: unknown) =>
    typeof v === "number" ? `${v > 0 ? "+" : ""}${percent(v, lang)}` : "—";
  const pct = (v: unknown) => (typeof v === "number" ? percent(v, lang) : "—");
  const comparison = records.some((r) => "variant_a" in r),
    control = records.some((r) => "understanding_differs" in r);
  return (
    <section className="worksheet page-records">
      <div className="sheet-header">
        <h2>{title}</h2>
        <span>{records.length}</span>
      </div>
      {!records.length ? (
        <p className="padded muted">
          {t(
            "No comparison or finding was returned in this category.",
            "Aucune comparaison ni aucun constat renvoyé dans cette catégorie.",
          )}
        </p>
      ) : comparison ? (
        <>
          <div
            className="table-scroll"
            role="region"
            tabIndex={0}
            aria-label={title}
          >
            <table>
              <thead>
                <tr>
                  {[
                    t("Variants", "Variantes"),
                    t("Viewport", "Vue"),
                    t("Paired personas", "Personas appariés"),
                    t("Intention A", "Intention A"),
                    t("Intention B", "Intention B"),
                    t("Intention difference", "Écart d’intention"),
                    t("Trust difference", "Écart de confiance"),
                    t("Status", "Statut"),
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={i}>
                    <th>
                      {String(r.variant_a)} / {String(r.variant_b)}
                    </th>
                    <td>{String(r.viewport)}</td>
                    <td>
                      {String(r.paired_count ?? "—")} /{" "}
                      {String(r.persona_count ?? "—")}
                    </td>
                    <td>{pct(r.mean_intention_a)}</td>
                    <td>{pct(r.mean_intention_b)}</td>
                    <td>{delta(r.mean_intention_delta)}</td>
                    <td>{delta(r.mean_trust_delta)}</td>
                    <td>{String(r.status ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="table-caption">
            {t(
              "Conditional synthetic scores on paired initial personas. Differences are not measured conversion lifts.",
              "Scores synthétiques conditionnels sur des personas initiaux appariés. Les écarts ne mesurent pas des gains de conversion réels.",
            )}
          </p>
          {records
            .flatMap((r) => (Array.isArray(r.limitations) ? r.limitations : []))
            .map((v, i) => (
              <p className="padded small muted" key={i}>
                {String(v)}
              </p>
            ))}
        </>
      ) : control ? (
        <>
          <div
            className="table-scroll"
            role="region"
            tabIndex={0}
            aria-label={title}
          >
            <table>
              <thead>
                <tr>
                  {[
                    t("Persona / age", "Persona / âge"),
                    t("Variant / viewport", "Variante / vue"),
                    t("Step", "Étape"),
                    t("Understanding differs", "Compréhension différente"),
                    t("Intention difference", "Écart d’intention"),
                    t("Trust difference", "Écart de confiance"),
                    t("Evidence", "Preuve"),
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={i}>
                    <th>
                      {String(r.persona_id)} · {String(r.age)}
                    </th>
                    <td>
                      {String(r.variant_id)} · {String(r.viewport)}
                    </td>
                    <td>{Number(r.step) + 1}</td>
                    <td>
                      {r.understanding_differs
                        ? t("Yes", "Oui")
                        : t("No", "Non")}
                    </td>
                    <td>{delta(r.intention_delta)}</td>
                    <td>{delta(r.trust_delta)}</td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => onSelectSnapshot(String(r.snapshot_id))}
                      >
                        {t("View section", "Voir la section")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="table-caption">
            {t(
              "This compares direct-image and shared-observation reactions. Agreement does not establish real-person validity.",
              "Ce contrôle compare les réactions à l’image directe et à l’observation partagée. L’accord ne prouve pas la validité auprès de personnes réelles.",
            )}
          </p>
        </>
      ) : (
        <div className="padded page-findings">
          {records.map((r, i) => (
            <article key={String(r.id ?? i)}>
              <div>
                <span
                  className={`chip ${String(r.status) === "observed" ? "observed" : "assumption"}`}
                >
                  {String(r.status ?? t("Hypothesis", "Hypothèse"))}
                </span>
                <span className="small muted">
                  {String(r.severity ?? "")} · {String(r.kind ?? "")}
                </span>
                <span className="small muted">
                  {String(r.variant_id ?? "")} · {String(r.viewport ?? "")}
                </span>
              </div>
              <p>{String(r.text ?? r.title ?? "")}</p>
              {r.snapshot_id != null && (
                <button
                  className="text-button"
                  onClick={() => onSelectSnapshot(String(r.snapshot_id))}
                >
                  {t("Inspect this section", "Examiner cette section")}
                </button>
              )}
              <details>
                <summary>
                  {t(
                    "Evidence and affected personas",
                    "Preuves et personas concernés",
                  )}
                </summary>
                <dl>
                  {[
                    "snapshot_id",
                    "region_ids",
                    "persona_ids",
                    "evidence_ids",
                  ].map((key) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>
                        {Array.isArray(r[key])
                          ? r[key].map(String).join(", ")
                          : plain(r[key])}
                      </dd>
                    </div>
                  ))}
                </dl>
              </details>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
