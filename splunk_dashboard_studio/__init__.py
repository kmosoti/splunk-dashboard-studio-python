"""Version-aware Splunk Enterprise Dashboard Studio generation and validation."""

from splunk_dashboard_studio.generation import DashboardBuilder, canonical_json
from splunk_dashboard_studio.graph import (
    GraphAnalysis,
    SearchOptimizationPlan,
    analyze_search_graph,
    plan_search_optimizations,
)
from splunk_dashboard_studio.issues import ValidationIssue, ValidationReport
from splunk_dashboard_studio.models import DashboardDefinition
from splunk_dashboard_studio.profiles import EnterpriseProfile, available_profiles, profile_for
from splunk_dashboard_studio.validation import validate_dashboard
from splunk_dashboard_studio.version import EnterpriseVersion, TargetPlatform

__all__ = [
    "DashboardBuilder",
    "DashboardDefinition",
    "EnterpriseProfile",
    "EnterpriseVersion",
    "GraphAnalysis",
    "SearchOptimizationPlan",
    "TargetPlatform",
    "ValidationIssue",
    "ValidationReport",
    "analyze_search_graph",
    "available_profiles",
    "canonical_json",
    "plan_search_optimizations",
    "profile_for",
    "validate_dashboard",
]

__version__ = "0.1.0"
