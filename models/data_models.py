"""models/data_models.py — Fragment, ChannelCandidate, Resolution states."""
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict
from config.settings import PENDING, RESOLVED, FAILED

@dataclass
class Fragment:
    fragment_type: str = ""; value: str = ""; source_url: str = ""; source_type: str = ""
    context: str = ""; search_query: str = ""; search_wave: int = 1
    timestamp: float = field(default_factory=time.time)
    def to_dict(self): return asdict(self)

@dataclass
class ChannelCandidate:
    candidate_id: str = ""; channel_name: str = ""; channel_url: str = ""
    alternative_names: list = field(default_factory=list)
    target_city: str = ""; target_state: str = ""; target_category: str = ""
    fragments: list = field(default_factory=list); fragment_count: int = 0
    independent_sources: int = 0
    city_evidence: list = field(default_factory=list); city_score: float = 0.0
    category_evidence: list = field(default_factory=list); category_score: float = 0.0
    yt_verified: bool = False; yt_exists: bool = False; yt_real_name: str = ""
    yt_subscribers_text: str = ""; yt_subscribers_count: int = 0; yt_subscriber_match: bool = False
    yt_last_upload_text: str = ""; yt_last_upload_recent: bool = False; yt_description: str = ""
    total_score: float = 0.0; verified: bool = False
    rejection_reasons: list = field(default_factory=list)
    def to_dict(self): return asdict(self)
    def add_fragment(self, frag: Fragment):
        self.fragments.append(frag.to_dict()); self.fragment_count = len(self.fragments)
        self.independent_sources = len(set(f["source_url"] for f in self.fragments if f.get("source_url")))
    def compute_city_score(self):
        if not self.city_evidence: self.city_score = 0.0; return
        srcs = set(e.get("source_url","") for e in self.city_evidence if isinstance(e,dict) and e.get("source_url"))
        self.city_score = min(0.95, 0.3 + len(srcs)*0.2) if srcs else 0.15
    def compute_total_score(self):
        self.compute_city_score()
        if not self.yt_exists: self.total_score = 0.0; return
        self.total_score = round(
            0.30*self.city_score + 0.15*self.category_score
            + 0.25*(1.0 if self.yt_subscriber_match else 0.0)
            + 0.20*(1.0 if self.yt_last_upload_recent else 0.0)
            + 0.10*min(1.0, self.independent_sources/3.0), 3)

@dataclass
class CategoryResolution:
    category: str = ""; status: str = PENDING; waves_attempted: int = 0
    candidates: list = field(default_factory=list); best_candidate: Optional[dict] = None
    failure_reason: str = ""; search_log: list = field(default_factory=list)
    def to_dict(self): return asdict(self)

@dataclass
class CityResolution:
    city: str = ""; state: str = ""; status: str = PENDING
    categories: Dict[str,CategoryResolution] = field(default_factory=dict)
    collected_fragments: list = field(default_factory=list)
    cross_city_fragments: list = field(default_factory=list)
    def is_resolved(self): return all(c.status==RESOLVED for c in self.categories.values())
    def is_fully_attempted(self): return all(c.status in (RESOLVED,FAILED) for c in self.categories.values())
    def summary(self): return f"{sum(1 for c in self.categories.values() if c.status==RESOLVED)}/{len(self.categories)}"
    def to_dict(self): return {"city":self.city,"state":self.state,"status":self.status,
        "categories":{k:v.to_dict() for k,v in self.categories.items()},"summary":self.summary()}

@dataclass
class StateResolution:
    state: str = ""; status: str = PENDING
    cities: Dict[str,CityResolution] = field(default_factory=dict)
    def is_resolved(self): return all(c.is_fully_attempted() for c in self.cities.values())
    def summary(self):
        t=sum(len(c.categories) for c in self.cities.values())
        ok=sum(1 for c in self.cities.values() for cat in c.categories.values() if cat.status==RESOLVED)
        return {"total":t,"resolved":ok,"cities":{n:c.summary() for n,c in self.cities.items()}}
    def to_dict(self): return {"state":self.state,"status":self.status,
        "cities":{k:v.to_dict() for k,v in self.cities.items()},"summary":self.summary()}
