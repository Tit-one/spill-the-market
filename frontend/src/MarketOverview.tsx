import { useId } from "react";
import type { Lang } from "./types";
import type { MarketAnalysis } from "./marketTypes";
import { channelNames, money, number, percent, safeURL } from "./utils";
import "./MarketOverview.css";

export default function MarketOverview({
  report: r,
  lang,
  currency,
}: {
  report: MarketAnalysis;
  lang: Lang;
  currency: string;
}) {
  const headingId = useId();
  const t = (en: string, fr: string) => (lang === "fr" ? fr : en);
  const num = (value?: number | null) =>
    number(typeof value === "number" ? value : undefined, lang, 3);
  const pct = (value?: number) => percent(value, lang);
  const channelName = (channel: string) => {
    const french: Record<string, string> = {
      search: "Recherche",
      creators: "Créateurs",
      communities: "Communautés",
      display: "Publicité display",
      newsletter: "Newsletter",
      in_game: "Dans un jeu",
      affiliate: "Affiliation",
    };
    return (
      (lang === "fr" && french[channel]) ||
      channelNames[channel] ||
      channel.replaceAll("_", " ")
    );
  };
  const sources = r.sources ?? [];
  const sourceMap = new Map(sources.map((s) => [s.id, s]));
  const referenceSources = (ids: string[] = []) =>
    ids.map((id) => sourceMap.get(id));
  const isFictional = (kind = "") => /demo|fictional|synthetic/i.test(kind);
  const sourceRefs = (ids: string[] = []) =>
    ids.length > 0 ? (
      <small className="market-source-refs">
        {t("Sources", "Sources")} :{" "}
        {referenceSources(ids)
          .map(
            (s) =>
              s?.title ||
              (s ? s.id : t("Source unavailable", "Source indisponible")),
          )
          .join(" · ")}
      </small>
    ) : null;
  const competitorStatus = (
    competitor: NonNullable<MarketAnalysis["competitors"]>[number],
  ) => {
    const referenced = referenceSources(competitor.source_ids);
    if (
      isFictional(competitor.evidence_status) ||
      referenced.some((s) => isFictional(s?.kind))
    )
      return t("Fictional reference", "Référence fictive");
    if (
      /source_statement|source_backed|documented|sourced|observed|source_excerpt/i.test(
        competitor.evidence_status ?? "",
      ) &&
      referenced.some((s) => !!s && !isFictional(s.kind))
    )
      return t("Documented reference", "Référence documentée");
    return competitor.url
      ? t("Supplied URL — content not read", "URL fournie — contenu non lu")
      : t("Unverified reference", "Référence non documentée");
  };
  const segments = r.segment_recommendation?.segments ?? [];
  const channels = r.channel_recommendation?.channels ?? [];
  const noSegmentSales =
    segments.length > 0 && segments.every((s) => s.units === 0);
  const noChannelSales =
    channels.length > 0 && channels.every((c) => c.units === 0);
  const segment = r.segment_recommendation;
  const channel = r.channel_recommendation;
  const hasAgeHypothesis =
    segment?.status === "hypothesis" &&
    typeof segment.age_min === "number" &&
    typeof segment.age_max === "number" &&
    segments.some((s) => (s.units ?? 0) > 0);
  const hasChannelHypothesis =
    channel?.status === "hypothesis" &&
    !!channel?.channel &&
    channels.some((c) => (c.units ?? 0) > 0);
  const switching = r.switching;
  const projection = switching?.market_projection;
  const status =
    r.status === "demo"
      ? t(
          "Fictional demonstration — no real market measured.",
          "Démonstration fictive — aucun marché réel mesuré.",
        )
      : r.status === "evidence_informed_simulation" &&
          r.coverage?.real_source_count !== 0
        ? t(
            "Source-informed simulation — real demand not measured.",
            "Simulation éclairée par des sources — demande réelle non mesurée.",
          )
        : r.status
          ? t(
              "Simulation hypotheses — no real source collected.",
              "Hypothèses de simulation — aucune source réelle collectée.",
            )
          : t(
              "No market conclusion is available for this older report.",
              "Aucune conclusion de marché disponible pour cet ancien rapport.",
            );
  const date = (value?: string | null) => {
    const parsed = value ? new Date(value) : null;
    return parsed && Number.isFinite(parsed.getTime())
      ? parsed.toLocaleDateString(lang)
      : t("unknown", "inconnue");
  };
  return (
    <section className="market-overview" aria-labelledby={headingId}>
      <header className="market-overview-header">
        <h2 id={headingId}>
          {t(
            "What the market exploration suggests",
            "Ce que l’exploration de marché suggère",
          )}
        </h2>
        <p>
          {t(
            "Directions to test, not measured real-world demand.",
            "Des pistes à tester, pas une demande réelle mesurée.",
          )}
        </p>
      </header>
      <div className="market-evidence-status" role="note">
        <strong>{status}</strong>
        <div className="market-coverage">
          <span>
            {t("Real sources", "Sources réelles")} :{" "}
            {num(r.coverage?.real_source_count)}
          </span>
          <span>
            {t("Competitor references", "Références concurrentes")} :{" "}
            {num(r.coverage?.competitor_reference_count)}
          </span>
          <span>
            {t("Market size: unknown", "Taille du marché : inconnue")}
          </span>
        </div>
      </div>
      <div className="market-directions">
        <section>
          <span className="market-direction-label">
            {t("Audience hypothesis", "Hypothèse de public")}
          </span>
          <h3>
            {hasAgeHypothesis
              ? t(
                  `Ages ${segment!.age_min}–${segment!.age_max} to test`,
                  `${segment!.age_min}–${segment!.age_max} ans à tester`,
                )
              : t("No age group stands out", "Aucun âge ne se détache")}
          </h3>
          <p>
            {hasAgeHypothesis && segment?.reason
              ? segment.reason
              : noSegmentSales
                ? t(
                    "No simulated purchase in the sampled age groups. This does not establish which ages would buy in real life.",
                    "Aucun achat simulé dans les âges échantillonnés. Cela ne permet pas d’identifier des acheteurs réels par âge.",
                  )
                : t(
                    "The available results do not support an age recommendation.",
                    "Les résultats disponibles ne permettent pas de retenir une tranche d’âge.",
                  )}
          </p>
        </section>
        <section>
          <span className="market-direction-label">
            {t("Channel hypothesis", "Hypothèse de canal")}
          </span>
          <h3>
            {hasChannelHypothesis
              ? t(
                  `${channelName(channel!.channel!)} to test`,
                  `${channelName(channel!.channel!)} à tester`,
                )
              : t("No channel stands out", "Aucun canal ne se détache")}
          </h3>
          <p>
            {hasChannelHypothesis && channel?.reason
              ? channel.reason
              : noChannelSales
                ? t(
                    "No simulated purchase is attributed to these channels. Visibility alone does not establish sales potential.",
                    "Aucun achat simulé n’est attribué à ces canaux. La visibilité seule ne démontre pas un potentiel de vente.",
                  )
                : t(
                    "The available results do not support a channel recommendation.",
                    "Les résultats disponibles ne permettent pas de retenir un canal.",
                  )}
          </p>
        </section>
      </div>
      <section className="market-competitors">
        <h3>{t("Competitor references", "Les références concurrentes")}</h3>
        <p className="market-explanation">
          {t(
            "A reference or a supplied URL does not establish a complete competitor landscape.",
            "Une référence ou une URL fournie ne constitue pas un panorama complet de la concurrence.",
          )}
        </p>
        {r.competitors?.length ? (
          <ul>
            {r.competitors.map((competitor, index) => {
              const url = safeURL(competitor.url ?? null);
              return (
                <li key={`${competitor.name}-${index}`}>
                  <div className="market-competitor-heading">
                    <strong>
                      {competitor.name ||
                        t("Unnamed reference", "Référence sans nom")}
                    </strong>
                    <span>{competitorStatus(competitor)}</span>
                  </div>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer">
                      {t("Open reference", "Ouvrir la référence")} ↗
                    </a>
                  )}
                  {competitor.excerpts?.length ? (
                    <details>
                      <summary>
                        {t(
                          "Read the supplied excerpts",
                          "Lire les extraits fournis",
                        )}
                      </summary>
                      {competitor.excerpts.map((excerpt, i) => (
                        <blockquote key={i}>{excerpt}</blockquote>
                      ))}
                    </details>
                  ) : null}
                  {sourceRefs(competitor.source_ids)}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="market-empty">
            {t(
              "No competitor reference supplied. This does not mean there is no competition.",
              "Aucune référence concurrente renseignée. Cela ne signifie pas qu’il n’existe aucune concurrence.",
            )}
          </p>
        )}
      </section>
      {r.barriers?.length ? (
        <section className="market-barriers">
          <h3>{t("Barriers to check", "Les freins à vérifier")}</h3>
          <ul>
            {r.barriers.map((barrier, i) => (
              <li key={i}>
                <strong>
                  {barrier.title || t("Possible barrier", "Frein possible")}
                </strong>
                <p>
                  {barrier.detail ||
                    t("No detail supplied.", "Aucun détail renseigné.")}
                </p>
                {sourceRefs(barrier.source_ids)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section
        className="market-switching"
        aria-label={t("Simulated switching", "Changement de solution simulé")}
      >
        <h3>
          {t(
            "Would existing users switch solutions?",
            "Des utilisateurs changeraient-ils de solution ?",
          )}
        </h3>
        {switching?.enabled ? (
          <>
            <p className="market-explanation">
              {t(
                `Simulation averages over ${num(switching.population)} people; these are not observed customer counts.`,
                `Moyennes de simulation sur ${num(switching.population)} personnes ; ce ne sont pas des clients observés.`,
              )}
            </p>
            <dl className="market-switching-values">
              <div>
                <dt>{t("Switch solutions", "Changent de solution")}</dt>
                <dd>{num(switching.switchers)}</dd>
              </div>
              <div>
                <dt>
                  {t("New to the category", "Nouveaux dans la catégorie")}
                </dt>
                <dd>{num(switching.new_to_category_buyers)}</dd>
              </div>
              <div>
                <dt>
                  {t(
                    "Keep their existing solution",
                    "Gardent leur solution actuelle",
                  )}
                </dt>
                <dd>{num(switching.retained_incumbents)}</dd>
              </div>
            </dl>
            {projection ? (
              <div className="market-projection">
                <strong>
                  {t(
                    "Unvalidated extrapolation — not a market forecast",
                    "Extrapolation non validée — pas une prévision de marché",
                  )}
                </strong>
                <p>
                  {t(
                    "Assumed addressable population",
                    "Population adressable supposée",
                  )}{" "}
                  : {num(projection.addressable_population)} ·{" "}
                  {t(
                    "Projected switchers",
                    "Changements de solution extrapolés",
                  )}{" "}
                  : {num(projection.estimated_switchers)}
                </p>
              </div>
            ) : (
              <p className="market-explanation">
                {t(
                  "Actual market size is unknown — no extrapolation to the real market.",
                  "La taille réelle du marché est inconnue — aucune extrapolation au marché réel.",
                )}
              </p>
            )}
            <details>
              <summary>
                {t(
                  "Switching assumptions and population detail",
                  "Hypothèses de changement et détail de population",
                )}
              </summary>
              <dl className="market-assumptions">
                <div>
                  <dt>
                    {t("Existing category users", "Utilisateurs déjà équipés")}
                  </dt>
                  <dd>{num(switching.incumbent_users)}</dd>
                </div>
                <div>
                  <dt>{t("Not yet equipped", "Personnes non équipées")}</dt>
                  <dd>{num(switching.non_incumbent_users)}</dd>
                </div>
                <div>
                  <dt>{t("Virtual buyers", "Acheteurs virtuels")}</dt>
                  <dd>{num(switching.buyers)}</dd>
                </div>
                <div>
                  <dt>
                    {t(
                      "Non-buyers new to the category",
                      "Non-acheteurs non équipés",
                    )}
                  </dt>
                  <dd>{num(switching.new_to_category_nonbuyers)}</dd>
                </div>
                <div>
                  <dt>
                    {t("Assumed incumbent share", "Part déjà équipée supposée")}
                  </dt>
                  <dd>{pct(switching.incumbent_share)}</dd>
                </div>
                <div>
                  <dt>
                    {t(
                      "Assumed switching friction",
                      "Friction de changement supposée",
                    )}
                  </dt>
                  <dd>{pct(switching.switching_friction)}</dd>
                </div>
                <div>
                  <dt>
                    {t(
                      "Mean model acceptance",
                      "Acceptation moyenne du modèle",
                    )}
                  </dt>
                  <dd>{pct(switching.mean_switching_acceptance)}</dd>
                </div>
              </dl>
              {switching.assumptions?.length ? (
                <ul>
                  {switching.assumptions.map((assumption, i) => (
                    <li key={i}>{assumption}</li>
                  ))}
                </ul>
              ) : (
                <p>
                  {t(
                    "Switching assumptions were not supplied.",
                    "Les hypothèses de changement ne sont pas renseignées.",
                  )}
                </p>
              )}
            </details>
          </>
        ) : (
          <p className="market-empty">
            {t(
              "Switching was not simulated. No competitor-customer capture estimate is available.",
              "Le changement de solution n’a pas été simulé. Aucune estimation de conquête de clients concurrents n’est disponible.",
            )}
          </p>
        )}
      </section>
      {r.next_actions?.length ? (
        <section className="market-next-actions">
          <h3>{t("What to verify next", "À vérifier ensuite")}</h3>
          <ol>
            {r.next_actions.map((action, i) => (
              <li key={i}>
                <strong>
                  {action.title || t("Next step", "Prochaine étape")}
                </strong>
                {action.detail && <p>{action.detail}</p>}
                {sourceRefs(action.source_ids)}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <details className="market-disclosure">
        <summary>
          {t(
            "Age and channel results in detail",
            "Résultats par âge et par canal en détail",
          )}
        </summary>
        <p className="market-explanation">
          {t(
            "Conditional simulation averages, not survey results. Groups and channel attribution depend on the chosen scenario.",
            "Moyennes de simulation conditionnelles, pas des résultats de sondage. Les groupes et l’attribution par canal dépendent du scénario retenu.",
          )}
        </p>
        {segments.length ? (
          <div
            className="market-table-scroll"
            role="region"
            aria-label={t(
              "Age segment results",
              "Résultats des tranches d’âge",
            )}
            tabIndex={0}
          >
            <table>
              <caption>
                {t("Sampled age groups", "Âges échantillonnés")}
              </caption>
              <thead>
                <tr>
                  <th>{t("Ages", "Âges")}</th>
                  <th>{t("Population", "Population")}</th>
                  <th>{t("Virtual purchases", "Achats virtuels")}</th>
                  <th>{t("Organic purchases", "Achats organiques")}</th>
                  <th>{t("Conversion", "Conversion")}</th>
                  <th>{t("Virtual revenue", "CA virtuel")}</th>
                </tr>
              </thead>
              <tbody>
                {segments.map((s, i) => (
                  <tr key={i}>
                    <th>
                      {s.age_min}–{s.age_max}
                    </th>
                    <td>{num(s.population)}</td>
                    <td>{num(s.units)}</td>
                    <td>{num(s.organic_units)}</td>
                    <td>{pct(s.conversion_rate)}</td>
                    <td>{money(s.revenue_cents, currency, lang)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>
            {t(
              "No age-segment detail supplied.",
              "Aucun détail par âge renseigné.",
            )}
          </p>
        )}
        {channels.length ? (
          <div
            className="market-table-scroll"
            role="region"
            aria-label={t("Channel results", "Résultats par canal")}
            tabIndex={0}
          >
            <table>
              <caption>
                {t(
                  "Simulated channel attribution",
                  "Attribution simulée par canal",
                )}
              </caption>
              <thead>
                <tr>
                  <th>{t("Channel", "Canal")}</th>
                  <th>{t("Unique reach", "Portée unique")}</th>
                  <th>{t("Virtual purchases", "Achats virtuels")}</th>
                  <th>{t("Conversion", "Conversion")}</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((c, i) => (
                  <tr key={i}>
                    <th>
                      {c.channel
                        ? channelName(c.channel)
                        : t("Unspecified", "Non renseigné")}
                    </th>
                    <td>{num(c.unique_reach)}</td>
                    <td>{num(c.units)}</td>
                    <td>
                      {pct(c.attributed_conversion_rate ?? c.conversion_rate)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>
            {t(
              "No channel detail supplied.",
              "Aucun détail par canal renseigné.",
            )}
          </p>
        )}
        {(segment?.based_on_plan || channel?.based_on_plan) && (
          <p className="market-explanation">
            {t("Scenario references", "Scénarios de référence")} :{" "}
            {segment?.based_on_plan ?? "—"} · {channel?.based_on_plan ?? "—"}
          </p>
        )}
      </details>
      <details className="market-disclosure">
        <summary>
          {t(
            "Sources and limits of this exploration",
            "Sources et limites de l’exploration",
          )}
        </summary>
        {sources.length ? (
          <ul className="market-source-list">
            {sources.map((source) => {
              const url = safeURL(source.url ?? null);
              return (
                <li key={source.id}>
                  <strong>
                    {url ? (
                      <a href={url} target="_blank" rel="noreferrer">
                        {source.title || source.id} ↗
                      </a>
                    ) : (
                      source.title || source.id
                    )}
                  </strong>
                  <p>
                    {t("Retrieved", "Collectée le")} :{" "}
                    {date(source.retrieved_at)} · {t("Published", "Publiée le")}{" "}
                    : {date(source.published_at)}
                  </p>
                  {isFictional(source.kind) && (
                    <span>{t("Fictional source", "Source fictive")}</span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : (
          <p>
            {t(
              "No source supplied. Market facts remain unknown.",
              "Aucune source renseignée. Les faits de marché restent inconnus.",
            )}
          </p>
        )}
        {r.limitations?.length ? (
          <ul>
            {r.limitations.map((limit, i) => (
              <li key={i}>{limit}</li>
            ))}
          </ul>
        ) : null}
        <p>
          {t(
            "These assumptions do not establish market size, actual demand or real-world switching probability. Confirm the product claims and test demand with real people.",
            "Ces hypothèses n’établissent ni la taille du marché, ni la demande réelle, ni une probabilité observée de changement. Vérifiez les promesses du produit et testez la demande auprès de personnes réelles.",
          )}
        </p>
      </details>
    </section>
  );
}
