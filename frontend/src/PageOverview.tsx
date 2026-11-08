import { ArrowRight } from "@phosphor-icons/react";
import type { Lang } from "./types";
import type { PageAuditReport } from "./pageAnalysisTypes";

export default function PageOverview({
  report: r,
  lang,
  onInspect,
}: {
  report: PageAuditReport;
  lang: Lang;
  onInspect: (id?: string) => void;
}) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en);
  const people = new Map(
    r.reviews.map((review) => [review.persona_id, review.age]),
  );
  const bands = [
    { min: 18, max: 34 },
    { min: 35, max: 54 },
    { min: 55, max: 74 },
    { min: 75, max: 100 },
  ]
    .map((band) => {
      const ids = new Set(
        [...people]
          .filter(([, age]) => age >= band.min && age <= band.max)
          .map(([id]) => id),
      );
      const reviews = r.reviews.filter((review) => ids.has(review.persona_id));
      const top = (key: "questions" | "frictions") => {
        const answers = new Map<string, Set<string>>();
        for (const review of reviews)
          for (const text of review[key]) {
            const value = text.trim();
            if (value) {
              const personas = answers.get(value) ?? new Set<string>();
              personas.add(review.persona_id);
              answers.set(value, personas);
            }
          }
        return [...answers]
          .sort((a, b) => b[1].size - a[1].size)
          .slice(0, 2)
          .map(([text]) => text);
      };
      return {
        ...band,
        count: ids.size,
        questions: top("questions"),
        frictions: top("frictions"),
      };
    })
    .filter((band) => band.count > 0);
  const findings = r.findings
    .filter((f) => typeof f.text === "string" && f.text.trim())
    .sort(
      (a, b) =>
        (({ high: 0, medium: 1, low: 2 })[String(a.severity)] ?? 3) -
        ({ high: 0, medium: 1, low: 2 }[String(b.severity)] ?? 3),
    )
    .slice(0, 3);
  const understandings = [
    ...new Map(
      r.reviews
        .filter((v) => v.understanding.trim())
        .map((v) => [v.understanding, { text: v.understanding, age: v.age }]),
    ).values(),
  ].slice(0, 1);
  return (
    <section className="page-executive-summary">
      <span className="report-section-label">
        {t("PAGE ANALYSIS REPORT", "RAPPORT DE LECTURE DE PAGE")}
      </span>
      <h2>
        {t("What stands out from the reading", "Ce qui ressort de la lecture")}
      </h2>
      <p>
        {t(
          "Start with the questions and points of friction. Then inspect the screenshots and individual reactions to understand where they came from.",
          "Commencez par les questions et les freins. Examinez ensuite les captures et les réactions individuelles pour comprendre leur origine.",
        )}
      </p>
      {r.mode === "demo" && (
        <div className="notice warning">
          {t(
            "Fictional demonstration — no visual AI reading",
            "Démonstration fictive — aucune lecture par IA visuelle",
          )}
        </div>
      )}
      <div className="page-overview-metrics">
        <div>
          <strong>{people.size}</strong>
          <span>
            {t(
              "distinct synthetic personas",
              "personas synthétiques distincts",
            )}
          </span>
        </div>
        <div>
          <strong>{r.observations.length}</strong>
          <span>{t("sections described", "sections décrites")}</span>
        </div>
        <div>
          <strong>{r.findings.length}</strong>
          <span>{t("reported findings", "constats rapportés")}</span>
        </div>
      </div>
      <section className="page-primary-findings">
        <h3>{t("Main findings", "Les principaux constats")}</h3>
        {findings.length ? (
          <ol>
            {findings.map((finding, i) => (
              <li key={String(finding.id ?? i)}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <p>{String(finding.text)}</p>
                  {finding.snapshot_id != null && (
                    <button
                      className="text-button"
                      onClick={() => onInspect(String(finding.snapshot_id))}
                    >
                      {t(
                        "See the supporting section",
                        "Voir la section concernée",
                      )}
                      <ArrowRight size={14} />
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">
            {t(
              "No specific finding was supplied. That does not establish that the page is effective or easy to understand.",
              "Aucun constat précis n’a été renseigné. Cela ne démontre pas l’efficacité ou la clarté de la page.",
            )}
          </p>
        )}
      </section>
      {understandings.length > 0 && (
        <section className="understanding-excerpts">
          <h3>
            {t(
              "What a persona understood — sample excerpt",
              "Ce qu’un persona a compris — extrait",
            )}
          </h3>
          {understandings.map((v, i) => (
            <blockquote key={i}>
              <p>
                {v.text.length > 280
                  ? v.text.slice(0, 280).replace(/\s+\S*$/, "") + "…"
                  : v.text}
              </p>
              <cite>
                {t("Synthetic profile", "Profil synthétique")} · {v.age}{" "}
                {t("years", "ans")}
              </cite>
            </blockquote>
          ))}
        </section>
      )}
      <section className="page-cohorts">
        <h3>
          {t(
            "Questions and friction in the sampled age groups",
            "Questions et freins dans les âges échantillonnés",
          )}
        </h3>
        <p className="muted">
          {t(
            "Each persona is counted once, even if it read several sections or variants. These small synthetic groups do not describe real age-based behaviour.",
            "Chaque persona est compté une seule fois, même après plusieurs sections ou variantes. Ces petits groupes synthétiques ne décrivent pas les comportements réels d’une tranche d’âge.",
          )}
        </p>
        <div
          className="table-scroll"
          role="region"
          aria-label={t("Sampled age groups", "Âges échantillonnés")}
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>{t("Ages", "Âges")}</th>
                <th>{t("Personas", "Personas")}</th>
                <th>{t("Questions expressed", "Questions exprimées")}</th>
                <th>{t("Friction expressed", "Freins exprimés")}</th>
              </tr>
            </thead>
            <tbody>
              {bands.map((b) => (
                <tr key={b.min}>
                  <th>
                    {b.min}–{b.max} {t("years", "ans")}
                  </th>
                  <td>{b.count}</td>
                  <td>
                    {b.questions.length
                      ? b.questions.join(" · ")
                      : t("No question supplied", "Aucune question renseignée")}
                  </td>
                  <td>
                    {b.frictions.length
                      ? b.frictions.join(" · ")
                      : t("No friction supplied", "Aucun frein renseigné")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <button className="button secondary" onClick={() => onInspect()}>
        {t("Explore the visual evidence", "Explorer les preuves visuelles")}
        <ArrowRight size={18} />
      </button>
    </section>
  );
}
