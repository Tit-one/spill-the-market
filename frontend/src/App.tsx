/* THESIS: A working launch notebook; the brief and experiment spine lead, rather than metric cards.
 * OWN-WORLD: Bright experiment blue, dark ink, white worksheets, system sans and tabular data.
 * STORY: Describe a product, inspect evidence and people, edit three strategies, then run and compare.
 * FIRST VIEWPORT: Labelled blue rail, editable brief worksheet, compact timeline and reproducibility notes.
 * FORM: User-approved notebook direction; native controls, ordered workflow, quiet analytical results. */
import {
  useState,
  useEffect,
  useCallback,
  useRef,
  createContext,
  useContext,
  useId,
} from "react";
import type { ReactNode, FormEvent } from "react";
import {
  ArrowRight,
  ArrowSquareOut,
  ArrowClockwise,
  CheckCircle,
  ChartLineUp,
  DownloadSimple,
  FileText,
  Flask,
  GearSix,
  Globe,
  Info,
  Lightning,
  LockSimple,
  LockSimpleOpen,
  MagnifyingGlass,
  Notebook,
  Pause,
  Play,
  Plus,
  SpinnerGap,
  Trash,
  UsersThree,
  WarningCircle,
  X,
  Broadcast,
  CaretDown,
  CaretUp,
} from "@phosphor-icons/react";
import type {
  Lang,
  StudySpec,
  Bootstrap,
  Study,
  MediaPlan,
  Placement,
  ResearchRequest,
  TrendReport,
  Run,
  Report,
  Scenario,
  Persona,
  Finding,
  Category,
} from "./types";
import { api, setToken } from "./api";
import PageAnalysis from "./PageAnalysis";
import { WorkspaceRequests } from "./workspaceRequests";
import type { OperationTicket } from "./workspaceRequests";
import {
  channels,
  channelNames,
  initialSpec,
  money,
  number,
  percent,
  plain,
  safeURL,
  newPlacement,
  validateSpec,
} from "./utils";

type Tab =
  | "brief"
  | "research"
  | "personas"
  | "media"
  | "page"
  | "results"
  | "settings"
  | "roadmap";
const Language = createContext<Lang>("en");
const useCopy = () => {
  const l = useContext(Language);
  return (en: string, fr: string) => (l === "fr" ? fr : en);
};
const activeStatus = (s: string) =>
  ["queued", "running", "cancelling", "resuming"].includes(s);
const resumableStatus = (s: string) => ["cancelled", "interrupted"].includes(s);
function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <label className={`field ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <small id={id}>{hint}</small>}
    </label>
  );
}
function NumberField({
  label,
  value,
  onChange,
  min = 0,
  max,
  step = 1,
  hint,
  className,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  className?: string;
}) {
  return (
    <Field label={label} hint={hint} className={className}>
      <input
        required
        type="number"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? NaN : Number(e.target.value))
        }
      />
    </Field>
  );
}
function Empty({
  title,
  children,
  icon = <Notebook size={28} />,
}: {
  title: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">{icon}</span>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "warning" | "success";
}) {
  return (
    <div className={`notice ${tone}`}>
      <Info size={19} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}
function statusLabel(status: string, t: (en: string, fr: string) => string) {
  return (
    (
      {
        queued: t("Queued", "En attente"),
        running: t("Running", "En cours"),
        completed: t("Completed", "Terminée"),
        cancelled: t("Cancelled", "Annulée"),
        interrupted: t("Interrupted", "Interrompue"),
        failed: t("Failed", "Échec"),
        cancelling: t("Cancelling", "Annulation"),
        resuming: t("Resuming", "Reprise"),
      } as Record<string, string>
    )[status] ?? status
  );
}

export default function App() {
  const [lang, setLang] = useState<Lang>(() =>
    localStorage.getItem("spill-language") === "fr" ? "fr" : "en",
  );
  const t = useCallback(
    (en: string, fr: string) => (lang === "fr" ? fr : en),
    [lang],
  );
  const [pageBusy, setPageBusy] = useState(false);
  const initialized = useRef(false);
  const requests = useRef(new WorkspaceRequests());
  const selectedStudyId = useRef<string | null>(null);
  const selectedRunId = useRef<string | null>(null);
  const bootstrapGeneration = useRef(0);
  const [boot, setBoot] = useState<Bootstrap | null>(null),
    [bootLoading, setBootLoading] = useState(true),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [tab, setTab] = useState<Tab>("brief"),
    [spec, setSpec] = useState<StudySpec>(structuredClone(initialSpec)),
    [study, setStudy] = useState<Study | null>(null),
    [studies, setStudies] = useState<Study[]>([]),
    [plans, setPlans] = useState<MediaPlan[]>([]),
    [run, setRun] = useState<Run | null>(null),
    [busy, setBusy] = useState(""),
    [dirty, setDirty] = useState(false),
    [planDirty, setPlanDirty] = useState(false);
  const [researchRequest, setResearchRequest] = useState<ResearchRequest>(
    structuredClone(initialSpec.research),
  );
  const [cost, setCost] = useState<{
    studyId: string;
    ledger: Record<string, unknown>;
  } | null>(null);
  const chooseRun = (next: Run | null) => {
    selectedRunId.current = next?.id ?? null;
    setRun(next);
  };
  const adoptStudy = (next: Study) => {
    selectedStudyId.current = next.id;
    setStudy(next);
    setStudies((previous) => [
      next,
      ...previous.filter((saved) => saved.id !== next.id),
    ]);
  };
  const notify = (text: string) => {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 6000);
  };
  const loadBootstrap = useCallback(async () => {
    if (requests.current.pending) return;
    const generation = ++bootstrapGeneration.current;
    setBootLoading(true);
    setError("");
    try {
      const b = await api<Bootstrap>("/bootstrap");
      if (generation !== bootstrapGeneration.current) return;
      setToken(b.session_token);
      setBoot(b);
      if (b.examples[0] && !initialized.current) {
        initialized.current = true;
        setSpec({ ...b.examples[0].spec, locale: lang });
        setResearchRequest(b.examples[0].spec.research);
      }
      const saved = await api<{ studies: Study[] }>("/studies");
      if (generation === bootstrapGeneration.current)
        setStudies(saved.studies ?? []);
    } catch (e) {
      if (generation === bootstrapGeneration.current)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === bootstrapGeneration.current) setBootLoading(false);
    }
  }, []);
  useEffect(() => {
    void loadBootstrap();
    return () => {
      bootstrapGeneration.current++;
      requests.current.invalidate();
    };
  }, [loadBootstrap]);
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [tab]);
  useEffect(() => {
    document.documentElement.lang = lang;
    localStorage.setItem("spill-language", lang);
  }, [lang]);
  // Run history is study-owned. Poll responses may never update a newly selected notebook/run.
  useEffect(() => {
    if (!run || !activeStatus(run.status)) return;
    const ctrl = new AbortController();
    const studyId = run.study_id;
    const runId = run.id;
    const stillSelected = () =>
      !ctrl.signal.aborted &&
      selectedStudyId.current === studyId &&
      selectedRunId.current === runId;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (requests.current.pending) {
        timer = setTimeout(poll, 250);
        return;
      }
      try {
        const next = await api<Run>(
          `/runs/${runId}`,
          "GET",
          undefined,
          ctrl.signal,
        );
        if (!stillSelected()) return;
        if (requests.current.pending) {
          timer = setTimeout(poll, 250);
          return;
        }
        if (!activeStatus(next.status)) {
          const canonical = await api<Study>(
            `/studies/${studyId}`,
            "GET",
            undefined,
            ctrl.signal,
          );
          if (!stillSelected()) return;
          if (requests.current.pending) {
            timer = setTimeout(poll, 250);
            return;
          }
          setStudy(canonical);
          setStudies((previous) => [
            canonical,
            ...previous.filter((saved) => saved.id !== studyId),
          ]);
        }
        if (!stillSelected()) return;
        setRun(next);
        if (activeStatus(next.status)) timer = setTimeout(poll, 1000);
      } catch {
        if (stillSelected()) {
          setError(
            t(
              "Run monitoring disconnected. Retry using Refresh run.",
              "Le suivi est déconnecté. Utilisez Actualiser le suivi.",
            ),
          );
          timer = setTimeout(poll, 4000);
        }
      }
    };
    timer = setTimeout(poll, 700);
    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [run?.id, run?.status, t]);
  const editSpec = (next: StudySpec) => {
    if (requests.current.pending || pageBusy) return;
    setSpec(next);
    setDirty(!!study);
  };
  const selectExample = (id: string) => {
    if (requests.current.pending || bootLoading || pageBusy) return;
    const example = boot?.examples.find((value) => value.id === id);
    if (!example) return;
    requests.current.invalidate();
    selectedStudyId.current = null;
    setCost(null);
    setMessage("");
    setSpec({ ...structuredClone(example.spec), locale: lang });
    setResearchRequest(structuredClone(example.spec.research));
    setStudy(null);
    setPlans([]);
    chooseRun(null);
    setDirty(false);
    setPlanDirty(false);
    setTab("brief");
    setError("");
    notify(
      t(
        `Loaded fictional example: ${example.name}.`,
        `Exemple fictif chargé : ${example.name}.`,
      ),
    );
  };
  const act = async (
    key: string,
    fn: (ticket: OperationTicket) => Promise<void>,
  ) => {
    const ticket = requests.current.begin();
    if (!ticket) return;
    setBusy(key);
    setError("");
    try {
      await fn(ticket);
    } catch (e) {
      if (ticket.current())
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (ticket.finish()) setBusy("");
    }
  };
  const canonicalStudy = async (id: string, ticket: OperationTicket) => {
    const canonical = await api<Study>(`/studies/${id}`);
    if (!ticket.current() || selectedStudyId.current !== id) return null;
    adoptStudy(canonical);
    return canonical;
  };
  const prepare = async (ticket: OperationTicket, goToMedia = true) => {
    const errors = validateSpec(spec, lang);
    if (errors.length) throw new Error(errors.join(" "));
    const next = await api<Study>("/studies", "POST", {
      spec: {
        ...spec,
        audience: { ...spec.audience, auto_age: false },
        locale: lang,
        research: researchRequest,
      },
    });
    if (!ticket.current()) return null;
    setCost(null);
    adoptStudy(next);
    setSpec(next.spec);
    setPlans(next.plans);
    chooseRun(null);
    setDirty(false);
    setPlanDirty(false);
    if (goToMedia) setTab("media");
    return next;
  };
  const openStudy = (id: string) =>
    void act("open", async (ticket) => {
      const next = await api<Study>(`/studies/${id}`);
      const last = next.runs?.[0];
      const latest = last?.id ? await api<Run>(`/runs/${last.id}`) : null;
      if (!ticket.current()) return;
      setCost(null);
      setMessage("");
      adoptStudy(next);
      setSpec(next.spec);
      setResearchRequest(next.spec.research);
      setPlans(next.plans);
      chooseRun(latest);
      setDirty(false);
      setPlanDirty(false);
      setTab("media");
    });
  const savePlans = () =>
    void act("save", async (ticket) => {
      if (!study) return;
      const id = study.id;
      const submitted = structuredClone(plans);
      const canonical = await api<Study>(`/studies/${id}/plans`, "PUT", {
        plans: submitted,
      });
      if (!ticket.current() || selectedStudyId.current !== id) return;
      adoptStudy(canonical);
      setPlans(canonical.plans);
      setPlanDirty(false);
      notify(t("Media plans saved.", "Plans média enregistrés."));
    });
  const startRun = () =>
    void act("run", async (ticket) => {
      if (!study) return;
      const id = study.id;
      const next = await api<Run>(`/studies/${id}/runs`, "POST", {
        plans: structuredClone(plans),
      });
      if (!ticket.current() || selectedStudyId.current !== id) return;
      chooseRun(next);
      setTab("results");
      const canonical = await canonicalStudy(id, ticket);
      if (!canonical) return;
      // Creation atomically persists the submitted plans. Clear unsaved state only after reading that canonical study.
      setPlans(canonical.plans);
      setPlanDirty(false);
      notify(t("Experiment started.", "Expérience lancée."));
    });
  const openRun = (id: string) =>
    void act("open-run", async (ticket) => {
      const next = await api<Run>(`/runs/${id}`);
      if (!ticket.current() || selectedStudyId.current !== next.study_id)
        return;
      const canonical = await canonicalStudy(next.study_id, ticket);
      if (canonical && ticket.current()) chooseRun(next);
    });
  const refreshRun = () => {
    if (run) openRun(run.id);
  };
  const runAction = (action: "cancel" | "resume") =>
    void act(action, async (ticket) => {
      if (!run) return;
      const next = await api<Run>(`/runs/${run.id}/${action}`, "POST");
      if (!ticket.current() || selectedStudyId.current !== next.study_id)
        return;
      chooseRun(next);
      if (!(await canonicalStudy(next.study_id, ticket))) return;
      notify(
        action === "cancel"
          ? t("Cancellation requested.", "Annulation demandée.")
          : t(
              "Experiment resumed from its checkpoint.",
              "Expérience reprise depuis son point de sauvegarde.",
            ),
      );
    });
  const doResearch = () =>
    void act("research", async (ticket) => {
      if (
        researchRequest.mode === "live" &&
        (study && !dirty ? study.spec.api_budget_usd : spec.api_budget_usd) <= 0
      )
        throw new Error(
          t(
            "Set a real API cost cap above $0 in the brief before online research.",
            "Définissez un plafond API réel supérieur à 0 $ dans le brief avant une recherche en ligne.",
          ),
        );
      const current = study && !dirty ? study : await prepare(ticket, false);
      if (!current || !ticket.current()) return;
      const response = await api<{
        report: TrendReport;
        cost: Record<string, unknown>;
      }>(`/studies/${current.id}/research`, "POST", researchRequest);
      if (!ticket.current() || selectedStudyId.current !== current.id) return;
      const refreshed = await canonicalStudy(current.id, ticket);
      if (!refreshed) return;
      setPlans(refreshed.plans);
      setPlanDirty(false);
      setCost({ studyId: current.id, ledger: response.cost });
      notify(
        t(
          "Research completed. Inspect its sources and limitations below.",
          "Recherche terminée. Consultez ses sources et limites ci-dessous.",
        ),
      );
    });
  const navigation: { id: Tab; en: string; fr: string; icon: ReactNode }[] = [
    {
      id: "brief",
      en: "The brief",
      fr: "Le brief",
      icon: <Notebook size={21} />,
    },
    {
      id: "research",
      en: "Evidence",
      fr: "Sources",
      icon: <MagnifyingGlass size={21} />,
    },
    {
      id: "personas",
      en: "The audience",
      fr: "Le public",
      icon: <UsersThree size={21} />,
    },
    {
      id: "media",
      en: "Media plans",
      fr: "Plans média",
      icon: <Broadcast size={21} />,
    },
    { id: "page", en: "The page", fr: "La page", icon: <FileText size={21} /> },
    {
      id: "results",
      en: "Results",
      fr: "Résultats",
      icon: <ChartLineUp size={21} />,
    },
  ];
  const busyAll = !!busy || bootLoading || !boot || pageBusy;
  return (
    <Language.Provider value={lang}>
      <a className="skip-link" href="#main">
        {t("Skip to experiment", "Aller à l’expérience")}
      </a>
      <div className="app-shell">
        <aside className="rail">
          <a
            className="brand"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              if (!requests.current.pending && !pageBusy) setTab("brief");
            }}
            aria-label="Spill the Market"
          >
            <span className="brand-mark">
              <Flask size={28} weight="fill" />
            </span>
            <span>
              Spill the
              <br />
              <strong>Market</strong>
              <small>{t("LAUNCH NOTEBOOK", "CARNET DE LANCEMENT")}</small>
            </span>
          </a>
          <div className="rail-label">
            {t("YOUR EXPERIMENT", "VOTRE EXPÉRIENCE")}
          </div>
          <nav aria-label={t("Experiment workflow", "Étapes de l’expérience")}>
            {navigation.map((item, i) => (
              <button
                key={item.id}
                className={`nav-item ${tab === item.id ? "active" : ""}`}
                disabled={!!busy || bootLoading || pageBusy}
                onClick={() => setTab(item.id)}
                aria-current={tab === item.id ? "page" : undefined}
              >
                {item.icon}
                <span>{t(item.en, item.fr)}</span>
                <span className="nav-step">0{i + 1}</span>
              </button>
            ))}
          </nav>
          <div className="rail-bottom">
            <button
              className={`nav-item ${tab === "roadmap" ? "active" : ""}`}
              aria-label={t("What’s next", "La suite")}
              disabled={!!busy || bootLoading || pageBusy}
              onClick={() => setTab("roadmap")}
            >
              <Lightning size={21} />
              <span>{t("What’s next", "La suite")}</span>
            </button>
            <button
              className={`nav-item ${tab === "settings" ? "active" : ""}`}
              aria-label={t("Settings", "Réglages")}
              disabled={!!busy || bootLoading || pageBusy}
              onClick={() => setTab("settings")}
            >
              <GearSix size={21} />
              <span>{t("Settings", "Réglages")}</span>
            </button>
            <div className="local-status">
              <span className={boot ? "status-dot" : "status-dot offline"} />
              {boot
                ? t("Local workspace", "Espace local")
                : t("Connecting…", "Connexion…")}
              <small>v{boot?.version ?? "0.1.0"}</small>
            </div>
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <span className="workspace-label">
              {t(
                "Make your assumptions visible.",
                "Rendez vos hypothèses visibles.",
              )}
            </span>
            <div className="top-actions">
              <span className="simulation-label">
                <Flask size={15} />
                {t("Simulation only", "Simulation uniquement")}
              </span>
              <button
                className="language-button"
                disabled={!!busy || bootLoading || pageBusy}
                onClick={() => setLang(lang === "en" ? "fr" : "en")}
                aria-label={t("Switch to French", "Passer en anglais")}
              >
                <Globe size={17} />
                {lang === "en" ? "EN" : "FR"}
              </button>
            </div>
          </header>
          <main id="main" tabIndex={-1}>
            <fieldset
              className="operation-lock"
              disabled={!!busy || bootLoading || pageBusy}
            >
              {error && (
                <div className="error-banner" role="alert">
                  <WarningCircle size={22} />
                  <div>
                    <strong>
                      {t(
                        "The action could not finish.",
                        "L’action n’a pas abouti.",
                      )}
                    </strong>
                    <p>{error}</p>
                  </div>
                  {!boot && (
                    <button
                      className="button compact"
                      onClick={() => void loadBootstrap()}
                    >
                      {t("Reconnect", "Reconnecter")}
                    </button>
                  )}
                  <button
                    className="icon-button"
                    onClick={() => setError("")}
                    aria-label={t("Dismiss error", "Fermer l’erreur")}
                  >
                    <X size={18} />
                  </button>
                </div>
              )}
              {message && (
                <div className="toast" role="status">
                  <CheckCircle size={19} />
                  {message}
                </div>
              )}
              <div className="page-heading">
                <div>
                  <p className="page-kicker">
                    {t(
                      "A SMALL TEST. A CLEARER NEXT MOVE.",
                      "UN PETIT TEST. UNE SUITE PLUS CLAIRE.",
                    )}
                  </p>
                  <h1>
                    {tab === "brief"
                      ? t("Before you go all in.", "Avant de vous lancer.")
                      : tab === "research"
                        ? t(
                            "Keep the evidence close.",
                            "Gardez les preuves à portée.",
                          )
                        : tab === "personas"
                          ? t(
                              "People, with differences.",
                              "Des profils, des différences.",
                            )
                          : tab === "media"
                            ? t(
                                "Three ways to show up.",
                                "Trois façons d’émerger.",
                              )
                            : tab === "page"
                              ? t(
                                  "What happens after the click?",
                                  "Que se passe-t-il après le clic ?",
                                )
                              : tab === "results"
                                ? t(
                                    "Read the experiment.",
                                    "Lisez l’expérience.",
                                  )
                                : tab === "settings"
                                  ? t(
                                      "Your local workspace.",
                                      "Votre espace local.",
                                    )
                                  : t(
                                      "The next chapter.",
                                      "Le prochain chapitre.",
                                    )}
                  </h1>
                  <p className="page-description">
                    {tab === "brief"
                      ? t(
                          "Give your idea a dry run. Shape the audience, compare launch strategies, and see what your assumptions change.",
                          "Testez votre idée à blanc. Définissez le public, comparez les stratégies et voyez ce que vos hypothèses changent.",
                        )
                      : tab === "media"
                        ? t(
                            "Same product, three price and communication candidates. Every assumption is yours to edit.",
                            "Un produit, trois couples prix et communication. Chaque hypothèse est modifiable.",
                          )
                        : tab === "page"
                          ? t(
                              "Capture locally, inspect the visible evidence, then follow your personas through the page.",
                              "Capturez localement, examinez les éléments visibles, puis suivez vos personas dans la page.",
                            )
                          : tab === "results"
                            ? t(
                                "Virtual purchases, real arithmetic. These outcomes are conditional on your inputs.",
                                "Des achats virtuels, de vrais calculs. Ces résultats dépendent de vos paramètres.",
                              )
                            : tab === "research"
                              ? t(
                                  "Separate sourced observations, interpretations, and assumptions before you simulate.",
                                  "Séparez les observations sourcées, les interprétations et les hypothèses avant de simuler.",
                                )
                              : tab === "personas"
                                ? t(
                                    "A bounded sample makes your numerical population understandable. Each displayed profile is synthetic.",
                                    "Un échantillon limité rend la population numérique lisible. Chaque profil présenté est synthétique.",
                                  )
                                : ""}
                  </p>
                </div>
                {study && (
                  <span className="study-stamp">
                    <span>{t("EXPERIMENT", "EXPÉRIENCE")}</span>
                    {study.id.slice(0, 8)}
                  </span>
                )}
              </div>
              {tab === "brief" && (
                <div className="brief-layout">
                  <section className="worksheet">
                    <div className="sheet-header">
                      <h2>
                        {t(
                          "Start with the product",
                          "Commençons par le produit",
                        )}
                      </h2>
                      <span className="chip">
                        {t("Editable brief", "Brief modifiable")}
                      </span>
                    </div>
                    <div className="example-strip">
                      <span>
                        {t("Try a fictional example", "Exemple fictif")}
                      </span>
                      {boot?.examples.map((ex) => (
                        <button
                          key={ex.id}
                          onClick={() => selectExample(ex.id)}
                          className={
                            spec.product.name === ex.name
                              ? "example selected"
                              : "example"
                          }
                        >
                          <span>{ex.id === "game" ? "↗" : "↗"}</span>
                          {ex.name}
                          <small>
                            {ex.id === "game"
                              ? t("indie game", "jeu indépendant")
                              : t("creative software", "logiciel créatif")}
                          </small>
                        </button>
                      ))}
                      {bootLoading && (
                        <span
                          className="skeleton"
                          style={{ width: 170, height: 35 }}
                        />
                      )}
                    </div>
                    <BriefForm
                      spec={spec}
                      onChange={editSpec}
                      busy={busyAll}
                      llmConfigured={!!boot?.provider_status.llm}
                      onPrepare={() =>
                        void act("prepare", async (ticket) => {
                          await prepare(ticket);
                          notify(
                            t(
                              "Your audience and three media plans are ready.",
                              "Votre public et vos trois plans média sont prêts.",
                            ),
                          );
                        })
                      }
                      dirty={dirty}
                    />
                  </section>
                  <aside className="experiment-aside">
                    <div className="experiment-note">
                      <div className="note-top">
                        <Flask size={24} />
                        <span>{t("THE EXPERIMENT", "L’EXPÉRIENCE")}</span>
                      </div>
                      <h2>{spec.product.name}</h2>
                      <p>
                        {t(
                          "A launch you can rewind.",
                          "Un lancement que l’on peut rejouer.",
                        )}
                      </p>
                      <dl>
                        <div>
                          <dt>
                            {t("Virtual media budget", "Budget média virtuel")}
                          </dt>
                          <dd>
                            {money(
                              spec.media_budget_cents,
                              spec.product.currency,
                              lang,
                              true,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t("Population", "Population")}</dt>
                          <dd>{number(spec.audience.population, lang)}</dd>
                        </div>
                        <div>
                          <dt>{t("Simulation days", "Jours simulés")}</dt>
                          <dd>{number(spec.rounds, lang)}</dd>
                        </div>
                        <div>
                          <dt>{t("Real API cap", "Plafond API réel")}</dt>
                          <dd>
                            {money(spec.api_budget_usd * 100, "USD", lang)}
                          </dd>
                        </div>
                      </dl>
                      <div className="experiment-timeline">
                        {[
                          t("Gather evidence", "Rassembler les sources"),
                          t(
                            "Build a diverse audience",
                            "Former un public diversifié",
                          ),
                          t(
                            "Compare three strategies",
                            "Comparer trois stratégies",
                          ),
                          t(
                            "Follow virtual purchases",
                            "Suivre les achats virtuels",
                          ),
                        ].map((v, i) => (
                          <div key={v}>
                            <span>{i + 1}</span>
                            <p>{v}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                    <p className="aside-caption">
                      <Info size={17} />
                      {t(
                        "A thinking tool, not a sales forecast. Synthetic behaviour cannot establish real demand.",
                        "Un outil de réflexion, pas une prévision de ventes. Un comportement synthétique ne prouve pas la demande réelle.",
                      )}
                    </p>
                    {studies.length > 0 && (
                      <div className="history">
                        <h3>{t("Reopen a notebook", "Rouvrir un carnet")}</h3>
                        <label className="sr-only" htmlFor="history-select">
                          {t("Saved experiments", "Expériences enregistrées")}
                        </label>
                        <select
                          id="history-select"
                          value=""
                          onChange={(e) => openStudy(e.target.value)}
                          disabled={busyAll}
                        >
                          <option value="">
                            {t(
                              "Choose an experiment…",
                              "Choisir une expérience…",
                            )}
                          </option>
                          {studies.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.spec.product.name} ·{" "}
                              {new Date(s.created_at).toLocaleDateString(lang)}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </aside>
                </div>
              )}
              {tab === "research" && (
                <ResearchPanel
                  request={researchRequest}
                  setRequest={(next) => {
                    if (!requests.current.pending) setResearchRequest(next);
                  }}
                  report={study?.research}
                  onResearch={doResearch}
                  busy={busyAll}
                  cost={
                    cost?.studyId === study?.id ? (cost?.ledger ?? null) : null
                  }
                  cap={
                    study && !dirty
                      ? study.spec.api_budget_usd
                      : spec.api_budget_usd
                  }
                  boot={boot}
                  onBrief={() => setTab("brief")}
                  onApplyAges={(ages) => {
                    editSpec({
                      ...spec,
                      audience: {
                        ...spec.audience,
                        age_min: ages[0],
                        age_max: ages[1],
                        auto_age: false,
                      },
                    });
                    setTab("brief");
                    notify(
                      t(
                        "Suggested ages applied to the draft. Prepare it to confirm.",
                        "Âges suggérés appliqués au brouillon. Préparez-le pour confirmer.",
                      ),
                    );
                  }}
                />
              )}
              {tab === "personas" &&
                (study ? (
                  <AudiencePanel
                    personas={study.personas}
                    study={study}
                    onError={setError}
                  />
                ) : (
                  <Empty
                    title={t(
                      "Meet the audience after the brief.",
                      "Découvrez le public après le brief.",
                    )}
                    icon={<UsersThree size={30} />}
                  >
                    {t(
                      "Prepare your experiment to generate a bounded, diverse set of synthetic profiles.",
                      "Préparez l’expérience pour générer un ensemble limité et diversifié de profils synthétiques.",
                    )}
                    <button className="button" onClick={() => setTab("brief")}>
                      {t("Open the brief", "Ouvrir le brief")}
                      <ArrowRight />
                    </button>
                  </Empty>
                ))}
              {tab === "media" &&
                (study ? (
                  <>
                    <div className="study-toolbar">
                      <div>
                        <strong>{study.spec.product.name}</strong>
                        <span>
                          {number(study.spec.audience.population, lang)}{" "}
                          {t("people", "personnes")} · {study.spec.rounds}{" "}
                          {t("days", "jours")} · {t("seed", "graine")}{" "}
                          {study.spec.seed}
                        </span>
                      </div>
                      <div className="button-row">
                        <button
                          className="button secondary"
                          onClick={savePlans}
                          disabled={busyAll || !planDirty}
                        >
                          {busy === "save" ? (
                            <SpinnerGap className="spin" />
                          ) : (
                            <CheckCircle />
                          )}
                          {t("Save plans", "Enregistrer")}
                        </button>
                        <button
                          className="button"
                          onClick={startRun}
                          disabled={
                            busyAll || (!!run && activeStatus(run.status))
                          }
                        >
                          {busy === "run" ? (
                            <SpinnerGap className="spin" />
                          ) : (
                            <Play weight="fill" />
                          )}
                          {t("Run experiment", "Lancer l’expérience")}
                        </button>
                      </div>
                    </div>
                    {dirty && (
                      <Notice tone="warning">
                        {t(
                          "The brief has unsaved changes. These plans still use the prepared brief. Prepare again to generate plans for your changes.",
                          "Le brief a changé. Ces plans utilisent encore le brief préparé. Préparez-le à nouveau pour intégrer vos changements.",
                        )}{" "}
                        <button
                          className="text-button"
                          onClick={() => setTab("brief")}
                        >
                          {t("Review brief", "Revoir le brief")}
                        </button>
                      </Notice>
                    )}
                    <MediaEditor
                      plans={plans}
                      setPlans={(next) => {
                        if (!requests.current.pending) {
                          setPlans(next);
                          setPlanDirty(true);
                        }
                      }}
                      currency={study.spec.product.currency}
                      catalog={boot?.channels ?? []}
                      budget={study.spec.media_budget_cents}
                    />
                    <ChannelCatalogue
                      catalog={boot?.channels ?? []}
                      currency={study.spec.product.currency}
                    />
                  </>
                ) : (
                  <Empty
                    title={t(
                      "Give the plans a product to work with.",
                      "Donnez un produit aux plans média.",
                    )}
                    icon={<Broadcast size={30} />}
                  >
                    {t(
                      "Prepare the brief to get three editable price and communication candidates.",
                      "Préparez le brief pour obtenir trois propositions prix et communication modifiables.",
                    )}
                    <button className="button" onClick={() => setTab("brief")}>
                      {t("Open the brief", "Ouvrir le brief")}
                      <ArrowRight />
                    </button>
                  </Empty>
                ))}
              {tab === "page" && (
                <PageAnalysis
                  key={study?.id ?? "new"}
                  study={study}
                  lang={lang}
                  onOpenBrief={() => setTab("brief")}
                  onPendingChange={setPageBusy}
                />
              )}
              {tab === "results" && (
                <>
                  {run ? (
                    <>
                      <RunMonitor
                        run={run}
                        busy={busyAll}
                        onCancel={() => runAction("cancel")}
                        onResume={() => runAction("resume")}
                        onRefresh={refreshRun}
                      />
                      {run.report ? (
                        <Results report={run.report} runId={run.id} />
                      ) : (
                        !activeStatus(run.status) && (
                          <Empty
                            title={
                              run.status === "failed"
                                ? t(
                                    "This run stopped with an error.",
                                    "Cette exécution s’est arrêtée sur une erreur.",
                                  )
                                : t(
                                    "No completed report yet.",
                                    "Le rapport n’est pas encore terminé.",
                                  )
                            }
                          >
                            {run.error ??
                              t(
                                "Resume an interrupted run from its saved state, or review the media plans and start another.",
                                "Reprenez une exécution interrompue depuis son état sauvegardé, ou revoyez les plans média pour en lancer une nouvelle.",
                              )}
                          </Empty>
                        )
                      )}
                    </>
                  ) : (
                    <Empty
                      title={t(
                        "Your results start with a run.",
                        "Vos résultats commencent par une exécution.",
                      )}
                      icon={<ChartLineUp size={32} />}
                    >
                      {t(
                        "Prepare the brief, inspect the media plans, then run the experiment. No results are invented in this workspace.",
                        "Préparez le brief, examinez les plans média, puis lancez l’expérience. Aucun résultat n’est inventé dans cet espace.",
                      )}
                      <button
                        className="button"
                        onClick={() => setTab(study ? "media" : "brief")}
                      >
                        {study
                          ? t("Review media plans", "Voir les plans média")
                          : t("Open the brief", "Ouvrir le brief")}
                        <ArrowRight />
                      </button>
                    </Empty>
                  )}
                  {study && study.runs?.length > 0 && (
                    <div className="run-history">
                      <h3>{t("Saved runs", "Exécutions enregistrées")}</h3>
                      <div className="button-row">
                        {study.runs.map((r) => (
                          <button
                            key={r.id}
                            className="button secondary compact"
                            onClick={() => openRun(r.id)}
                          >
                            {r.id.slice(0, 8)} · {statusLabel(r.status, t)}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {tab === "settings" && (
                <Settings boot={boot} onRefresh={() => void loadBootstrap()} />
              )}
              {tab === "roadmap" && <Roadmap />}
            </fieldset>
          </main>
          <footer className="footer">
            <span>
              Spill the Market <span aria-hidden="true">↗</span>
            </span>
            <p>
              {t(
                "Local by default. Assumptions in the open.",
                "Local par défaut. Hypothèses au grand jour.",
              )}
            </p>
            <span>
              {t(
                "No campaigns or purchases are real.",
                "Aucune campagne ni aucun achat réel.",
              )}
            </span>
          </footer>
        </div>
      </div>
    </Language.Provider>
  );
}

function BriefForm({
  spec: s,
  onChange,
  busy,
  onPrepare,
  dirty,
  llmConfigured,
}: {
  spec: StudySpec;
  onChange: (s: StudySpec) => void;
  busy: boolean;
  onPrepare: () => void;
  dirty: boolean;
  llmConfigured: boolean;
}) {
  const t = useCopy(),
    lang = useContext(Language);
  const [advanced, setAdvanced] = useState(false);
  const p = (changes: Partial<StudySpec["product"]>) =>
      onChange({ ...s, product: { ...s.product, ...changes } }),
    a = (changes: Partial<StudySpec["audience"]>) =>
      onChange({ ...s, audience: { ...s.audience, ...changes } });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onPrepare();
  };
  return (
    <form onSubmit={submit} className="brief-form">
      <fieldset disabled={busy}>
        <legend className="sr-only">
          {t(
            "Product and experiment settings",
            "Paramètres du produit et de l’expérience",
          )}
        </legend>
        <div className="form-grid">
          <Field label={t("Product name", "Nom du produit")}>
            <input
              required
              minLength={2}
              maxLength={120}
              value={s.product.name}
              onChange={(e) => p({ name: e.target.value })}
            />
          </Field>
          <Field label={t("Category", "Catégorie")}>
            <select
              value={s.product.category}
              onChange={(e) => p({ category: e.target.value as Category })}
            >
              {(
                ["game", "software", "physical", "service", "other"] as const
              ).map((v, i) => (
                <option key={v} value={v}>
                  {
                    [
                      t("Game", "Jeu"),
                      t("Software", "Logiciel"),
                      t("Physical product", "Produit physique"),
                      t("Service", "Service"),
                      t("Other", "Autre"),
                    ][i]
                  }
                </option>
              ))}
            </select>
          </Field>
          <Field
            className="span-2"
            label={t(
              "What does it do, and who is it for?",
              "Que fait-il, et pour qui ?",
            )}
            hint={t(
              "Describe the benefit, the buying situation, and any requirements.",
              "Décrivez le bénéfice, la situation d’achat et les prérequis.",
            )}
          >
            <textarea
              required
              minLength={8}
              maxLength={12000}
              rows={4}
              value={s.product.description}
              onChange={(e) => p({ description: e.target.value })}
            />
          </Field>
          <NumberField
            label={
              t("Selling price", "Prix de vente") + ` (${s.product.currency})`
            }
            value={s.product.unit_price_cents / 100}
            onChange={(v) => p({ unit_price_cents: Math.round(v * 100) })}
            min={0.01}
            max={1000000}
            step={0.01}
          />
          <NumberField
            label={
              t("Variable cost / purchase", "Coût variable / achat") +
              ` (${s.product.currency})`
            }
            value={s.product.variable_cost_cents / 100}
            onChange={(v) => p({ variable_cost_cents: Math.round(v * 100) })}
            max={1000000}
            step={0.01}
          />
        </div>
        <div className="form-section-heading">
          <span>02</span>
          <h3>{t("Define the experiment", "Définissez l’expérience")}</h3>
        </div>
        <div className="form-grid">
          <NumberField
            label={t("Numerical population", "Population numérique")}
            value={s.audience.population}
            onChange={(v) =>
              a({
                population: v,
                representatives: Math.min(v, s.audience.representatives),
              })
            }
            min={30}
            max={100000}
            hint={t(
              "30–100,000 individual states. Profiles below are only representatives.",
              "30 à 100 000 états individuels. Les profils sont des représentants.",
            )}
          />
          <NumberField
            label={
              t("Virtual media budget", "Budget média virtuel") +
              ` (${s.product.currency})`
            }
            value={s.media_budget_cents / 100}
            onChange={(v) =>
              onChange({ ...s, media_budget_cents: Math.round(v * 100) })
            }
            max={100000000}
            step={0.01}
            hint={t(
              "Total per candidate. No advertising money is spent.",
              "Total par proposition. Aucune dépense publicitaire réelle.",
            )}
          />
          <div className="field">
            <span>{t("Strict age range", "Tranche d’âge stricte")}</span>
            <div className="age-range">
              <label>
                <span className="sr-only">
                  {t("Minimum age", "Âge minimum")}
                </span>
                <input
                  required
                  type="number"
                  min={18}
                  max={s.audience.age_max}
                  value={s.audience.age_min}
                  onChange={(e) =>
                    a({ age_min: Number(e.target.value), auto_age: false })
                  }
                />
              </label>
              <span>–</span>
              <label>
                <span className="sr-only">
                  {t("Maximum age", "Âge maximum")}
                </span>
                <input
                  required
                  type="number"
                  min={s.audience.age_min}
                  max={100}
                  value={s.audience.age_max}
                  onChange={(e) =>
                    a({ age_max: Number(e.target.value), auto_age: false })
                  }
                />
              </label>
              <span>{t("years", "ans")}</span>
            </div>
            <small>
              {t(
                "Adults only. No inferred age change without your confirmation.",
                "Adultes uniquement. Aucun changement d’âge suggéré sans confirmation.",
              )}
            </small>
          </div>
          <NumberField
            label={t("Simulation days", "Jours simulés")}
            value={s.rounds}
            onChange={(v) => onChange({ ...s, rounds: v })}
            min={1}
            max={90}
            hint={t(
              "1 day = 1 round. Up to 90 days.",
              "1 jour = 1 tour. Jusqu’à 90 jours.",
            )}
          />
          <Field label={t("Region", "Région")}>
            <input
              required
              maxLength={100}
              value={s.audience.region}
              onChange={(e) => a({ region: e.target.value })}
            />
          </Field>
          <NumberField
            label={t("Representative profiles", "Profils représentatifs")}
            value={s.audience.representatives}
            onChange={(v) => a({ representatives: v })}
            min={1}
            max={Math.min(200, s.audience.population)}
            hint={t(
              "Bounded, synthetic profiles for inspection.",
              "Profils synthétiques limités, pour inspection.",
            )}
          />
        </div>
        <button
          type="button"
          className="disclosure"
          aria-expanded={advanced}
          onClick={() => setAdvanced(!advanced)}
        >
          {advanced ? <CaretUp /> : <CaretDown />}
          {t(
            "Reproducibility, cost cap & advanced inputs",
            "Reproductibilité, plafond réel et réglages avancés",
          )}
        </button>
        {advanced && (
          <div className="advanced-fields form-grid">
            <NumberField
              label={t("Random seed", "Graine aléatoire")}
              value={s.seed}
              onChange={(v) => onChange({ ...s, seed: v })}
              max={2147483647}
            />
            <Field label={t("Currency", "Devise")}>
              <select
                value={s.product.currency}
                onChange={(e) => p({ currency: e.target.value })}
              >
                {["EUR", "USD", "GBP", "CAD", "CHF"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </Field>
            <NumberField
              label={t("Exploration repetitions", "Répétitions d’exploration")}
              value={s.exploration_repetitions}
              onChange={(v) => onChange({ ...s, exploration_repetitions: v })}
              min={1}
              max={50}
            />
            <NumberField
              label={t("Validation repetitions", "Répétitions de validation")}
              value={s.validation_repetitions}
              onChange={(v) => onChange({ ...s, validation_repetitions: v })}
              min={1}
              max={50}
            />
            <NumberField
              label={t("Real API cost cap (USD)", "Plafond API réel (USD)")}
              value={s.api_budget_usd}
              onChange={(v) => onChange({ ...s, api_budget_usd: v })}
              max={10000}
              step={0.01}
              hint={t(
                "$0 keeps paid online calls unavailable. Separate from virtual media.",
                "0 $ empêche les appels payants. Distinct du budget média virtuel.",
              )}
            />
            <NumberField
              label={t("Maximum API calls", "Nombre maximal d’appels API")}
              value={s.api_max_calls}
              onChange={(v) => onChange({ ...s, api_max_calls: v })}
              min={1}
              max={10000}
            />
            <label className="checkbox span-2">
              <input
                type="checkbox"
                checked={s.use_representative_llm ?? false}
                disabled={
                  (!llmConfigured || s.api_budget_usd <= 0) &&
                  !s.use_representative_llm
                }
                onChange={(e) =>
                  onChange({ ...s, use_representative_llm: e.target.checked })
                }
              />
              <span>
                {t(
                  "Enrich representative reactions with AI",
                  "Enrichir les réactions représentatives par IA",
                )}
                <small>
                  {t(
                    "Optional paid qualitative comments for bounded representatives. Requires a configured model and a positive real API cap. Offline demos do not call AI.",
                    "Commentaires qualitatifs payants facultatifs pour les représentants limités. Modèle configuré et plafond API positif requis. Les démos hors ligne n’appellent pas d’IA.",
                  )}
                </small>
              </span>
            </label>
            <NumberField
              label={t(
                "Age behaviour prior",
                "A priori comportemental lié à l’âge",
              )}
              value={s.audience.age_behavior_weight ?? 0.15}
              onChange={(v) => a({ age_behavior_weight: v })}
              max={0.5}
              step={0.05}
              hint={t(
                "Weak, unvalidated assumption. 0 = neutral. Diversity within each age remains.",
                "Hypothèse faible, non validée. 0 = neutre. La diversité dans chaque âge est conservée.",
              )}
            />
            <NumberField
              label={t("Fatigue multiplier", "Multiplicateur de fatigue")}
              value={s.fatigue_multiplier}
              onChange={(v) => onChange({ ...s, fatigue_multiplier: v })}
              max={3}
              step={0.1}
            />
            <NumberField
              label={t(
                "Price elasticity multiplier",
                "Multiplicateur d’élasticité prix",
              )}
              value={s.price_elasticity}
              onChange={(v) => onChange({ ...s, price_elasticity: v })}
              min={0.1}
              max={3}
              step={0.1}
            />
            <Field
              label={t("Stock limit (optional)", "Stock maximal (facultatif)")}
              hint={t(
                "Leave blank for no stock cap.",
                "Laissez vide pour aucun plafond de stock.",
              )}
            >
              <input
                type="number"
                min={0}
                step={1}
                value={s.product.stock ?? ""}
                onChange={(e) =>
                  p({
                    stock:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </Field>
            <Field
              label={t("Audience languages", "Langues du public")}
              hint={t(
                "Comma-separated language codes.",
                "Codes de langue séparés par des virgules.",
              )}
            >
              <input
                defaultValue={s.audience.languages.join(", ")}
                key={s.product.name + "languages"}
                onBlur={(e) =>
                  a({
                    languages: e.target.value
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean)
                      .slice(0, 10),
                  })
                }
              />
            </Field>
            <Field
              className="span-2"
              label={t("Product keywords", "Mots-clés du produit")}
            >
              <input
                defaultValue={s.product.keywords.join(", ")}
                key={s.product.name + "keywords"}
                onBlur={(e) =>
                  p({
                    keywords: e.target.value
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean)
                      .slice(0, 30),
                  })
                }
              />
            </Field>
            <Field
              className="span-2"
              label={t(
                "Prerequisites (one per line)",
                "Prérequis (un par ligne)",
              )}
            >
              <textarea
                rows={2}
                defaultValue={s.product.prerequisites.join("\n")}
                key={s.product.name + "prerequisites"}
                onBlur={(e) =>
                  p({
                    prerequisites: e.target.value
                      .split("\n")
                      .map((x) => x.trim())
                      .filter(Boolean)
                      .slice(0, 20),
                  })
                }
              />
            </Field>
          </div>
        )}
      </fieldset>
      <div className="form-submit">
        <p>
          {dirty
            ? t(
                "Preparing saves a new experiment with these changes.",
                "La préparation crée une nouvelle expérience avec ces changements.",
              )
            : t(
                "Offline preparation. No real API spending.",
                "Préparation hors ligne. Aucun coût API réel.",
              )}{" "}
          <span>
            {t("Seed", "Graine")} {number(s.seed, lang)}
          </span>
        </p>
        <button className="button" type="submit" disabled={busy}>
          {busy ? <SpinnerGap className="spin" /> : <Flask />}
          {t("Prepare experiment", "Préparer l’expérience")}
          <ArrowRight size={18} />
        </button>
      </div>
    </form>
  );
}

function ResearchPanel({
  request: r,
  setRequest,
  report,
  onResearch,
  busy,
  cost,
  cap,
  boot,
  onBrief,
  onApplyAges,
}: {
  request: ResearchRequest;
  setRequest: (r: ResearchRequest) => void;
  report?: TrendReport;
  onResearch: () => void;
  busy: boolean;
  cost: Record<string, unknown> | null;
  cap: number;
  boot: Bootstrap | null;
  onBrief: () => void;
  onApplyAges: (ages: number[]) => void;
}) {
  const t = useCopy(),
    lang = useContext(Language),
    [fileError, setFileError] = useState("");
  const update = (v: Partial<ResearchRequest>) => setRequest({ ...r, ...v });
  const addFiles = async (files: FileList | null) => {
    if (!files) return;
    setFileError("");
    try {
      const docs = await Promise.all(
        Array.from(files).map(async (f) => {
          if (f.size > 800000)
            throw new Error(
              t(
                "Document too large. Maximum: 200,000 text characters per document.",
                "Document trop volumineux. Maximum : 200 000 caractères par document.",
              ),
            );
          const text = await f.text();
          if (text.length > 200000 || !text.trim())
            throw new Error(
              t(
                "Use a non-empty plain text document under 200,000 characters.",
                "Utilisez un document texte non vide de moins de 200 000 caractères.",
              ),
            );
          return { name: f.name.slice(0, 200), text };
        }),
      );
      if (r.documents.length + docs.length > 20)
        throw new Error(t("Maximum 20 documents.", "20 documents au maximum."));
      update({ documents: [...r.documents, ...docs] });
    } catch (e) {
      setFileError(plain(e instanceof Error ? e.message : e));
    }
  };
  return (
    <div className="research-layout">
      <section className="worksheet">
        <div className="sheet-header">
          <h2>{t("Choose your evidence", "Choisissez vos sources")}</h2>
          <span className="chip">
            {t("Explicit sources", "Sources explicites")}
          </span>
        </div>
        <form
          className="padded"
          onSubmit={(e) => {
            e.preventDefault();
            onResearch();
          }}
        >
          <fieldset disabled={busy}>
            <div
              className="mode-switch"
              role="group"
              aria-label={t("Research mode", "Mode de recherche")}
            >
              {(["demo", "offline", "urls", "live"] as const).map((mode, i) => (
                <button
                  type="button"
                  key={mode}
                  onClick={() =>
                    update({
                      mode,
                      use_llm: mode === "live" ? r.use_llm : false,
                      use_firecrawl: mode === "live" ? r.use_firecrawl : false,
                    })
                  }
                  className={r.mode === mode ? "selected" : ""}
                >
                  {
                    [
                      t("Demo", "Démo"),
                      t("Documents", "Documents"),
                      t("URL / RSS", "URL / RSS"),
                      t("Live search", "Recherche web"),
                    ][i]
                  }
                </button>
              ))}
            </div>
            <p className="mode-description">
              {r.mode === "demo"
                ? t(
                    "Fictional evidence to explore the workflow. No network calls.",
                    "Sources fictives pour découvrir le parcours. Aucun appel réseau.",
                  )
                : r.mode === "offline"
                  ? t(
                      "Import your own text. Local analysis uses no network.",
                      "Importez votre texte. L’analyse locale n’utilise pas le réseau.",
                    )
                  : r.mode === "urls"
                    ? t(
                        "Fetch only the public URLs you select. Each source retains its provenance.",
                        "Consultez uniquement les URL publiques choisies. La provenance est conservée.",
                      )
                    : t(
                        "Run a paid, provider-backed search. Your real cost cap applies before every call.",
                        "Lancez une recherche via un fournisseur payant. Votre plafond réel s’applique avant chaque appel.",
                      )}
            </p>
            <Field label={t("Research topic", "Sujet de recherche")}>
              <input
                maxLength={500}
                value={r.topic}
                placeholder={t(
                  "The market question you want to explore",
                  "La question de marché à explorer",
                )}
                onChange={(e) => update({ topic: e.target.value })}
              />
            </Field>
            <div className="form-grid research-parameters">
              <Field label={t("Language", "Langue")}>
                <select
                  value={r.language}
                  onChange={(e) => update({ language: e.target.value })}
                >
                  <option value="en">English</option>
                  <option value="fr">Français</option>
                </select>
              </Field>
              <NumberField
                label={t("Look-back window (days)", "Période examinée (jours)")}
                value={r.days}
                onChange={(v) => update({ days: v })}
                min={1}
                max={730}
              />
              <Field label={t("Research region", "Région étudiée")}>
                <input
                  maxLength={100}
                  value={r.region}
                  onChange={(e) => update({ region: e.target.value })}
                />
              </Field>
              <NumberField
                label={t("Maximum sources", "Nombre maximal de sources")}
                value={r.max_sources}
                onChange={(v) => update({ max_sources: v })}
                min={1}
                max={30}
              />
            </div>
            {r.mode === "urls" && (
              <Field
                label={t(
                  "Public URL or RSS feeds, one per line",
                  "URL publiques ou flux RSS, un par ligne",
                )}
                hint={t(
                  "Up to 20 URLs. Local and private network addresses are blocked.",
                  "20 URL au maximum. Les adresses locales et privées sont bloquées.",
                )}
              >
                <textarea
                  rows={4}
                  defaultValue={r.urls.join("\n")}
                  key="urls"
                  onBlur={(e) =>
                    update({
                      urls: e.target.value
                        .split("\n")
                        .map((x) => x.trim())
                        .filter(Boolean)
                        .slice(0, 20),
                    })
                  }
                  placeholder="https://example.org/research"
                />
              </Field>
            )}
            {r.mode === "offline" && (
              <>
                <Field
                  label={t(
                    "Import plain text / Markdown / CSV",
                    "Importer du texte / Markdown / CSV",
                  )}
                >
                  <input
                    type="file"
                    accept=".txt,.md,.csv,.json,text/plain,text/markdown,text/csv,application/json"
                    multiple
                    onChange={(e) => void addFiles(e.target.files)}
                  />
                </Field>
                {fileError && (
                  <p className="inline-error" role="alert">
                    {fileError}
                  </p>
                )}
                <div className="document-list">
                  {r.documents.map((doc, i) => (
                    <div key={`${doc.name}-${i}`}>
                      <FileText />
                      <span>
                        {doc.name}
                        <small>
                          {number(doc.text.length, lang)}{" "}
                          {t("characters", "caractères")}
                        </small>
                      </span>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={t(
                          `Remove ${doc.name}`,
                          `Retirer ${doc.name}`,
                        )}
                        onClick={() =>
                          update({
                            documents: r.documents.filter((_, j) => j !== i),
                          })
                        }
                      >
                        <Trash />
                      </button>
                    </div>
                  ))}
                </div>
                <Field
                  label={t("Or paste a document", "Ou collez un document")}
                >
                  <textarea
                    rows={5}
                    maxLength={200000}
                    placeholder={t(
                      "Paste your notes, interview transcript, or research extract…",
                      "Collez vos notes, un entretien ou un extrait de recherche…",
                    )}
                    onBlur={(e) => {
                      const text = e.target.value.trim();
                      if (text) {
                        update({
                          documents: [
                            ...r.documents.filter(
                              (d) => d.name !== "Pasted notes",
                            ),
                            { name: "Pasted notes", text },
                          ],
                        });
                        e.target.value = "";
                      }
                    }}
                  />
                </Field>
              </>
            )}
            {r.mode === "live" && (
              <div className="online-consent">
                <p>
                  <strong>
                    {t("Real API cap", "Plafond API réel")}:{" "}
                    {money(cap * 100, "USD", lang)}
                  </strong>{" "}
                  <button
                    className="text-button"
                    type="button"
                    onClick={onBrief}
                  >
                    {t("Edit in the brief", "Modifier dans le brief")}
                  </button>
                </p>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={r.use_llm}
                    disabled={!boot?.provider_status.llm}
                    onChange={(e) => update({ use_llm: e.target.checked })}
                  />
                  {t(
                    "Use configured semantic analysis",
                    "Utiliser l’analyse sémantique configurée",
                  )}
                  {!boot?.provider_status.llm && (
                    <small>{t("Not configured", "Non configurée")}</small>
                  )}
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={r.use_firecrawl}
                    disabled={!boot?.provider_status.firecrawl}
                    onChange={(e) =>
                      update({ use_firecrawl: e.target.checked })
                    }
                  />
                  {t(
                    "Use configured Firecrawl extraction",
                    "Utiliser l’extraction Firecrawl configurée",
                  )}
                  {!boot?.provider_status.firecrawl && (
                    <small>{t("Not configured", "Non configurée")}</small>
                  )}
                </label>
                <p className="muted small">
                  {t(
                    "The button below explicitly authorizes this research within the saved cap. Unknown charges remain reserved after an interruption.",
                    "Le bouton ci-dessous autorise explicitement cette recherche dans le plafond enregistré. Après une interruption, les coûts incertains restent réservés.",
                  )}
                </p>
              </div>
            )}
          </fieldset>
          <div className="research-submit">
            <button
              className="button"
              disabled={
                busy ||
                (r.mode === "offline" && r.documents.length === 0) ||
                (r.mode === "live" && cap <= 0)
              }
              type="submit"
            >
              {busy ? <SpinnerGap className="spin" /> : <MagnifyingGlass />}
              {r.mode === "live"
                ? t(
                    "Run selected online research",
                    "Lancer la recherche en ligne choisie",
                  )
                : t(
                    "Analyse selected evidence",
                    "Analyser les sources choisies",
                  )}
            </button>
          </div>
        </form>
      </section>
      <aside className="research-note">
        <h3>
          {t(
            "A source is not a conclusion.",
            "Une source n’est pas une conclusion.",
          )}
        </h3>
        <p>
          {t(
            "Every finding keeps its source IDs and a status. Inference and synthetic assumptions stay visible.",
            "Chaque constat conserve les identifiants de ses sources et un statut. Déductions et hypothèses synthétiques restent visibles.",
          )}
        </p>
        <div className="status-key">
          <span className="chip observed">{t("Observed", "Observé")}</span>
          <span className="chip inferred">{t("Inferred", "Déduit")}</span>
          <span className="chip assumption">
            {t("Assumption", "Hypothèse")}
          </span>
        </div>
        {cost && (
          <details className="cost-details">
            <summary>
              {t("Research cost ledger", "Registre des coûts de recherche")}
            </summary>
            <pre>{plain(cost)}</pre>
          </details>
        )}
      </aside>
      {report && <EvidenceReport report={report} onApplyAges={onApplyAges} />}
    </div>
  );
}

function EvidenceReport({
  report: r,
  onApplyAges,
}: {
  report: TrendReport;
  onApplyAges: (v: number[]) => void;
}) {
  const t = useCopy(),
    lang = useContext(Language);
  const ageSuggestion = r.coverage.age_recommendation as
    | {
        range?: number[];
        status?: string;
        source_ids?: string[];
        reason?: string;
      }
    | undefined;
  const suggestedAges = r.recommended_age_range ?? ageSuggestion?.range;
  const findingGroups: {
    key: "trends" | "pain_points" | "segments" | "jargon";
    label: string;
  }[] = [
    { key: "trends", label: t("Trends", "Tendances") },
    { key: "pain_points", label: t("Pain points", "Difficultés") },
    { key: "segments", label: t("Segments", "Segments") },
    { key: "jargon", label: t("Jargon", "Vocabulaire") },
  ];
  const showFinding = (f: Finding, i: number) => (
    <li key={i}>
      <div>
        <span className={`chip ${f.status}`}>
          {f.status === "observed"
            ? t("Observed", "Observé")
            : f.status === "inferred"
              ? t("Inferred", "Déduit")
              : t("Assumption", "Hypothèse")}
        </span>
        <span className="small muted">
          {t("Confidence", "Confiance")} {percent(f.confidence, lang)}
        </span>
      </div>
      <p>{f.text}</p>
      <div className="source-references">
        {f.source_ids.map((id) => (
          <a key={id} href={`#source-${id}`}>
            {id}
          </a>
        ))}
      </div>
    </li>
  );
  return (
    <section className="evidence-output">
      <div className="section-heading">
        <div>
          <h2>{t("Evidence notebook", "Carnet de sources")}</h2>
          <p>
            {r.topic} · {r.mode} · {new Date(r.created_at).toLocaleString(lang)}
          </p>
        </div>
        <span className="chip">
          {r.sources.length} {t("sources", "sources")}
        </span>
      </div>
      {r.mode === "demo" && (
        <Notice tone="warning">
          {t(
            "Demonstration: all sources and market claims below are fictional. They do not establish real demand.",
            "Démonstration : les sources et affirmations de marché ci-dessous sont fictives. Elles ne prouvent aucune demande réelle.",
          )}
        </Notice>
      )}
      {r.limitations.length > 0 && (
        <details className="limitations" open>
          <summary>
            {t("Coverage & limitations", "Couverture et limites")}
          </summary>
          <ul>
            {r.limitations.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
          <details>
            <summary>{t("Coverage details", "Détails de couverture")}</summary>
            <pre>{plain(r.coverage)}</pre>
          </details>
        </details>
      )}
      {suggestedAges && suggestedAges.length === 2 && (
        <Notice>
          {t("Suggested age range", "Tranche d’âge suggérée")}:{" "}
          {suggestedAges.join("–")}.{" "}
          <span className={`chip ${ageSuggestion?.status ?? "assumption"}`}>
            {ageSuggestion?.status === "inferred"
              ? t(
                  "Inferred · confirm relevance",
                  "Déduit · pertinence à confirmer",
                )
              : t("Unvalidated hypothesis", "Hypothèse non validée")}
          </span>{" "}
          {ageSuggestion?.reason && <p>{ageSuggestion.reason}</p>}
          {ageSuggestion?.source_ids?.map((id) => (
            <a key={id} href={`#source-${id}`}>
              {id}
            </a>
          ))}{" "}
          <button
            className="text-button"
            onClick={() => onApplyAges(suggestedAges)}
          >
            {t(
              "Apply to draft for review",
              "Appliquer au brouillon pour vérification",
            )}
          </button>
        </Notice>
      )}
      <div className="findings-grid">
        {findingGroups.map((g) => (
          <section key={g.key}>
            <h3>{g.label}</h3>
            {r[g.key].length ? (
              <ul className="finding-list">{r[g.key].map(showFinding)}</ul>
            ) : (
              <p className="muted">
                {t(
                  "No supported findings in this category.",
                  "Aucun constat étayé dans cette catégorie.",
                )}
              </p>
            )}
          </section>
        ))}
      </div>
      <h3 className="source-heading">
        {t(
          "Provenance & source extracts",
          "Provenance et extraits des sources",
        )}
      </h3>
      <div className="source-list">
        {r.sources.map((source) => (
          <details key={source.id} id={`source-${source.id}`}>
            <summary>
              <span className="source-id">{source.id}</span>
              <strong>{source.title}</strong>
              <span className="chip">
                {source.kind === "demo"
                  ? t("Synthetic", "Synthétique")
                  : source.kind === "import"
                    ? t("Imported", "Importé")
                    : source.kind}
              </span>
            </summary>
            <div className="source-detail">
              {source.url &&
                (source.kind !== "demo" && safeURL(source.url) ? (
                  <a
                    href={safeURL(source.url)!}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {source.url}
                    <ArrowSquareOut size={14} />
                  </a>
                ) : (
                  <p className="muted">
                    {source.url} · {t("synthetic URL", "URL synthétique")}
                  </p>
                ))}
              <dl className="inline-meta">
                <div>
                  <dt>{t("Retrieved", "Consulté")}</dt>
                  <dd>{new Date(source.retrieved_at).toLocaleString(lang)}</dd>
                </div>
                <div>
                  <dt>{t("Published", "Publié")}</dt>
                  <dd>
                    {source.published_at
                      ? new Date(source.published_at).toLocaleString(lang)
                      : t("Not supplied", "Non fourni")}
                  </dd>
                </div>
              </dl>
              <pre className="source-text">{source.content}</pre>
              {source.content_hash && (
                <p className="hash">SHA-256 {source.content_hash}</p>
              )}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function AudiencePanel({
  personas,
  study,
  onError,
}: {
  personas: Persona[];
  study: Study;
  onError: (v: string) => void;
}) {
  const t = useCopy(),
    lang = useContext(Language),
    [query, setQuery] = useState(""),
    [selected, setSelected] = useState(personas[0]?.id ?? ""),
    [memoryQuery, setMemoryQuery] = useState(""),
    [memory, setMemory] = useState<unknown>(null),
    [searching, setSearching] = useState(false);
  const filtered = personas.filter((p) =>
    `${p.name} ${p.profession} ${p.segment} ${p.age}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const person = personas.find((p) => p.id === selected) ?? personas[0];
  const searchMemory = async (e: FormEvent) => {
    e.preventDefault();
    setSearching(true);
    try {
      setMemory(
        await api(
          `/studies/${study.id}/memory?q=${encodeURIComponent(memoryQuery)}`,
        ),
      );
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setSearching(false);
    }
  };
  return (
    <>
      <Notice>
        {number(personas.length, lang)}{" "}
        {t("displayed representatives for", "représentants affichés pour")}{" "}
        {number(study.spec.audience.population, lang)}{" "}
        {t(
          "individual numerical states. These are fictional profiles, not surveyed customers.",
          "états numériques individuels. Ces profils sont fictifs, pas des clients interrogés.",
        )}{" "}
        {t("Strict ages", "Âges stricts")}: {study.spec.audience.age_min}–
        {study.spec.audience.age_max}.
      </Notice>
      <div className="audience-layout">
        <section className="persona-list worksheet">
          <div className="sheet-header">
            <h2>{t("Representative profiles", "Profils représentatifs")}</h2>
            <span>{personas.length}</span>
          </div>
          <div className="search-field">
            <MagnifyingGlass size={18} />
            <input
              aria-label={t("Filter profiles", "Filtrer les profils")}
              type="search"
              placeholder={t(
                "Name, work, segment, age…",
                "Nom, métier, segment, âge…",
              )}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="profile-buttons">
            {filtered.map((p, i) => (
              <button
                key={p.id}
                className={
                  person?.id === p.id ? "profile-row selected" : "profile-row"
                }
                onClick={() => setSelected(p.id)}
              >
                <span className={`avatar tone-${i % 4}`}>
                  {p.name
                    .split(" ")
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <span>
                  <strong>{p.name}</strong>
                  <small>{p.profession}</small>
                </span>
                <span className="profile-age">
                  {p.age}
                  <small>{p.language.toUpperCase()}</small>
                </span>
              </button>
            ))}
            {!filtered.length && (
              <p className="padded muted">
                {t(
                  "No profiles match. Try another search.",
                  "Aucun profil correspondant. Essayez une autre recherche.",
                )}
              </p>
            )}
          </div>
        </section>
        {person && (
          <section className="persona-detail worksheet">
            <div className="profile-heading">
              <span className="avatar large">
                {person.name
                  .split(" ")
                  .map((n) => n[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <div>
                <span className="chip">
                  {t("Synthetic representative", "Représentant synthétique")}
                </span>
                <h2>{person.name}</h2>
                <p>
                  {person.profession} · {person.age} {t("years", "ans")} ·{" "}
                  {person.language.toUpperCase()}
                </p>
              </div>
            </div>
            <dl className="profile-facts">
              <div>
                <dt>{t("Available budget", "Budget disponible")}</dt>
                <dd>
                  {money(
                    person.budget_cents,
                    study.spec.product.currency,
                    lang,
                  )}
                </dd>
              </div>
              <div>
                <dt>{t("Segment", "Segment")}</dt>
                <dd>{person.segment}</dd>
              </div>
              <div>
                <dt>{t("Time zone", "Fuseau horaire")}</dt>
                <dd>{person.timezone}</dd>
              </div>
            </dl>
            <h3>{t("Individual assumptions", "Hypothèses individuelles")}</h3>
            <div className="trait-list">
              {[
                {
                  label: t("Need fit", "Adéquation au besoin"),
                  value: person.need_fit,
                },
                { label: t("Trust", "Confiance"), value: person.trust },
                {
                  label: t("Price sensitivity", "Sensibilité au prix"),
                  value: person.price_sensitivity,
                },
                {
                  label: t("Social sensitivity", "Sensibilité sociale"),
                  value: person.social_sensitivity,
                },
                {
                  label: t("Fatigue tolerance", "Tolérance à la fatigue"),
                  value: person.fatigue_tolerance,
                },
              ].map((trait) => (
                <div key={trait.label}>
                  <span>{trait.label}</span>
                  <meter min={0} max={1} value={trait.value}>
                    {percent(trait.value, lang)}
                  </meter>
                  <strong>{percent(trait.value, lang)}</strong>
                </div>
              ))}
            </div>
            <h3>{t("Channel affinities", "Affinités avec les canaux")}</h3>
            <div className="channel-affinities">
              {Object.entries(person.channels)
                .sort((a, b) => b[1] - a[1])
                .map(([ch, v]) => (
                  <span className="chip" key={ch}>
                    {channelNames[ch] ?? ch} <strong>{percent(v, lang)}</strong>
                  </span>
                ))}
            </div>
            <h3>{t("Beliefs & provenance", "Croyances et provenance")}</h3>
            {person.beliefs.length ? (
              <div className="beliefs">
                {person.beliefs.map((b, i) => (
                  <details key={i}>
                    <summary>
                      {String(
                        b.text ??
                          b.belief ??
                          `${t("Belief", "Croyance")} ${i + 1}`,
                      )}
                    </summary>
                    <pre>{plain(b)}</pre>
                  </details>
                ))}
              </div>
            ) : (
              <p className="muted">
                {t(
                  "No stored beliefs for this representative.",
                  "Aucune croyance enregistrée pour ce représentant.",
                )}
              </p>
            )}
          </section>
        )}
      </div>
      <section className="memory-search worksheet">
        <div className="sheet-header">
          <h2>
            {t(
              "Search this experiment’s memory",
              "Rechercher dans la mémoire de cette expérience",
            )}
          </h2>
          <span className="chip">
            {t("Study-isolated", "Isolée par expérience")}
          </span>
        </div>
        <form className="padded search-row" onSubmit={searchMemory}>
          <Field label={t("Memory query", "Requête mémoire")}>
            <input
              type="search"
              required
              minLength={1}
              value={memoryQuery}
              onChange={(e) => setMemoryQuery(e.target.value)}
              placeholder={t(
                "Source, concern, product…",
                "Source, question, produit…",
              )}
            />
          </Field>
          <button className="button secondary" disabled={searching}>
            {searching ? <SpinnerGap className="spin" /> : <MagnifyingGlass />}
            {t("Search memory", "Rechercher")}
          </button>
        </form>
        {memory !== null && (
          <div className="memory-results">
            <pre>{plain(memory)}</pre>
          </div>
        )}
      </section>
    </>
  );
}

function MediaEditor({
  plans,
  setPlans,
  currency,
  budget,
  catalog,
}: {
  plans: MediaPlan[];
  setPlans: (p: MediaPlan[]) => void;
  currency: string;
  budget: number;
  catalog: Record<string, unknown>[];
}) {
  const t = useCopy(),
    lang = useContext(Language);
  const [open, setOpen] = useState(plans[0]?.id ?? "");
  const [hoursError, setHoursError] = useState("");
  const formats = (channel: string) => {
    const values = catalog.find((c) => c.channel === channel)?.formats;
    return Array.isArray(values) ? values.map(String) : ["feed"];
  };
  const editPlan = (id: string, v: Partial<MediaPlan>) =>
    setPlans(plans.map((p) => (p.id === id ? { ...p, ...v } : p)));
  const editPlacement = (plan: MediaPlan, id: string, v: Partial<Placement>) =>
    editPlan(plan.id, {
      placements: plan.placements.map((p) =>
        p.id === id ? { ...p, ...v } : p,
      ),
    });
  return (
    <>
      <Notice>
        {t(
          "Costs and response parameters are illustrative assumptions, not current advertising platform quotes. Lock a placement to protect it from adaptive changes.",
          "Les coûts et réponses sont des hypothèses illustratives, pas les tarifs actuels des plateformes. Verrouillez un placement pour le protéger des ajustements adaptatifs.",
        )}
      </Notice>
      <div className="plans">
        {plans.map((plan, i) => (
          <section
            className={`plan-sheet ${open === plan.id ? "open" : ""}`}
            key={plan.id}
          >
            <button
              className="plan-heading"
              onClick={() => setOpen(open === plan.id ? "" : plan.id)}
              aria-expanded={open === plan.id}
            >
              <span className="plan-index">{String.fromCharCode(65 + i)}</span>
              <span className="plan-title">
                <strong>{plan.name}</strong>
                <span>{plan.description}</span>
              </span>
              <span className="plan-summary">
                <strong>{money(plan.price_cents, currency, lang)}</strong>
                <small>
                  {t("price", "prix")} ·{" "}
                  {money(plan.media_budget_cents, currency, lang, true)}{" "}
                  {t("media", "média")}
                </small>
              </span>
              {open === plan.id ? (
                <CaretUp size={20} />
              ) : (
                <CaretDown size={20} />
              )}
            </button>
            {open === plan.id && (
              <div className="plan-content">
                <div className="form-grid plan-settings">
                  <Field label={t("Strategy name", "Nom de la stratégie")}>
                    <input
                      value={plan.name}
                      onChange={(e) =>
                        editPlan(plan.id, { name: e.target.value })
                      }
                    />
                  </Field>
                  <Field label={t("Intensity", "Intensité")}>
                    <select
                      value={plan.intensity}
                      onChange={(e) =>
                        editPlan(plan.id, {
                          intensity: e.target.value as MediaPlan["intensity"],
                        })
                      }
                    >
                      <option value="selective">
                        {t("Selective", "Sélective")}
                      </option>
                      <option value="balanced">
                        {t("Balanced", "Équilibrée")}
                      </option>
                      <option value="intensive">
                        {t("Intensive", "Intensive")}
                      </option>
                    </select>
                  </Field>
                  <NumberField
                    label={
                      t("Candidate price", "Prix proposé") + ` (${currency})`
                    }
                    value={plan.price_cents / 100}
                    onChange={(v) =>
                      editPlan(plan.id, { price_cents: Math.round(v * 100) })
                    }
                    min={0.01}
                    max={1000000}
                    step={0.01}
                  />
                  <Field
                    label={t(
                      "Shared virtual media envelope",
                      "Enveloppe média virtuelle commune",
                    )}
                    hint={t(
                      "Change the budget in the brief and prepare a new experiment. All three candidates use the same envelope.",
                      "Modifiez le budget dans le brief, puis préparez une nouvelle expérience. Les trois propositions ont la même enveloppe.",
                    )}
                  >
                    <input
                      readOnly
                      value={money(plan.media_budget_cents, currency, lang)}
                      aria-readonly="true"
                    />
                  </Field>
                  <label className="checkbox span-2">
                    <input
                      type="checkbox"
                      checked={plan.adaptive}
                      onChange={(e) =>
                        editPlan(plan.id, { adaptive: e.target.checked })
                      }
                    />
                    <span>
                      {t(
                        "Adapt unlocked placements during the simulation",
                        "Adapter les placements non verrouillés pendant la simulation",
                      )}
                      <small>
                        {t(
                          "Every adjustment appears in the final report.",
                          "Chaque ajustement apparaît dans le rapport final.",
                        )}
                      </small>
                    </span>
                  </label>
                </div>
                {plan.media_budget_cents !== budget && (
                  <p className="inline-warning">
                    {t(
                      "This budget differs from the original envelope. Use equal budgets for a fair comparison.",
                      "Ce budget diffère de l’enveloppe initiale. Utilisez des budgets égaux pour comparer équitablement.",
                    )}
                  </p>
                )}
                {plan.rationale.length > 0 && (
                  <details className="plan-rationale">
                    <summary>
                      {t("Why this strategy?", "Pourquoi cette stratégie ?")}
                    </summary>
                    <ul>
                      {plan.rationale.map((r, j) => (
                        <li key={j}>{r}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="placements-heading">
                  <h3>{t("Placements & cadence", "Placements et rythme")}</h3>
                  <span>{plan.placements.length} / 30</span>
                </div>
                <div className="placements">
                  {plan.placements.map((p, j) => (
                    <div
                      className={`placement ${p.locked ? "locked" : ""}`}
                      key={p.id}
                    >
                      <div className="placement-top">
                        <span className="placement-number">{j + 1}</span>
                        <strong>{channelNames[p.channel] ?? p.channel}</strong>
                        <span className="placement-format">{p.format}</span>
                        <div className="placement-actions">
                          <button
                            className="button secondary compact"
                            aria-pressed={p.locked}
                            onClick={() =>
                              editPlacement(plan, p.id, { locked: !p.locked })
                            }
                          >
                            {p.locked ? (
                              <LockSimple size={16} />
                            ) : (
                              <LockSimpleOpen size={16} />
                            )}{" "}
                            {p.locked
                              ? t("Locked", "Verrouillé")
                              : t("Lock", "Verrouiller")}
                          </button>
                          <button
                            className="icon-button danger"
                            disabled={p.locked}
                            onClick={() =>
                              editPlan(plan.id, {
                                placements: plan.placements.filter(
                                  (x) => x.id !== p.id,
                                ),
                              })
                            }
                            aria-label={t(
                              `Remove ${channelNames[p.channel]} placement`,
                              `Retirer le placement ${channelNames[p.channel]}`,
                            )}
                          >
                            <Trash size={18} />
                          </button>
                        </div>
                      </div>
                      <fieldset disabled={p.locked}>
                        <legend className="sr-only">
                          {channelNames[p.channel]}{" "}
                          {t("placement settings", "paramètres du placement")}
                        </legend>
                        <div className="placement-grid">
                          <Field label={t("Channel", "Canal")}>
                            <select
                              value={p.channel}
                              onChange={(e) =>
                                editPlacement(plan, p.id, {
                                  channel: e.target
                                    .value as Placement["channel"],
                                  format: formats(e.target.value)[0],
                                })
                              }
                            >
                              {channels.map((c) => (
                                <option key={c} value={c}>
                                  {channelNames[c]}
                                </option>
                              ))}
                            </select>
                          </Field>
                          <Field
                            label={t("Format", "Format")}
                            hint={t(
                              "Executable formats for this channel.",
                              "Formats exécutables pour ce canal.",
                            )}
                          >
                            <select
                              value={p.format}
                              onChange={(e) =>
                                editPlacement(plan, p.id, {
                                  format: e.target.value,
                                })
                              }
                            >
                              {Array.from(
                                new Set([p.format, ...formats(p.channel)]),
                              ).map((f) => (
                                <option key={f} value={f}>
                                  {f.replaceAll("_", " ")}
                                </option>
                              ))}
                            </select>
                          </Field>
                          <Field label={t("Distribution", "Diffusion")}>
                            <select
                              value={p.distribution}
                              onChange={(e) =>
                                editPlacement(plan, p.id, {
                                  distribution: e.target
                                    .value as Placement["distribution"],
                                })
                              }
                            >
                              <option value="paid">
                                {t("Paid", "Payante")}
                              </option>
                              <option value="organic">
                                {t("Organic", "Organique")}
                              </option>
                              <option value="partnership">
                                {t("Partnership", "Partenariat")}
                              </option>
                            </select>
                          </Field>
                          <Field label={t("Charge basis", "Facturation")}>
                            <select
                              value={p.charge_basis}
                              onChange={(e) =>
                                editPlacement(plan, p.id, {
                                  charge_basis: e.target
                                    .value as Placement["charge_basis"],
                                })
                              }
                            >
                              {["CPM", "CPC", "CPA", "FIXED", "ORGANIC"].map(
                                (v) => (
                                  <option key={v}>{v}</option>
                                ),
                              )}
                            </select>
                          </Field>
                          <NumberField
                            label={t(
                              "Relative budget weight",
                              "Poids budgétaire relatif",
                            )}
                            value={p.weight}
                            onChange={(v) =>
                              editPlacement(plan, p.id, { weight: v })
                            }
                            max={100}
                            step={0.1}
                          />
                          <NumberField
                            label={t(
                              "Daily frequency",
                              "Fréquence quotidienne",
                            )}
                            value={p.daily_frequency}
                            onChange={(v) =>
                              editPlacement(plan, p.id, { daily_frequency: v })
                            }
                            max={12}
                            step={0.1}
                          />
                          {p.charge_basis === "ORGANIC" ? (
                            <Field
                              label={t("Cash charge", "Coût facturé")}
                              hint={t(
                                "Organic delivery has no cash charge.",
                                "La diffusion organique ne facture aucun coût.",
                              )}
                            >
                              <input
                                readOnly
                                value={money(0, currency, lang)}
                              />
                            </Field>
                          ) : (
                            <NumberField
                              label={`${p.charge_basis === "CPM" ? t("Per 1,000 impressions", "Pour 1 000 impressions") : p.charge_basis === "CPC" ? t("Per click", "Par clic") : p.charge_basis === "CPA" ? t("Per acquisition", "Par acquisition") : t("Fixed fee", "Forfait")} (${currency})`}
                              value={
                                (p.charge_basis === "CPM"
                                  ? p.cpm_cents
                                  : p.charge_basis === "CPC"
                                    ? p.cpc_cents
                                    : p.charge_basis === "CPA"
                                      ? p.cpa_cents
                                      : p.fee_cents) / 100
                              }
                              min={p.charge_basis === "FIXED" ? 0 : 0.01}
                              max={
                                p.charge_basis === "CPM" ||
                                p.charge_basis === "CPC"
                                  ? 10000
                                  : 1000000
                              }
                              step={0.01}
                              onChange={(v) => {
                                const key =
                                  p.charge_basis === "CPM"
                                    ? "cpm_cents"
                                    : p.charge_basis === "CPC"
                                      ? "cpc_cents"
                                      : p.charge_basis === "CPA"
                                        ? "cpa_cents"
                                        : "fee_cents";
                                editPlacement(plan, p.id, {
                                  [key]: Math.round(v * 100),
                                });
                              }}
                            />
                          )}
                          <Field
                            label={t(
                              "Dayparts (0–23)",
                              "Heures de diffusion (0–23)",
                            )}
                            hint={t(
                              "Comma-separated local hours.",
                              "Heures locales séparées par des virgules.",
                            )}
                          >
                            <input
                              defaultValue={p.dayparts.join(", ")}
                              key={p.dayparts.join(",")}
                              onBlur={(e) => {
                                const raw = e.target.value
                                  .split(",")
                                  .map((v) => v.trim());
                                const hours = raw.map(Number);
                                if (
                                  !raw.length ||
                                  raw.some((x) => x === "") ||
                                  hours.some(
                                    (h) =>
                                      !Number.isInteger(h) || h < 0 || h > 23,
                                  )
                                ) {
                                  setHoursError(
                                    t(
                                      "Use local hours from 0 to 23, separated by commas.",
                                      "Utilisez des heures de 0 à 23, séparées par des virgules.",
                                    ),
                                  );
                                  e.target.value = p.dayparts.join(", ");
                                } else {
                                  setHoursError("");
                                  editPlacement(plan, p.id, {
                                    dayparts: [...new Set(hours)],
                                  });
                                }
                              }}
                            />
                          </Field>
                          <Field
                            className="span-full"
                            label={t(
                              "Creative message",
                              "Message publicitaire",
                            )}
                          >
                            <textarea
                              rows={2}
                              maxLength={2000}
                              value={p.creative}
                              onChange={(e) =>
                                editPlacement(plan, p.id, {
                                  creative: e.target.value,
                                })
                              }
                            />
                          </Field>
                        </div>
                      </fieldset>
                      <p className="placement-assumption">
                        <Info size={15} />
                        {p.assumption}
                      </p>
                    </div>
                  ))}
                </div>
                {hoursError && (
                  <p className="inline-error" role="alert">
                    {hoursError}
                  </p>
                )}
                <button
                  className="button secondary add-placement"
                  disabled={plan.placements.length >= 30}
                  onClick={() =>
                    editPlan(plan.id, {
                      placements: [...plan.placements, newPlacement()],
                    })
                  }
                >
                  <Plus size={18} />
                  {t("Add placement", "Ajouter un placement")}
                </button>
              </div>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

function ChannelCatalogue({
  catalog,
  currency,
}: {
  catalog: Record<string, unknown>[];
  currency: string;
}) {
  const t = useCopy(),
    lang = useContext(Language);
  return (
    <details className="channel-catalogue">
      <summary>
        {t(
          "Inspect the full channel & format catalogue",
          "Examiner le catalogue complet des canaux et formats",
        )}{" "}
        · {catalog.length}
      </summary>
      <p className="muted small">
        {t(
          "Synthetic, unvalidated mechanism and cost assumptions. These values do not describe current platform prices or measured audiences.",
          "Hypothèses synthétiques non validées de mécanisme et de coût. Ces valeurs ne décrivent ni les tarifs actuels ni des audiences mesurées.",
        )}
      </p>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label={t("Channel catalogue", "Catalogue des canaux")}
      >
        <table>
          <thead>
            <tr>
              <th>{t("Channel", "Canal")}</th>
              <th>{t("Mechanism", "Mécanisme")}</th>
              <th>{t("Formats", "Formats")}</th>
              <th>{t("Default CPM", "CPM initial")}</th>
              <th>
                {t("Synthetic availability", "Disponibilité synthétique")}
              </th>
            </tr>
          </thead>
          <tbody>
            {catalog.map((c) => (
              <tr key={String(c.channel)}>
                <td>{channelNames[String(c.channel)] ?? String(c.name)}</td>
                <td>{String(c.mechanism).replaceAll("_", " ")}</td>
                <td>
                  {Array.isArray(c.formats)
                    ? c.formats.map(String).join(", ").replaceAll("_", " ")
                    : "—"}
                </td>
                <td>{money(Number(c.default_cpm_cents), currency, lang)}</td>
                <td>{percent(Number(c.availability), lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function RunMonitor({
  run,
  busy,
  onCancel,
  onResume,
  onRefresh,
}: {
  run: Run;
  busy: boolean;
  onCancel: () => void;
  onResume: () => void;
  onRefresh: () => void;
}) {
  const t = useCopy(),
    lang = useContext(Language);
  const running = activeStatus(run.status);
  const progress = Math.max(0, Math.min(100, run.progress?.percent ?? 0));
  return (
    <section
      className={`run-monitor ${running ? "is-running" : ""}`}
      aria-label={t("Run progress", "Progression de l’exécution")}
    >
      <div className="run-heading">
        <span className="run-icon">
          {running ? (
            <SpinnerGap className="spin" size={25} />
          ) : run.status === "completed" ? (
            <CheckCircle size={25} />
          ) : (
            <Pause size={25} />
          )}
        </span>
        <div>
          <h2>{statusLabel(run.status, t)}</h2>
          <p>
            {run.id.slice(0, 12)} ·{" "}
            {run.progress?.message ??
              t("Waiting for worker", "En attente du moteur")}
          </p>
        </div>
        <div className="button-row">
          <button
            className="button secondary compact"
            disabled={busy}
            onClick={onRefresh}
          >
            <ArrowClockwise size={17} />
            {t("Refresh run", "Actualiser le suivi")}
          </button>
          {running && (
            <button
              className="button secondary compact"
              disabled={busy}
              onClick={onCancel}
            >
              <Pause size={17} />
              {t("Cancel safely", "Annuler proprement")}
            </button>
          )}
          {resumableStatus(run.status) && (
            <button
              className="button compact"
              disabled={busy}
              onClick={onResume}
            >
              <Play size={17} />
              {t("Resume checkpoint", "Reprendre la sauvegarde")}
            </button>
          )}
        </div>
        <strong className="progress-percent">
          {number(progress, lang, 1)}%
        </strong>
      </div>
      <progress
        max={100}
        value={progress}
        aria-label={t("Experiment completion", "Avancement de l’expérience")}
      />
      <div className="run-meta">
        <span>
          {run.progress?.day
            ? `${t("Day", "Jour")} ${run.progress.day}`
            : t(
                "Reproducible individual states",
                "États individuels reproductibles",
              )}
        </span>
        <span>
          {t(
            "Cancellation saves a resumable checkpoint.",
            "L’annulation conserve un état reprenable.",
          )}
        </span>
      </div>
      {run.error && <p className="inline-error">{run.error}</p>}
    </section>
  );
}

function Results({ report: r, runId }: { report: Report; runId: string }) {
  const t = useCopy(),
    lang = useContext(Language);
  const [scenarioId, setScenarioId] = useState(
      r.winner_id ??
        r.scenarios.find((s) => !s.is_baseline)?.plan_id ??
        r.scenarios[0]?.plan_id ??
        "",
    ),
    [metric, setMetric] = useState<"revenue" | "units" | "spend">("revenue"),
    [showDaily, setShowDaily] = useState(false);
  const chosen =
      r.scenarios.find((s) => s.plan_id === scenarioId) ?? r.scenarios[0],
    winner = r.scenarios.find((s) => s.plan_id === r.winner_id);
  const curr = r.product.currency;
  const candidates = r.scenarios.filter((s) => !s.is_baseline);
  return (
    <div className="results">
      <div className="result-verdict">
        <div>
          <span className="chip">
            {t(
              "Conditional simulation result",
              "Résultat de simulation conditionnel",
            )}
          </span>
          <h2>
            {winner ? winner.name : t("No clear winner", "Aucun gagnant clair")}
          </h2>
          <p>{r.winner_reason}</p>
        </div>
        <div className="exports">
          <span>{t("Take the notebook with you", "Emportez le carnet")}</span>
          <div>
            {(["csv", "json", "html", "md"] as const).map((format) => (
              <a
                className="export-link"
                key={format}
                href={`/api/v1/runs/${runId}/export?format=${format}`}
                download
              >
                <DownloadSimple size={16} />
                {format.toUpperCase()}
              </a>
            ))}
          </div>
        </div>
      </div>
      <Notice>
        {t(
          "Intervals describe variability under these assumptions; they are not confidence bounds on real-world sales. No campaign or purchase took place.",
          "Les intervalles décrivent la variabilité sous ces hypothèses ; ils ne bornent pas des ventes réelles. Aucune campagne ni aucun achat n’a eu lieu.",
        )}
      </Notice>
      <section className="worksheet result-comparison">
        <div className="sheet-header">
          <h2>{t("Strategy comparison", "Comparaison des stratégies")}</h2>
          <span className="chip">
            {number(r.population, lang)} {t("people", "personnes")} · {r.rounds}{" "}
            {t("days", "jours")}
          </span>
        </div>
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label={t(
            "Strategy comparison table",
            "Tableau de comparaison des stratégies",
          )}
        >
          <table>
            <thead>
              <tr>
                <th>{t("Strategy", "Stratégie")}</th>
                <th>{t("Price", "Prix")}</th>
                <th>{t("Mean units", "Unités moyennes")}</th>
                <th>{t("Mean revenue", "CA moyen")}</th>
                <th>{t("Revenue interval", "Intervalle du CA")}</th>
                <th>{t("Media spend", "Dépense média")}</th>
                <th>{t("All-buyer CAC", "CAC tous acheteurs")}</th>
                <th>{t("Paid CAC", "CAC payant")}</th>
              </tr>
            </thead>
            <tbody>
              {r.scenarios.map((s) => (
                <tr
                  key={s.plan_id}
                  className={
                    s.is_baseline
                      ? "baseline-row"
                      : s.plan_id === r.winner_id
                        ? "winner-row"
                        : ""
                  }
                >
                  <th>
                    <button
                      className="table-button"
                      onClick={() => setScenarioId(s.plan_id)}
                    >
                      {s.plan_id === r.winner_id && <CheckCircle size={16} />}{" "}
                      {s.name}
                    </button>
                    <small>
                      {s.is_baseline
                        ? t("No-campaign baseline", "Témoin sans campagne")
                        : t("Campaign candidate", "Stratégie avec campagne")}
                    </small>
                  </th>
                  <td>{money(s.price_cents, curr, lang)}</td>
                  <td>{number(s.mean_units, lang, 1)}</td>
                  <td>
                    <strong>{money(s.mean_revenue_cents, curr, lang)}</strong>
                  </td>
                  <td>
                    {s.revenue_interval_cents
                      ?.map((v) => money(v, curr, lang, true))
                      .join(" – ") ?? "—"}
                  </td>
                  <td>{money(s.mean_spend_cents, curr, lang)}</td>
                  <td>{money(s.mean_cac_cents, curr, lang)}</td>
                  <td>{money(s.mean_paid_cac_cents, curr, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-caption">
          {t(
            "— means the denominator is zero or the metric does not apply. CAC = virtual media spend / qualifying unique buyers.",
            "— indique un dénominateur nul ou une mesure non applicable. CAC = dépense média virtuelle / acheteurs uniques concernés.",
          )}
        </p>
      </section>
      <section className="worksheet chart-section">
        <div className="sheet-header">
          <h2>{t("How the launch unfolded", "Le déroulé du lancement")}</h2>
          <div
            className="segmented"
            aria-label={t("Chart measure", "Mesure du graphique")}
          >
            {(["revenue", "units", "spend"] as const).map((m, i) => (
              <button
                key={m}
                className={metric === m ? "selected" : ""}
                onClick={() => setMetric(m)}
              >
                {
                  [
                    t("Revenue", "CA"),
                    t("Units", "Unités"),
                    t("Spend", "Dépenses"),
                  ][i]
                }
              </button>
            ))}
          </div>
        </div>
        <LaunchChart scenarios={candidates} metric={metric} currency={curr} />
        <div className="chart-bottom">
          <div className="chart-legend">
            {candidates.map((s, i) => (
              <span key={s.plan_id}>
                <i
                  style={{ background: chartColors[i % chartColors.length] }}
                />
                {s.name}
              </span>
            ))}
          </div>
          <button
            className="text-button"
            aria-expanded={showDaily}
            onClick={() => setShowDaily(!showDaily)}
          >
            {showDaily
              ? t("Hide daily table", "Masquer le tableau quotidien")
              : t("Show daily table", "Afficher le tableau quotidien")}
          </button>
        </div>
        {showDaily && (
          <div
            className="table-scroll"
            tabIndex={0}
            role="region"
            aria-label={t(
              "Daily scenario data",
              "Données quotidiennes des scénarios",
            )}
          >
            <table>
              <thead>
                <tr>
                  <th>{t("Day", "Jour")}</th>
                  <th>{t("Strategy", "Stratégie")}</th>
                  <th>{t("Units", "Unités")}</th>
                  <th>{t("Revenue", "CA")}</th>
                  <th>{t("Spend", "Dépenses")}</th>
                  <th>{t("Intention", "Intention")}</th>
                  <th>{t("Fatigue", "Fatigue")}</th>
                </tr>
              </thead>
              <tbody>
                {candidates.flatMap((s) =>
                  s.daily.map((d) => (
                    <tr key={`${s.plan_id}-${d.day}`}>
                      <td>{d.day}</td>
                      <th>{s.name}</th>
                      <td>{number(d.units, lang, 1)}</td>
                      <td>{money(d.revenue_cents, curr, lang)}</td>
                      <td>{money(d.spend_cents, curr, lang)}</td>
                      <td>{percent(d.mean_intention, lang)}</td>
                      <td>{percent(d.mean_fatigue, lang)}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {chosen && (
        <>
          <div className="scenario-selector">
            <h2>
              {t("Look inside a strategy", "À l’intérieur d’une stratégie")}
            </h2>
            <Field label={t("Selected strategy", "Stratégie sélectionnée")}>
              <select
                value={chosen.plan_id}
                onChange={(e) => setScenarioId(e.target.value)}
              >
                {r.scenarios.map((s) => (
                  <option key={s.plan_id} value={s.plan_id}>
                    {s.name}
                    {s.is_baseline ? ` · ${t("baseline", "témoin")}` : ""}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="financial-strip">
            <dl>
              {[
                {
                  label: t("Unique buyers", "Acheteurs uniques"),
                  value: number(chosen.mean_unique_buyers, lang, 1),
                },
                {
                  label: t(
                    "Attributed paid buyers",
                    "Acheteurs attribués payants",
                  ),
                  value: number(chosen.mean_paid_units, lang, 1),
                },
                {
                  label: t(
                    "Commission (part of media)",
                    "Commission (incluse au média)",
                  ),
                  value: money(chosen.mean_commission_cents, curr, lang),
                },
                {
                  label: t(
                    "Contribution after variable costs & media",
                    "Contribution après coûts variables et média",
                  ),
                  value: money(chosen.mean_contribution_cents, curr, lang),
                },
              ].map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </div>
          <ChannelTable scenario={chosen} currency={curr} />
          <div className="detail-columns">
            <section className="worksheet">
              <div className="sheet-header">
                <h3>{t("Adaptive changes", "Ajustements adaptatifs")}</h3>
                <span>{chosen.adjustments?.length ?? 0}</span>
              </div>
              <div className="padded">
                {chosen.adjustments?.length ? (
                  <RecordList
                    records={chosen.adjustments}
                    label={t("Adjustment", "Ajustement")}
                  />
                ) : (
                  <p className="muted">
                    {t(
                      "No adaptive changes were made in this scenario.",
                      "Aucun ajustement adaptatif dans ce scénario.",
                    )}
                  </p>
                )}
              </div>
            </section>
            <section className="worksheet">
              <div className="sheet-header">
                <h3>{t("Individual traces", "Trajectoires individuelles")}</h3>
                <span>{chosen.traces?.length ?? 0}</span>
              </div>
              <div className="padded">
                <p className="muted small">
                  {t(
                    "A bounded inspection sample. Exposure, intention and purchase remain distinct events.",
                    "Un échantillon d’inspection limité. Exposition, intention et achat restent distincts.",
                  )}
                </p>
                {chosen.traces?.length ? (
                  <RecordList
                    records={chosen.traces}
                    label={t("Trace", "Trajectoire")}
                  />
                ) : (
                  <p className="muted">
                    {t(
                      "No representative trace is available for this scenario.",
                      "Aucune trajectoire représentative disponible pour ce scénario.",
                    )}
                  </p>
                )}
              </div>
            </section>
          </div>
        </>
      )}
      <section className="methodology worksheet">
        <div className="sheet-header">
          <h2>
            {t(
              "Assumptions & reproducibility",
              "Hypothèses et reproductibilité",
            )}
          </h2>
          <span className="chip">{r.engine_version}</span>
        </div>
        <div className="padded">
          <dl className="inline-meta">
            <div>
              <dt>{t("Seed", "Graine")}</dt>
              <dd>{r.seed}</dd>
            </div>
            <div>
              <dt>{t("Schema", "Schéma")}</dt>
              <dd>{r.schema_version}</dd>
            </div>
            <div>
              <dt>{t("Population", "Population")}</dt>
              <dd>{number(r.population, lang)}</dd>
            </div>
          </dl>
          <ul>
            {r.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
          <details>
            <summary>
              {t("Comparison details", "Détails des comparaisons")}
            </summary>
            <pre>{plain(r.comparisons)}</pre>
          </details>
          {Array.isArray(r.metadata.semantic_reactions) &&
            r.metadata.semantic_reactions.length > 0 && (
              <details open>
                <summary>
                  {t(
                    "Optional AI representative reactions",
                    "Réactions représentatives IA facultatives",
                  )}
                </summary>
                <p className="muted small">
                  {t(
                    "Qualitative, synthetic comments grounded in the experiment. They are not customer interviews.",
                    "Commentaires qualitatifs synthétiques fondés sur l’expérience. Ce ne sont pas des entretiens clients.",
                  )}
                </p>
                <RecordList
                  records={
                    r.metadata.semantic_reactions as Record<string, unknown>[]
                  }
                  label={t("Reaction", "Réaction")}
                />
              </details>
            )}
          <details>
            <summary>
              {t("Execution metadata", "Métadonnées d’exécution")}
            </summary>
            <pre>{plain(r.metadata)}</pre>
          </details>
        </div>
      </section>
    </div>
  );
}
const chartColors = ["#214cfa", "#087568", "#b6630a"];
function LaunchChart({
  scenarios,
  metric,
  currency,
}: {
  scenarios: Scenario[];
  metric: "revenue" | "units" | "spend";
  currency: string;
}) {
  const t = useCopy(),
    lang = useContext(Language);
  const key =
    metric === "revenue"
      ? "cumulative_revenue_cents"
      : metric === "spend"
        ? "cumulative_spend_cents"
        : "cumulative_units";
  const all = scenarios.flatMap((s) => s.daily ?? []);
  if (!all.length)
    return (
      <p className="padded muted">
        {t(
          "Daily values are not available.",
          "Les valeurs quotidiennes ne sont pas disponibles.",
        )}
      </p>
    );
  const width = 960,
    height = 286,
    left = 80,
    right = 25,
    top = 20,
    bottom = 42,
    maxDay = Math.max(1, ...all.map((d) => d.day)),
    max = Math.max(metric === "units" ? 1 : 100, ...all.map((d) => d[key]));
  const x = (day: number) =>
      left + ((day - 1) / Math.max(1, maxDay - 1)) * (width - left - right),
    y = (v: number) => height - bottom - (v / max) * (height - top - bottom);
  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="launch-chart-title launch-chart-description"
      >
        <title id="launch-chart-title">
          {t("Cumulative launch outcomes", "Résultats cumulés du lancement")}
        </title>
        <desc id="launch-chart-description">
          {t(
            "Daily cumulative results for each campaign candidate. The same values are available in the daily table.",
            "Résultats quotidiens cumulés de chaque stratégie. Les mêmes valeurs sont disponibles dans le tableau quotidien.",
          )}
        </desc>
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line
              x1={left}
              x2={width - right}
              y1={y(v * max)}
              y2={y(v * max)}
              stroke="#dce2ec"
              strokeDasharray={v === 0 ? "0" : "3 5"}
            />
            <text x={left - 12} y={y(v * max) + 4} textAnchor="end">
              {metric === "units"
                ? number(v * max, lang, max <= 10 ? 1 : 0)
                : money(v * max, currency, lang, max >= 10000)}
            </text>
          </g>
        ))}
        {Array.from(
          new Set([
            1,
            Math.ceil(maxDay / 3),
            Math.ceil((maxDay * 2) / 3),
            maxDay,
          ]),
        ).map((day) => (
          <text x={x(day)} y={height - 14} textAnchor="middle" key={day}>
            {t("Day", "Jour")} {day}
          </text>
        ))}
        {scenarios.map((s, i) => (
          <polyline
            key={s.plan_id}
            points={s.daily.map((d) => `${x(d.day)},${y(d[key])}`).join(" ")}
            fill="none"
            stroke={chartColors[i % chartColors.length]}
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
      </svg>
    </div>
  );
}
function ChannelTable({
  scenario: s,
  currency,
}: {
  scenario: Scenario;
  currency: string;
}) {
  const t = useCopy(),
    lang = useContext(Language);
  return (
    <section className="worksheet">
      <div className="sheet-header">
        <h3>{t("Channel attribution", "Attribution par canal")}</h3>
        <span className="chip">{s.name}</span>
      </div>
      {s.channels?.length ? (
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label={t(
            "Channel attribution table",
            "Tableau d’attribution par canal",
          )}
        >
          <table>
            <thead>
              <tr>
                {[
                  t("Channel", "Canal"),
                  t("Impressions", "Impressions"),
                  t("Unique reach", "Portée unique"),
                  t("Clicks", "Clics"),
                  t("Attributed units", "Unités attribuées"),
                  t("Revenue", "CA"),
                  t("Spend", "Dépenses"),
                  t("Conversion", "Conversion"),
                  t("CAC", "CAC"),
                ].map((v) => (
                  <th key={v}>{v}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {s.channels.map((c, i) => (
                <tr key={`${c.channel}-${i}`}>
                  <th>{channelNames[c.channel] ?? c.channel}</th>
                  <td>{number(c.impressions, lang)}</td>
                  <td>{number(c.unique_reach, lang)}</td>
                  <td>{number(c.clicks, lang)}</td>
                  <td>{number(c.units, lang, 1)}</td>
                  <td>{money(c.revenue_cents, currency, lang)}</td>
                  <td>{money(c.spend_cents, currency, lang)}</td>
                  <td>{percent(c.attributed_conversion_rate, lang)}</td>
                  <td>{money(c.cac_cents, currency, lang)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="padded muted">
          {t(
            "No paid channel attribution for this baseline.",
            "Aucune attribution payante pour ce témoin.",
          )}
        </p>
      )}
      {s.channels?.some((c) => c.views !== undefined) && (
        <details className="engagement-details">
          <summary>
            {t(
              "Engagement, social diffusion & attribution detail",
              "Engagement, diffusion sociale et détail d’attribution",
            )}
          </summary>
          <div
            className="table-scroll"
            tabIndex={0}
            role="region"
            aria-label={t("Engagement events", "Événements d’engagement")}
          >
            <table>
              <thead>
                <tr>
                  {[
                    t("Channel", "Canal"),
                    t("Views", "Vues"),
                    t("Completions", "Complétions"),
                    t("Skips", "Passages"),
                    t("Comments", "Commentaires"),
                    t("Shares", "Partages"),
                    t("Creator posts", "Publications créateurs"),
                    t("Earned impressions", "Impressions gagnées"),
                    t(
                      "Click-attributed buyers",
                      "Acheteurs attribués aux clics",
                    ),
                    t("View-attributed buyers", "Acheteurs attribués aux vues"),
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {s.channels.map((c, i) => (
                  <tr key={c.channel + i}>
                    <th>{channelNames[c.channel] ?? c.channel}</th>
                    {[
                      c.views,
                      c.completions,
                      c.skips,
                      c.comments,
                      c.shares,
                      c.creator_posts,
                      c.earned_impressions,
                      c.click_attributed_units,
                      c.view_attributed_units,
                    ].map((v, j) => (
                      <td key={j}>{number(v, lang, 1)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <p className="table-caption">
        {t(
          "Unique reach is deduplicated within a channel; summing channel reach does not give unique audience size.",
          "La portée unique est dédupliquée dans chaque canal ; additionner les portées ne donne pas l’audience unique.",
        )}
      </p>
    </section>
  );
}
function RecordList({
  records,
  label,
}: {
  records: Record<string, unknown>[];
  label: string;
}) {
  return (
    <div className="record-list">
      {records.slice(0, 100).map((record, i) => (
        <details key={i}>
          <summary>
            {String(
              record.persona_id ??
                record.person_id ??
                record.channel ??
                `${label} ${i + 1}`,
            )}
            {record.day != null && <span> · {String(record.day)}</span>}
            {record.event != null && <span> · {String(record.event)}</span>}
          </summary>
          <dl className="record-data">
            {Object.entries(record).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>
                  {typeof value === "object" ? (
                    <pre>{plain(value)}</pre>
                  ) : (
                    plain(value)
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      ))}
    </div>
  );
}

function Settings({
  boot,
  onRefresh,
}: {
  boot: Bootstrap | null;
  onRefresh: () => void;
}) {
  const t = useCopy();
  return (
    <section className="worksheet settings">
      <div className="sheet-header">
        <h2>{t("Connections & privacy", "Connexions et confidentialité")}</h2>
        <button className="button secondary compact" onClick={onRefresh}>
          <ArrowClockwise size={17} />
          {t("Refresh status", "Actualiser")}
        </button>
      </div>
      <div className="padded">
        <Notice>
          {t(
            "Provider credentials are read from the server environment. This screen never requests or displays a secret. Offline demos do not use any provider.",
            "Les identifiants sont lus dans l’environnement du serveur. Cet écran ne demande ni n’affiche aucun secret. Les démos hors ligne n’utilisent aucun fournisseur.",
          )}
        </Notice>
        <div className="provider-list">
          {[
            {
              name: "Tavily",
              configured: boot?.provider_status.tavily,
              role: t("Live research", "Recherche web"),
            },
            {
              name: "Firecrawl",
              configured: boot?.provider_status.firecrawl,
              role: t(
                "Optional page extraction",
                "Extraction de pages facultative",
              ),
            },
            {
              name: t("Semantic model", "Modèle sémantique"),
              configured: boot?.provider_status.llm,
              role:
                boot?.provider_status.llm_model ??
                t(
                  "Optional structured analysis",
                  "Analyse structurée facultative",
                ),
            },
          ].map((p) => (
            <div key={p.name}>
              <div>
                <strong>{p.name}</strong>
                <p>{p.role}</p>
              </div>
              <span className={`chip ${p.configured ? "observed" : ""}`}>
                {p.configured
                  ? t("Configured", "Configuré")
                  : t("Not configured", "Non configuré")}
              </span>
            </div>
          ))}
        </div>
        <h3>{t("Where the work lives", "Où se trouve votre travail")}</h3>
        <p>
          {t(
            "Experiments, checkpoints, research, and local memory are stored by the local Python service in the application-data directory. The browser stores only your language preference. Export a report to keep a portable copy.",
            "Les expériences, sauvegardes, recherches et mémoires sont conservées par le service Python local dans le dossier de données de l’application. Le navigateur conserve seulement votre préférence de langue. Exportez un rapport pour en garder une copie portable.",
          )}
        </p>
        <h3>{t("Cost rules", "Règles de coût")}</h3>
        <p>
          {t(
            "The virtual media budget never charges an advertising account. The real API cap is separate, saved with the experiment, and reserved before provider calls. Change it in a new brief before preparing an experiment.",
            "Le budget média virtuel ne débite aucun compte publicitaire. Le plafond API réel est distinct, enregistré avec l’expérience et réservé avant les appels. Modifiez-le dans un nouveau brief avant la préparation.",
          )}
        </p>
        <details>
          <summary>
            {t(
              "Available service capabilities",
              "Capacités du service disponibles",
            )}
          </summary>
          <pre>{plain(boot?.capabilities ?? {})}</pre>
        </details>
      </div>
    </section>
  );
}
function Roadmap() {
  const t = useCopy();
  return (
    <section className="worksheet roadmap">
      <div className="sheet-header">
        <h2>
          {t(
            "Next: functional browsing",
            "La suite : navigation fonctionnelle",
          )}
        </h2>
        <span className="chip assumption">
          {t("Future work", "Prévu ultérieurement")}
        </span>
      </div>
      <div className="padded">
        <h3>
          {t(
            "From reading a page to using it.",
            "De la lecture d’une page à son utilisation.",
          )}
        </h3>
        <p>
          {t(
            "Page capture, image-grounded observation and progressive synthetic persona reactions are available in The page. A later extension will let a bounded sample navigate and test real interactive paths.",
            "La capture, l’observation fondée sur les images et les réactions progressives des personas synthétiques sont disponibles dans La page. Une extension ultérieure permettra à un échantillon limité de naviguer et de tester des parcours interactifs.",
          )}
        </p>
        <div className="notice">
          <Info />
          <p>
            {t(
              "A screenshot does not verify buttons, forms, accessibility flows, checkout, or real conversion. Autonomous functional navigation remains future work.",
              "Une capture ne vérifie ni les boutons, ni les formulaires, ni les parcours accessibles, ni le paiement, ni les conversions réelles. La navigation fonctionnelle autonome reste ultérieure.",
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
