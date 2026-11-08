import { ArrowRight, WarningCircle, CheckCircle } from "@phosphor-icons/react";
import type { Lang, Report } from "./types";
import { money, number, percent, planName } from "./utils";

export function CredibilityNotice({
  value,
  lang,
}: {
  value: unknown;
  lang: Lang;
}) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en);
  const c =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : null;
  const status = String(c?.status ?? "legacy");
  const title =
    status === "extraordinary_unsubstantiated"
      ? t(
          "Extraordinary claim without supporting evidence",
          "Promesse extraordinaire non étayée",
        )
      : status === "needs_evidence"
        ? t("Supporting evidence is missing", "Des éléments de preuve manquent")
        : status === "ordinary"
          ? t(
              "Product claims still need verification",
              "Les promesses du produit restent à vérifier",
            )
          : t(
              "Credibility not assessed — previous model",
              "Crédibilité non évaluée — ancien modèle",
            );
  const strings = (key: string) =>
    Array.isArray(c?.[key])
      ? (c![key] as unknown[]).map((v) =>
          v && typeof v === "object" && "text" in v
            ? String(v.text)
            : String(v),
        )
      : [];
  return (
    <aside
      className={`credibility-notice ${status === "extraordinary_unsubstantiated" ? "strong" : ""}`}
      aria-label={t("Product credibility", "Crédibilité du produit")}
    >
      <WarningCircle size={23} />
      <div>
        <strong>{title}</strong>
        <details>
          <summary>
            {t("Reasons, evidence and limits", "Raisons, preuves et limites")}
          </summary>
          <p>
            {t(
              "This simulation cannot establish that a promise is true or that a product works. Virtual interest is not proof of real demand.",
              "Cette simulation ne prouve ni la véracité d’une promesse ni l’efficacité d’un produit. L’intérêt virtuel ne prouve pas une demande réelle.",
            )}
          </p>
          {strings("reasons").length > 0 && (
            <ul>
              {strings("reasons")
                .slice(0, 2)
                .map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
            </ul>
          )}
          {c && (
            <div>
              {strings("claims").length > 0 && (
                <p>
                  <strong>
                    {t("Claims considered", "Promesses examinées")}:{" "}
                  </strong>
                  {strings("claims").join(" · ")}
                </p>
              )}
              {strings("required_evidence").length > 0 && (
                <ul>
                  {strings("required_evidence").map((v, i) => (
                    <li key={i}>{v}</li>
                  ))}
                </ul>
              )}
              <p>
                {typeof c.score === "number" && (
                  <span>
                    {t(
                      "Heuristic credibility score",
                      "Score heuristique de crédibilité",
                    )}
                    : {percent(c.score, lang)}.{" "}
                  </span>
                )}
                {typeof c.scam_suspicion === "number" && (
                  <span>
                    {t(
                      "Heuristic suspicion signal",
                      "Signal heuristique de suspicion",
                    )}
                    : {percent(c.scam_suspicion, lang)}.{" "}
                  </span>
                )}
                {t(
                  "Rule-based assumptions; neither a verified scientific assessment nor proof of fraud.",
                  "Hypothèses fondées sur des règles ; ni expertise scientifique validée, ni preuve de fraude.",
                )}
              </p>
            </div>
          )}
        </details>
      </div>
    </aside>
  );
}
export default function ResultOverview({
  report: r,
  lang,
  onSelect,
  showCredibility = true,
}: {
  report: Report;
  lang: Lang;
  onSelect?: (id: string) => void;
  showCredibility?: boolean;
}) {
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en);
  const ranked = r.scenarios
    .filter((s) => !s.is_baseline)
    .sort((a, b) => b.mean_revenue_cents - a.mean_revenue_cents);
  const winner = ranked.find((s) => s.plan_id === r.winner_id),
    leader = winner ?? ranked[0];
  if (!leader)
    return (
      <div className="notice">
        {t(
          "No campaign result is available in this report.",
          "Aucun résultat de campagne n’est disponible dans ce rapport.",
        )}
      </div>
    );
  const noSales = ranked.every((s) => s.mean_units === 0),
    curr = r.product.currency;
  const title = noSales
    ? t(
        "No virtual sales in these scenarios.",
        "Aucune vente virtuelle dans ces scénarios.",
      )
    : winner
      ? t(
          `${planName(winner, lang)} leads this experiment.`,
          `${planName(winner, lang)} arrive en tête de cette expérience.`,
        )
      : t(
          "No strategy clearly outperforms the others.",
          "Aucune stratégie ne se détache avec certitude.",
        );
  return (
    <section className="result-overview">
      <div className="report-introduction">
        <h2>{title}</h2>
        <p>
          {winner && !noSales
            ? t(
                `Under these assumptions, this strategy is the supported choice among the three candidates.`,
                `Sous ces hypothèses, cette stratégie est le choix retenu parmi les trois propositions.`,
              )
            : noSales
              ? t(
                  "Review the claims, price and audience. This result remains conditional on the model’s assumptions.",
                  "Revoyez les promesses, le prix et le public. Ce résultat dépend des hypothèses du modèle.",
                )
              : t(
                  `${planName(leader, lang)} has the highest virtual revenue, but the validation does not establish a clear advantage.`,
                  `${planName(leader, lang)} affiche le CA virtuel le plus élevé, mais la validation ne démontre pas d’avantage net.`,
                )}
        </p>
        <details className="verdict-method">
          <summary>
            {t(
              "How this verdict was obtained",
              "Comment ce verdict a été obtenu",
            )}
          </summary>
          <p>{r.winner_reason}</p>
        </details>
      </div>
      <section
        className="outcome-kpis"
        aria-label={t(
          `Results for ${planName(leader, lang)}`,
          `Résultats de ${planName(leader, lang)}`,
        )}
      >
        <div className="outcome-kpi-caption">
          <h3>
            {t("In figures", "En chiffres")} · {planName(leader, lang)}
          </h3>
          <span>
            {t(
              "Scenario totals · validation averages",
              "Totaux du scénario · moyennes de validation",
            )}
          </span>
        </div>
        <dl>
          <div>
            <dt>{t("Virtual sales", "Ventes virtuelles")}</dt>
            <dd>{number(leader.mean_units, lang, 1)}</dd>
            <small>{t("units purchased", "unités achetées")}</small>
          </div>
          <div>
            <dt>{t("Virtual revenue", "Chiffre d’affaires virtuel")}</dt>
            <dd>{money(leader.mean_revenue_cents, curr, lang)}</dd>
            <small>{t(`over ${r.rounds} days`, `sur ${r.rounds} jours`)}</small>
          </div>
          <div>
            <dt>{t("Media spend", "Budget média utilisé")}</dt>
            <dd>{money(leader.mean_spend_cents, curr, lang)}</dd>
            <small>
              {t("virtual advertising costs", "coûts publicitaires virtuels")}
            </small>
          </div>
          <div>
            <dt>{t("Cost per buyer (CAC)", "Coût par acheteur (CAC)")}</dt>
            <dd>
              {leader.mean_cac_cents == null
                ? t("Not calculable", "Non calculable")
                : money(leader.mean_cac_cents, curr, lang)}
            </dd>
            <small>
              {leader.mean_units === 0
                ? t(
                    "no buyer in this scenario",
                    "aucun acheteur dans ce scénario",
                  )
                : t(
                    "media spend / unique buyers",
                    "dépense média / acheteurs uniques",
                  )}
            </small>
          </div>
        </dl>
      </section>
      {showCredibility && (
        <CredibilityNotice value={r.metadata.product_credibility} lang={lang} />
      )}
      <section className="ranked-strategies">
        <div className="report-section-heading">
          <h2>
            {t("Compare the three strategies", "Comparer les trois stratégies")}
          </h2>
          <span>
            {noSales
              ? t(
                  "No purchase in any candidate",
                  "Aucun achat pour les trois propositions",
                )
              : t("Ordered by virtual revenue", "Classées par CA virtuel")}
          </span>
        </div>
        <ol>
          {ranked.map((s, i) => (
            <li
              key={s.plan_id}
              className={
                !noSales && s.plan_id === leader.plan_id ? "leading" : ""
              }
            >
              <div className="strategy-rank-heading">
                <span className="strategy-rank-number">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3>{planName(s, lang)}</h3>
                  <p>
                    {t("Selling price", "Prix de vente")}{" "}
                    {money(s.price_cents, curr, lang)}
                    {!noSales && s.plan_id === leader.plan_id && (
                      <span className="rank-label">
                        {winner ? <CheckCircle size={14} /> : null}
                        {winner
                          ? t("Selected strategy", "Stratégie retenue")
                          : t(
                              "Highest virtual revenue",
                              "CA virtuel le plus élevé",
                            )}
                      </span>
                    )}
                  </p>
                </div>
                {onSelect && (
                  <button
                    className="text-button"
                    onClick={() => onSelect(s.plan_id)}
                  >
                    {t("Inspect", "Examiner")}
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
              <dl className="strategy-rank-values">
                <div>
                  <dt>{t("Sales", "Ventes")}</dt>
                  <dd>{number(s.mean_units, lang, 1)}</dd>
                </div>
                <div>
                  <dt>{t("Virtual revenue", "CA virtuel")}</dt>
                  <dd>{money(s.mean_revenue_cents, curr, lang)}</dd>
                </div>
                <div>
                  <dt>{t("Media spend", "Dépense média")}</dt>
                  <dd>{money(s.mean_spend_cents, curr, lang)}</dd>
                </div>
                <div>
                  <dt>CAC</dt>
                  <dd>
                    {s.mean_cac_cents == null
                      ? "—"
                      : money(s.mean_cac_cents, curr, lang)}
                  </dd>
                </div>
              </dl>
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}
