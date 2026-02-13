"""pipeline/pipeline_core/strategy_planner.py — Strategic Research Decomposition Engine.

Transforms a natural language research prompt into a structured multi-layer
search strategy through systematic intellectual decomposition.

PROCESS:
  1. ANALYZE: Extract WHO/WHERE/WHAT (explicit, implicit, rejections)
  2. STRATEGIZE: Generate 3 strategy tiers (direct, semi-direct, indirect)
  3. DECOMPOSE: Break each strategy into hierarchical sub-steps
  4. GENERATE: Produce concrete search queries for each step
  5. PRIORITIZE: Assign cost/value estimates for the CostEngine

The decomposition follows a rigorous intellectual procedure:
  - Explicit = directly stated in the prompt
  - Implicit = logically deduced (stakeholders, intermediaries, artifacts)
  - Rejection = what to explicitly exclude
  - Each implicit element opens a new research branch

Generic: works for any research domain, not just YouTube/manga.

Usage:
    planner = StrategyPlanner(llm_func=query_llm)
    plan = await planner.analyze("recherche moi tous les mangakas americains professionnels")
    # plan contains full WHO/WHERE/WHAT analysis + strategy tree
    
    strategies = await planner.build_strategies(plan)
    # strategies = [{name, tier, steps: [{action, queries, sub_steps}]}]
    
    queries = planner.flatten_queries(strategies)
    # All concrete queries ready for the search engine
"""
import json
import time
from typing import List, Dict, Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from pathlib import Path

from config.settings import BASE_DIR


# ══════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════

@dataclass
class Dimension:
    """One dimension of analysis (WHO, WHERE, or WHAT)."""
    explicit: List[str] = field(default_factory=list)       # Directly stated
    explicit_refined: List[str] = field(default_factory=list)  # Refined/expanded explicit
    implicit: List[str] = field(default_factory=list)       # Logically deduced
    rejections: List[str] = field(default_factory=list)     # Explicitly excluded

    def to_dict(self):
        return asdict(self)


@dataclass
class AnalysisResult:
    """Full WHO/WHERE/WHAT decomposition of a prompt."""
    prompt: str = ""
    who: Dimension = field(default_factory=Dimension)
    where: Dimension = field(default_factory=Dimension)
    what: Dimension = field(default_factory=Dimension)
    when: Dimension = field(default_factory=Dimension)    # Time constraints
    objective: str = ""             # Reformulated objective
    domain: str = ""                # Detected domain (manga, cinema, music, tech...)
    confidence: float = 0.0         # How well the prompt was understood
    raw_llm_response: str = ""

    def to_dict(self):
        return {
            "prompt": self.prompt,
            "objective": self.objective,
            "domain": self.domain,
            "confidence": self.confidence,
            "who": self.who.to_dict(),
            "where": self.where.to_dict(),
            "what": self.what.to_dict(),
            "when": self.when.to_dict(),
        }


@dataclass
class Step:
    """A single step in a strategy, possibly with sub-steps."""
    id: str = ""                    # e.g. "S1.2.3"
    action: str = ""                # What to do
    description: str = ""           # Why
    queries: List[str] = field(default_factory=list)       # Concrete search queries
    expected_output: str = ""       # What we expect to find
    sub_steps: List["Step"] = field(default_factory=list)  # Nested sub-steps
    source_type: str = ""           # university, press, social, directory, etc.
    priority: float = 50.0          # For CostEngine
    depends_on: str = ""            # Step ID this depends on (for chaining)
    condition: str = ""             # When to execute: "if X found", "always", etc.

    def to_dict(self):
        d = asdict(self)
        d["sub_steps"] = [s.to_dict() if isinstance(s, Step) else s for s in self.sub_steps]
        return d


@dataclass
class Strategy:
    """A complete search strategy with tier and steps."""
    name: str = ""
    tier: str = ""                  # "direct", "semi_direct", "indirect"
    tier_label: str = ""            # Human label
    description: str = ""
    steps: List[Step] = field(default_factory=list)
    estimated_cost: str = ""        # "low", "medium", "high"
    estimated_yield: str = ""       # "high", "medium", "low"
    priority: int = 1               # Execution order

    def to_dict(self):
        return {
            "name": self.name,
            "tier": self.tier,
            "tier_label": self.tier_label,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_cost": self.estimated_cost,
            "estimated_yield": self.estimated_yield,
            "priority": self.priority,
        }


# ══════════════════════════════════════
# PROMPTS FOR LLM
# ══════════════════════════════════════

PROMPT_ANALYZE = """Tu es un analyste OSINT expert. Decompose cette requete de recherche en elements structurels.

REQUETE: "{prompt}"

Analyse selon 4 dimensions. Pour chaque dimension, identifie:
- explicit: ce qui est directement dit dans la requete
- explicit_refined: precision ou expansion de l'explicite (ex: "USA" -> "51 etats, 3 villes minimum par etat")
- implicit: ce qui est logiquement deductible mais pas dit (intermediaires, parties prenantes, artefacts, lieux de presence)
- rejections: ce qu'il faut explicitement exclure

DIMENSIONS:
1. QUI (who): Les cibles directes ET les intermediaires (agents, editeurs, institutions, syndicats...)
2. OU (where): Lieux physiques ET lieux numeriques (sites, reseaux, plateformes, annuaires, medias)
3. QUOI (what): Productions, artefacts, documents, publications, traces qui permettent d'identifier les cibles
4. QUAND (when): Contraintes temporelles (periode, recence, annees de diplome...)

Reponds UNIQUEMENT en JSON valide:
{{
    "objective": "reformulation claire de l'objectif",
    "domain": "domaine detecte (manga, cinema, musique, tech, sport, etc.)",
    "confidence": 0.0-1.0,
    "who": {{
        "explicit": ["..."],
        "explicit_refined": ["..."],
        "implicit": ["..."],
        "rejections": ["..."]
    }},
    "where": {{
        "explicit": ["..."],
        "explicit_refined": ["..."],
        "implicit": ["..."],
        "rejections": ["..."]
    }},
    "what": {{
        "explicit": ["..."],
        "explicit_refined": ["..."],
        "implicit": ["..."],
        "rejections": ["..."]
    }},
    "when": {{
        "explicit": ["..."],
        "explicit_refined": ["..."],
        "implicit": ["..."],
        "rejections": ["..."]
    }}
}}"""

PROMPT_STRATEGIES = """Tu es un planificateur de recherche OSINT. A partir de cette analyse, genere 3 strategies de recherche.

ANALYSE:
{analysis_json}

Genere exactement 3 strategies avec 3 niveaux:

1. STRATEGIE DIRECTE (cout faible, rendement incertain): 
   Rechercher directement la cible par son nom/description sur les moteurs de recherche.
   Requetes simples et directes.

2. STRATEGIE SEMI-DIRECTE (cout moyen, rendement moyen):
   Rechercher via les intermediaires identifies (agents, editeurs, annuaires pro, syndicats, associations).
   Chaque intermediaire peut reveler des cibles.
   Decompose en etapes: d'abord identifier l'intermediaire, puis explorer ses contacts/publications.

3. STRATEGIE INDIRECTE (cout eleve, rendement eleve):
   Rechercher via les artefacts, institutions, formations, evenements.
   Approche "pivot academique" ou "pivot evenementiel".
   La plus couteuse mais trouve les cibles cachees.

Pour CHAQUE strategie, decompose en etapes hierarchiques.
Chaque etape peut avoir des sous-etapes conditionnelles (si on trouve X, alors chercher Y).

IMPORTANT: Genere des REQUETES CONCRETES pour chaque etape.
Les requetes doivent etre des vraies recherches Google/Brave utilisables.
Utilise des variables {{city}}, {{state}}, {{country}} pour la localisation.

Reponds UNIQUEMENT en JSON valide:
{{
    "strategies": [
        {{
            "name": "Recherche directe",
            "tier": "direct",
            "description": "...",
            "estimated_cost": "low|medium|high",
            "estimated_yield": "low|medium|high",
            "steps": [
                {{
                    "id": "S1.1",
                    "action": "Description de l'action",
                    "description": "Pourquoi cette etape",
                    "queries": ["requete google 1", "requete google 2"],
                    "expected_output": "Ce qu'on espere trouver",
                    "source_type": "search_engine|directory|university|press|social|professional",
                    "priority": 90,
                    "condition": "always",
                    "sub_steps": [
                        {{
                            "id": "S1.1.1",
                            "action": "Sous-action",
                            "queries": ["..."],
                            "condition": "if results found in parent step",
                            "sub_steps": []
                        }}
                    ]
                }}
            ]
        }}
    ]
}}"""

PROMPT_REFINE_QUERIES = """Tu es un expert en recherche sur internet. Genere des requetes de recherche optimisees.

CONTEXTE:
- Objectif: {objective}
- Domaine: {domain}
- Etape: {step_action}
- Lieu: {city}, {state}
- Rejections: {rejections}

Genere {count} requetes de recherche Google/Brave CONCRETES et VARIEES pour cette etape.
Chaque requete doit etre directement utilisable dans un moteur de recherche.
Utilise des operateurs: site:, filetype:, OR, guillemets pour les expressions exactes.

Reponds UNIQUEMENT en JSON: {{"queries": ["requete 1", "requete 2", ...]}}"""


# ══════════════════════════════════════
# STRATEGY PLANNER
# ══════════════════════════════════════

class StrategyPlanner:
    """Decomposes a research prompt into a structured multi-tier strategy."""

    def __init__(self, llm_func: Callable = None):
        """
        Args:
            llm_func: async function(prompt, system="") -> str
                      The LLM query function used for analysis.
        """
        self.llm = llm_func
        self.last_analysis: Optional[AnalysisResult] = None
        self.last_strategies: List[Strategy] = []

    async def _ask_llm(self, prompt: str, system: str = "") -> str:
        """Query LLM and return raw text."""
        if not self.llm:
            raise ValueError("No LLM function configured. Pass llm_func to constructor.")
        return await self.llm(prompt, system)

    def _parse_json(self, text: str) -> Dict:
        """Extract JSON from LLM response (handles markdown code blocks)."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {}

    # ── Step 1: ANALYZE the prompt ──

    async def analyze(self, prompt: str) -> AnalysisResult:
        """Decompose prompt into WHO/WHERE/WHAT/WHEN dimensions.
        
        Returns AnalysisResult with explicit, implicit, and rejections for each.
        """
        llm_prompt = PROMPT_ANALYZE.format(prompt=prompt)
        raw = await self._ask_llm(llm_prompt)
        data = self._parse_json(raw)

        result = AnalysisResult(prompt=prompt, raw_llm_response=raw)
        result.objective = data.get("objective", prompt)
        result.domain = data.get("domain", "general")
        result.confidence = float(data.get("confidence", 0.5))

        for dim_name in ("who", "where", "what", "when"):
            dim_data = data.get(dim_name, {})
            dim = Dimension(
                explicit=dim_data.get("explicit", []),
                explicit_refined=dim_data.get("explicit_refined", []),
                implicit=dim_data.get("implicit", []),
                rejections=dim_data.get("rejections", []),
            )
            setattr(result, dim_name, dim)

        self.last_analysis = result
        return result

    # ── Step 2: BUILD strategies from analysis ──

    async def build_strategies(self, analysis: AnalysisResult = None) -> List[Strategy]:
        """Generate 3-tier strategy tree from analysis.
        
        Returns list of Strategy objects (direct, semi-direct, indirect).
        """
        analysis = analysis or self.last_analysis
        if not analysis:
            raise ValueError("No analysis available. Call analyze() first.")

        analysis_json = json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False)
        llm_prompt = PROMPT_STRATEGIES.format(analysis_json=analysis_json)
        raw = await self._ask_llm(llm_prompt)
        data = self._parse_json(raw)

        strategies = []
        tier_labels = {
            "direct": "Strategie directe",
            "semi_direct": "Strategie semi-directe",
            "indirect": "Strategie indirecte",
        }

        for i, s_data in enumerate(data.get("strategies", [])):
            tier = s_data.get("tier", ["direct","semi_direct","indirect"][min(i,2)])
            strategy = Strategy(
                name=s_data.get("name", f"Strategy {i+1}"),
                tier=tier,
                tier_label=tier_labels.get(tier, tier),
                description=s_data.get("description", ""),
                estimated_cost=s_data.get("estimated_cost", "medium"),
                estimated_yield=s_data.get("estimated_yield", "medium"),
                priority=i + 1,
            )
            strategy.steps = self._parse_steps(s_data.get("steps", []))
            strategies.append(strategy)

        self.last_strategies = strategies
        return strategies

    def _parse_steps(self, steps_data: List[Dict], depth: int = 0) -> List[Step]:
        """Recursively parse step tree."""
        steps = []
        for s in steps_data:
            step = Step(
                id=s.get("id", ""),
                action=s.get("action", ""),
                description=s.get("description", ""),
                queries=s.get("queries", []),
                expected_output=s.get("expected_output", ""),
                source_type=s.get("source_type", ""),
                priority=float(s.get("priority", 50)),
                depends_on=s.get("depends_on", ""),
                condition=s.get("condition", "always"),
            )
            if s.get("sub_steps"):
                step.sub_steps = self._parse_steps(s["sub_steps"], depth + 1)
            steps.append(step)
        return steps

    # ── Step 3: REFINE queries for a specific step + location ──

    async def refine_queries(self, step: Step, city: str = "", state: str = "",
                              count: int = 6) -> List[str]:
        """Generate optimized search queries for a specific step and location."""
        analysis = self.last_analysis
        if not analysis:
            return step.queries  # fallback

        # Collect all rejections
        rejections = (analysis.who.rejections + analysis.where.rejections +
                      analysis.what.rejections)

        prompt = PROMPT_REFINE_QUERIES.format(
            objective=analysis.objective,
            domain=analysis.domain,
            step_action=step.action,
            city=city or "any",
            state=state or "any",
            rejections=", ".join(rejections) or "none",
            count=count,
        )
        raw = await self._ask_llm(prompt)
        data = self._parse_json(raw)
        queries = data.get("queries", [])

        # Also include original queries with variable substitution
        for q in step.queries:
            filled = q.replace("{city}", city).replace("{state}", state)
            filled = filled.replace("{country}", "USA")
            if filled not in queries:
                queries.append(filled)

        return queries[:count * 2]  # Return up to 2x requested

    # ── Flatten: extract all queries from strategy tree ──

    def flatten_queries(self, strategies: List[Strategy] = None,
                        city: str = "", state: str = "") -> List[Dict]:
        """Extract all queries from all strategies as a flat list.
        
        Returns: [{"query": str, "strategy": str, "tier": str, "step_id": str,
                    "source_type": str, "priority": float, "condition": str}]
        """
        strategies = strategies or self.last_strategies
        result = []

        for strat in strategies:
            self._flatten_steps(strat.steps, strat.name, strat.tier,
                                city, state, result)
        
        # Sort by priority (highest first)
        result.sort(key=lambda x: x["priority"], reverse=True)
        return result

    def _flatten_steps(self, steps: List[Step], strat_name: str, tier: str,
                        city: str, state: str, result: List[Dict]):
        for step in steps:
            for q in step.queries:
                filled = q.replace("{city}", city).replace("{state}", state)
                filled = filled.replace("{country}", "USA")
                result.append({
                    "query": filled,
                    "strategy": strat_name,
                    "tier": tier,
                    "step_id": step.id,
                    "step_action": step.action,
                    "source_type": step.source_type,
                    "priority": step.priority,
                    "condition": step.condition,
                })
            # Recurse into sub-steps
            if step.sub_steps:
                self._flatten_steps(step.sub_steps, strat_name, tier,
                                     city, state, result)

    # ── Statistics ──

    def count_queries(self, strategies: List[Strategy] = None) -> Dict:
        """Count queries per tier."""
        strategies = strategies or self.last_strategies
        counts = {"direct": 0, "semi_direct": 0, "indirect": 0, "total": 0}
        for strat in strategies:
            n = self._count_step_queries(strat.steps)
            counts[strat.tier] = counts.get(strat.tier, 0) + n
            counts["total"] += n
        return counts

    def _count_step_queries(self, steps: List[Step]) -> int:
        total = 0
        for step in steps:
            total += len(step.queries)
            if step.sub_steps:
                total += self._count_step_queries(step.sub_steps)
        return total

    # ── Save / Load ──

    def save_plan(self, path: str = ""):
        """Save full analysis + strategies to JSON."""
        p = Path(path) if path else (Path(BASE_DIR) / "RESULTATS" / "strategy_plan.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "analysis": self.last_analysis.to_dict() if self.last_analysis else None,
            "strategies": [s.to_dict() for s in self.last_strategies],
            "query_counts": self.count_queries(),
            "generated_at": time.time(),
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(p)

    @classmethod
    def load_plan(cls, path: str = "") -> Dict:
        """Load saved plan."""
        p = Path(path) if path else (Path(BASE_DIR) / "RESULTATS" / "strategy_plan.json")
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {}

    # ── Format for display ──

    def format_plan_text(self, strategies: List[Strategy] = None) -> str:
        """Format strategies as readable text for UI/console."""
        strategies = strategies or self.last_strategies
        analysis = self.last_analysis
        lines = []

        if analysis:
            lines.append(f"═══ ANALYSE DE RECHERCHE ═══")
            lines.append(f"Prompt: {analysis.prompt}")
            lines.append(f"Objectif: {analysis.objective}")
            lines.append(f"Domaine: {analysis.domain}")
            lines.append(f"Confiance: {analysis.confidence:.0%}")
            lines.append("")
            for dim_name, dim in [("QUI", analysis.who), ("OU", analysis.where),
                                   ("QUOI", analysis.what), ("QUAND", analysis.when)]:
                lines.append(f"  {dim_name}:")
                if dim.explicit: lines.append(f"    Explicite: {', '.join(dim.explicit)}")
                if dim.explicit_refined: lines.append(f"    Affine: {', '.join(dim.explicit_refined)}")
                if dim.implicit: lines.append(f"    Implicite: {', '.join(dim.implicit)}")
                if dim.rejections: lines.append(f"    Rejets: {', '.join(dim.rejections)}")
            lines.append("")

        for strat in strategies:
            lines.append(f"═══ {strat.tier_label.upper()} : {strat.name} ═══")
            lines.append(f"  {strat.description}")
            lines.append(f"  Cout: {strat.estimated_cost} | Rendement: {strat.estimated_yield}")
            lines.append("")
            self._format_steps(strat.steps, lines, indent=2)
            lines.append("")

        counts = self.count_queries(strategies)
        lines.append(f"TOTAL: {counts['total']} requetes "
                     f"(directe: {counts.get('direct',0)}, "
                     f"semi-directe: {counts.get('semi_direct',0)}, "
                     f"indirecte: {counts.get('indirect',0)})")
        return "\n".join(lines)

    def _format_steps(self, steps: List[Step], lines: List[str], indent: int = 0):
        pad = "  " * indent
        for step in steps:
            cond = f" [si: {step.condition}]" if step.condition and step.condition != "always" else ""
            lines.append(f"{pad}[{step.id}] {step.action}{cond}")
            if step.description:
                lines.append(f"{pad}     {step.description}")
            for q in step.queries:
                lines.append(f"{pad}     → \"{q}\"")
            if step.expected_output:
                lines.append(f"{pad}     Attendu: {step.expected_output}")
            if step.sub_steps:
                self._format_steps(step.sub_steps, lines, indent + 2)
