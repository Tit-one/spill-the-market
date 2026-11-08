"""Offline triage of affirmative extraordinary product promises, not fact checking.

The numerical scores are editable model assumptions. A detected claim is never
declared false or fraudulent; marketing copy and unverified research snippets
cannot establish its truth. No age or population attribute enters these rules.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from .models import ProductSpec, TrendReport

VERSION = "1.0"
Status = Literal["ordinary", "needs_evidence", "extraordinary_unsubstantiated"]


class _Overrides(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    status: Status | None = None
    score: float | None = Field(default=None, ge=0, le=1, strict=True)
    scam_suspicion: float | None = Field(default=None, ge=0, le=1, strict=True)
    reason: str = Field(default="Explicit owner sensitivity scenario", min_length=1, max_length=1000)


def _fold(text):
    text = str(text).casefold().replace("’", "'").replace("‘", "'").replace("–", "-")
    text = "".join(character for character in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(character))
    for contraction, expanded in (("doesn't", "does not"), ("don't", "do not"), ("won't", "will not"),
                                  ("can't", "cannot"), ("isn't", "is not"), ("aren't", "are not")):
        text = text.replace(contraction, expanded)
    return re.sub(r"\s+", " ", text).strip()


def _plain(text):
    soup = BeautifulSoup(text, "html.parser")
    for element in soup(["script", "style", "template", "noscript"]):
        element.decompose()
    return soup.get_text(" ", strip=True)


@dataclass(frozen=True)
class _Rule:
    kind: str
    pattern: str
    score: float
    suspicion: float


_RULES = (
    _Rule("immortality", r"\b(?:immortalit[ey]|immortali?te|immortals?|immortel(?:le)?s?|"
          r"eternal life|vie eternelle|live forever|vivre (?:eternellement|pour toujours)|never die)\b", .04, .92),
    _Rule("cure_all", r"\b(?:(?:cure\w*|heal\w*|treat\w*)\s+(?:all|every|any)\s+(?:diseases?|illness\w*|conditions?)|"
          r"gueri\w*\s+(?:toutes?\s+les?|n'importe quelle)\s+(?:maladies?|affections?)|"
          r"cure[- ]all|universal cure|remede universel)\b", .08, .90),
    _Rule("guaranteed_returns", r"\b(?:(?:guarantee\w*|certain|risk[- ]free)\s+(?:\w+\s+){0,3}"
          r"(?:returns?|profits?|earnings?|income)|(?:returns?|profits?|rendements?|gains?|revenus?)\s+"
          r"(?:\w+\s+){0,2}(?:guarantee\w*|garanti\w*)|(?:invest\w*|returns?|profits?|rendements?|gains?)"
          r".{0,100}(?:no risk|without (?:any )?risk|zero risk|sans (?:aucun )?risque))\b", .12, .84),
    _Rule("unbounded_physical_performance", r"\b(?:perpetual motion|mouvement perpetuel|"
          r"(?:unlimited|infinite) energy.{0,100}(?:without|no).{0,30}(?:fuel|input)|"
          r"energie (?:illimitee|infinie).{0,100}sans.{0,30}(?:carburant|apport|energie))\b", .08, .88),
    _Rule("absolute_outcome_guarantee", r"\b(?:(?:guarantee\w*|garanti\w*)\s+(?:\w+\s+){0,3}"
          r"(?:success|succes|reussite|results? for everyone)|(?:100\s*%|perfect|parfait\w*)\s+"
          r"(?:accuracy|precision|prediction\w*).{0,80}(?:always|every|all|toujours|tous|toutes)|"
          r"(?:works?|fonctionne)\s+(?:for everyone|pour tout le monde).{0,50}(?:no exceptions?|sans exception))\b", .45, .35),
)

_ASSERTION = re.compile(r"\b(?:promis\w*|promet\w*|garanti\w*|guarantee\w*|grant\w*|offer\w*|offr\w*|"
                         r"makes?|allow\w*|rend\w*|permet\w*|devien\w*|become\w*|cure\w*|gueri\w*|"
                         r"will|vous|your|votre|miracle|pill|pilule|supplement|remede|produit)\b")
_REAL_TARGET = re.compile(r"\b(?:real[- ]life|real world|vraie vie|votre corps|your body|human\w*|humain\w*|"
                           r"pill|pilule|supplement|medical\w*|medicin\w*|remede|treatment|traitement|"
                           r"invest\w*|profits?|rendements?|gains? financiers)\b")
_TOPIC = re.compile(r"\b(?:about|discuss\w*|tracks?|analyse\w*|analyz\w*|sur la quete|au sujet|"
                      r"research whether|study whether|research into|etudie si|recherche sur|named|called|nomm\w*|appel\w*)\b")
_COUNTER_PREDICATE = re.compile(r"\b(?:debunk\w*|critique\w*|denonc\w*|refut\w*|examin\w*|analy[sz]\w*)\b")
_COUNTER_OBJECT = re.compile(r"\b(?:claims?|promess\w*|publicit\w*|advertise\w*|notions?|"
                             r"myths? of|mythes? de)\b")
_TENTATIVE = re.compile(r"\b(?:may|might|could|aim\w*|hope\w*|hypothes\w*|eventually|potential\w*|"
                          r"peut-etre|pourrait|esper\w*|vise\w*|a terme)\b")
_ABSOLUTE = re.compile(r"\b(?:guarantee\w*|garanti\w*|100\s*%|sans (?:aucun )?risque|no risk|risk[- ]free)\b")

# Split independent clauses, not a list of effects sharing one predicate. An
# auxiliary negation can consequently govern unfamiliar verbs without leaking
# across "while our ...", "mais ...", or another independently stated claim.
_CLAUSE_BOUNDARY = re.compile(
    r"\b(?:mais|but|however|pourtant|yet|while|whereas|tandis\s+que|alors\s+que|because|parce\s+que|puisque)\b|"
    r"\b(?:et|and)\b(?=\s+(?:our|my|their|this|that|it|we|the|a|an|notre|nos|ce|cet|cette|il|elle|nous|un|une|ne|n')\b)|[,;:]",
    re.IGNORECASE)
_NARRATIVE_ACTOR = re.compile(r"\b(?:characters?|personnages?|avatars?|fictional heroes?|heros fictifs?)\b")
_EXPLICIT_WORLD = re.compile(
    r"\b(?:in[- ]game|game (?:item|world|mechanic)|"
    r"(?:in|within|inside)\s+(?:(?:this|the|a|fictional|fantasy|adventure)\s+){0,4}(?:game|story|novel|world)|"
    r"dans\s+(?:(?:ce|le|un|cet|l')\s*)?(?:jeu|roman|recit|univers|monde)|"
    r"objet\s+(?:du|de ce)\s+jeu)\b")
_REAL_WORLD = re.compile(r"\b(?:real[- ]life|real world|in reality|vraie vie|dans la realite|actual human body)\b")


def _clauses(sentence_raw):
    start, inherited_world = 0, False
    for boundary in _CLAUSE_BOUNDARY.finditer(sentence_raw):
        raw = sentence_raw[start:boundary.start()]
        if raw.strip():
            yield raw, inherited_world
        # Only an explicit world-setting prefix carries across punctuation.
        # Merely mentioning an included game or "game-inspired" does not.
        inherited_world = (boundary.group(0) in {",", ":"} and bool(_EXPLICIT_WORLD.search(_fold(raw))))
        start = boundary.end()
    raw = sentence_raw[start:]
    if raw.strip():
        yield raw, inherited_world


def _negation_scope(clause, match_start):
    prefix = clause[max(0, match_start - 180):match_start]
    if re.search(r"\b(?:not only|not just|pas seulement)\b", prefix):
        return None
    if re.search(r"\bnot\s+(?:impossible|incapable|unable|unlikely|false)|\b(?:does not|cannot)\s+fail\b|"
                 r"\bpas\s+(?:impossible|incapable|faux)\b", prefix):
        return "ambiguous"
    operators = list(re.finditer(r"\b(?:(?:do|does|did|is|are|was|were|has|have|will|would|can|could|should|may|might)\s+not|cannot|never)\b", prefix))
    operators += list(re.finditer(r"\b(?:ne\s+|n')(?:(?:[\w'-]+)\s+){0,8}(?:pas|jamais|personne|rien|aucun\w*|nul\w*)\b", prefix))
    if operators and len(re.findall(r"[\w'-]+", prefix[max(operator.end() for operator in operators):])) <= 12:
        return "negated"
    if re.search(r"\bno\s+(?:[\w'-]+\s+){1,4}(?:can|will|could)\b", prefix) and not re.search(r"\bno (?:risk|doubt)\b", prefix):
        return "negated"
    if re.search(r"\b(?:sans|aucune?|no)\s+(?:une?\s+)?(?:promess\w*|garanti\w*)\b", prefix):
        return "negated"
    if re.search(r"\b(?:not|no|without)\s+(?:an?\s+)?$", prefix):
        return "negated"
    if re.search(r"(?:n'est|ne (?:sont|sera|seront)|is|are)\s+(?:pas|not)\s+(?:an?|un|une)?\s*$", prefix):
        return "negated"
    return None


def _fiction_governs(clause, match_start, inherited_world):
    if _REAL_WORLD.search(clause):
        return False
    if inherited_world or _EXPLICIT_WORLD.search(clause):
        return True
    for actor in _NARRATIVE_ACTOR.finditer(clause):
        actor_prefix = clause[:actor.start()]
        # A comparison to fictional people does not make the promised recipient
        # fictional. Keep actual narrative subjects and explicit effect targets.
        if re.search(r"\b(?:like|as|comme|a l'image de|a la maniere de)\s+(?:[\w'-]+\s+){0,4}$", actor_prefix):
            continue
        if actor.end() <= match_start or re.search(
                r"\b(?:to|for|of|a|au|aux|pour|de|des)\s+"
                r"(?:(?:a|an|the|le|la|les|un|une|des|our|your|its|son|sa|ses|votre|player|fictional|fictif\w*)\s+){0,4}$",
                actor_prefix):
            return True
    # A narrative noun immediately governing a topic/effect is different from
    # an adjective such as "game-inspired" modifying a real bracelet.
    prefix = clause[:match_start]
    return bool(re.search(r"\b(?:game|jeu|roman|novel|story|recit)\b(?![-])\s+(?:[\w']+\s+){0,1}$", prefix))


def _counter_governs(clause, match_start):
    prefix = clause[:match_start]
    for predicate in _COUNTER_PREDICATE.finditer(prefix):
        complement = prefix[predicate.end():]
        if len(complement) <= 160 and (_COUNTER_OBJECT.search(complement) or
                re.fullmatch(r"[\s'\"«»]*(?:(?:the|a|of|de|des|du|la|le|les|l')\s*)?[\s'\"«»]*", complement)):
            return True
    return bool(re.search(r"\b(?:false claims?|fausses promesses)\s+(?:of|de|d')?\s*$", prefix))


def _claim_scope(clause, match, kind, inherited_world):
    if _counter_governs(clause, match.start()):
        return "excluded"
    negation = _negation_scope(clause, match.start())
    if negation:
        return "excluded" if negation == "negated" else "ambiguous"
    if (kind == "immortality" and match.group(0) in {"immortelle", "immortelles"}
            and re.search(r"\b(?:fleur\w*|huile\w*|extrait\w*|extract\w*|plante\w*|cosmetique|botani\w*)\b", clause)
            and not re.search(r"\b(?:rend\w*|makes?|devi\w*|grant\w*|promet\w*)\b", clause)):
        return "excluded"
    if (kind == "immortality" and re.fullmatch(r"immortals?|immortel(?:le)?s?", match.group(0))
            and re.search(r"\b(?:memories|souvenirs?|artworks?|photos?|brands?|marques?|oeuvres?)\b", clause)
            and not _REAL_TARGET.search(clause) and not re.search(r"\b(?:you|vous)\b", clause)):
        return "excluded"
    if _fiction_governs(clause, match.start(), inherited_world):
        return "excluded"
    prefix = clause[:match.start()]
    if _TOPIC.search(prefix) and not re.search(r"\b(?:promis\w*|promet\w*|guarantee\w*|garanti\w*|grant\w*)\b", prefix):
        return "excluded"
    if kind == "absolute_outcome_guarantee" and re.search(
            r"\b(?:warrant\w*|money[- ]back|rembours\w*|livraison|delivery|sla)\b", clause):
        return "excluded"
    if kind == "immortality" and not _ASSERTION.search(clause):
        # A short affirmative predicate followed by its article/object is a
        # generic grammatical pattern, not another list of verb exceptions.
        if re.fullmatch(r"[a-z]+\s+(?:l'|la\s+|le\s+|les\s+|an?\s+|the\s+)\s*", prefix):
            return "affirmed"
        return "ambiguous"
    return "affirmed"


_EVIDENCE = {
    "immortality": ("Define bounded measurable outcomes and provide independently auditable, product-specific evidence; an indefinite promise is not established by marketing wording.",
                    "Définir des résultats bornés et mesurables, avec des éléments indépendants propres au produit ; une promesse indéfinie n'est pas établie par son texte marketing."),
    "cure_all": ("Provide independent product-specific efficacy evidence, explicit scope, limitations, uncertainty and reproducible evaluation.",
                 "Fournir des éléments indépendants d'efficacité propres au produit, avec périmètre, limites, incertitudes et évaluation reproductible."),
    "guaranteed_returns": ("Provide independently auditable outcome/risk records and the exact guarantee terms, exclusions and responsible guarantor.",
                           "Fournir un historique de résultats et risques auditable indépendamment, ainsi que les conditions, exclusions et responsable de la garantie."),
    "unbounded_physical_performance": ("Provide independent reproducible measurements, complete input/output accounting and bounded operating conditions.",
                                       "Fournir des mesures indépendantes reproductibles, un bilan complet des entrées/sorties et des conditions de fonctionnement bornées."),
    "absolute_outcome_guarantee": ("Specify the outcome, eligible conditions, failure cases, guarantee terms and independent product-specific support.",
                                   "Préciser le résultat, les conditions applicables, les cas d'échec, les termes de garantie et les éléments indépendants propres au produit."),
}


def assess_product_credibility(product: ProductSpec | dict, research: TrendReport | None = None,
                               overrides: dict | None = None) -> dict:
    """Return JSON-ready risk priors without treating a product brief as verified truth.

    `score` means an illustrative credibility prior, not the probability a claim
    is true; `scam_suspicion` is hypothetical consumer suspicion, not a fraud
    finding. Ordinary products receive no extraordinary-claim evidence label.
    Overrides may change those priors/status for sensitivity analysis, but can
    never mark a claim's evidence as verified.
    """
    product = ProductSpec.model_validate(product)
    edited = _Overrides.model_validate(overrides) if overrides is not None else None
    if research is not None:
        TrendReport.model_validate(research)  # Validate provenance shape; marketing text is not verification.
    sources = [_plain(product.name), _plain(product.description)]
    french = bool(re.search(r"\b(?:produit|promet\w*|immortali?te|gueri\w*|rendement|garanti\w*)\b", _fold(product.description)))
    claims, risks, required, seen = [], [], [], set()
    for source in sources:
        sentences = re.split(r"(?<=[.!?;])\s+|[\r\n]+", source)
        for sentence_raw in sentences:
            for clause_raw, inherited_world in _clauses(sentence_raw):
                clause = _fold(clause_raw)
                for rule in _RULES:
                    matches = [(match, _claim_scope(clause, match, rule.kind, inherited_world))
                               for match in re.finditer(rule.pattern, clause)]
                    scopes = [scope for _, scope in matches if scope != "excluded"]
                    if not scopes:
                        continue
                    key = (rule.kind, clause)
                    if key in seen:
                        continue
                    seen.add(key)
                    tentative = bool(_TENTATIVE.search(clause)) and not _ABSOLUTE.search(clause)
                    qualified_return = (rule.kind == "guaranteed_returns" and bool(re.search(
                        r"\b(?:insured|assure|deposit|depot|savings|epargne|fixed[- ]term|taux fixe)\b", clause))
                        and not re.search(r"\b(?:every month|per month|par mois|no risk|sans (?:aucun )?risque)\b", clause))
                    ambiguous = "affirmed" not in scopes
                    moderate = tentative or qualified_return or ambiguous or rule.kind == "absolute_outcome_guarantee"
                    score, suspicion = (.6, .2) if tentative or qualified_return or ambiguous else (rule.score, rule.suspicion)
                    reason = (("Promesse ou objectif à étayer : aucune vérification indépendante n'est effectuée par ce triage." if moderate else
                               "Promesse extraordinaire sans preuve indépendante vérifiée fournie ; scepticisme et soupçon sont des hypothèses de simulation, pas un verdict de fraude.")
                              if french else ("Claim or aspiration needs support; this triage performs no independent verification." if moderate else
                               "Extraordinary promise without independently verified support supplied; skepticism/suspicion are model assumptions, not a fraud verdict."))
                    claims.append({"text": clause_raw.strip()[:1000], "kind": rule.kind,
                                   "evidence_status": "unsubstantiated", "reason": reason})
                    risks.append((score, suspicion, not moderate))
                    evidence = _EVIDENCE[rule.kind][1 if french else 0]
                    if evidence not in required:
                        required.append(evidence)
    if claims:
        status = "extraordinary_unsubstantiated" if any(extraordinary for _, _, extraordinary in risks) else "needs_evidence"
        score = min(value for value, _, _ in risks)
        suspicion = max(value for _, value, _ in risks)
        reasons = [claim["reason"] for index, claim in enumerate(claims) if claim["reason"] not in [item["reason"] for item in claims[:index]]]
    else:
        status, score, suspicion = "ordinary", .8, .05
        reasons = ["Aucune promesse extraordinaire affirmative détectée ; cela ne vérifie ni l'efficacité ni la légitimité du produit." if french else
                   "No affirmative extraordinary promise matched; this does not verify the product's efficacy or legitimacy."]
    assumptions = ([
        "Les scores sont des hypothèses éditables, pas des taux observés de fraude, de vérité ou d'achat.",
        "Aucune vérification scientifique ou juridique n'est effectuée ; les règles peuvent manquer du contexte.",
        "Un texte marketing, une citation ou un extrait de recherche ne constitue pas une preuve indépendante vérifiée.",
        "L'âge n'intervient pas dans ce triage ; le scepticisme individuel doit varier séparément.",
        "Les mots-clés ne peuvent pas transformer une promesse réelle en fiction ni valider ses bénéfices."] if french else [
        "Scores are editable model assumptions, not observed rates of deception, truth or purchasing.",
        "No scientific or legal fact verification is performed; lexical rules can miss context.",
        "Marketing wording, quotations and research snippets are not independently verified evidence.",
        "Age is not used in this triage; individual skepticism must vary separately.",
        "Product keywords cannot turn a real-world promise into fiction or validate its benefits."])
    result = {"status": status, "score": score, "scam_suspicion": suspicion, "claims": claims,
              "reasons": reasons, "assumptions": assumptions, "required_evidence": required,
              "source": "rule_based", "version": VERSION}
    if overrides:
        for field in ("status", "score", "scam_suspicion"):
            value = getattr(edited, field)
            if value is not None:
                result[field] = value
        result["assumptions"].append("Explicit owner override (unverified simulation assumption): " + edited.reason)
    return result
