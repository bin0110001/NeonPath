"""
Deterministic evaluation service for Phase 3 implementation.
Implements rule-based evaluation logic without requiring AI.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import re

from careerflow.domain.jobs.model import Job
from careerflow.domain.profiles.model import Profile, RoleFamily, RoleTarget, SearchPreferences, ScoringPreferences


class DeterministicEvaluator:
    """Evaluates job-profile fit using deterministic rules."""
    
    def __init__(self):
        # Default weights - can be overridden by profile-specific weights
        self.default_weights = {
            "role_alignment": 0.20,
            "seniority_alignment": 0.15,
            "technical_alignment": 0.15,
            "architecture_alignment": 0.15,
            "leadership_alignment": 0.10,
            "location_alignment": 0.10,
            "compensation_alignment": 0.10,
            "interest_alignment": 0.05,
        }
        
        # Remote work preferences mapping
        self.remote_preference_scores = {
            "REQUIRED": {"REMOTE": 1.0, "HYBRID": 0.0, "ONSITE": 0.0},
            "PREFERRED": {"REMOTE": 1.0, "HYBRID": 0.5, "ONSITE": 0.0},
            "NEUTRAL": {"REMOTE": 0.5, "HYBRID": 0.5, "ONSITE": 0.5},
            "AVOID": {"REMOTE": 0.0, "HYBRID": 0.5, "ONSITE": 1.0},
            "BLOCK": {"REMOTE": 0.0, "HYBRID": 0.0, "ONSITE": 0.0},  # Blocker if not matched
        }
        
        # Employment type preferences mapping
        self.employment_type_preference_scores = {
            "REQUIRED": lambda pref, actual: 1.0 if pref == actual else 0.0,
            "PREFERRED": lambda pref, actual: 1.0 if pref == actual else 0.5,
            "NEUTRAL": lambda pref, actual: 0.5,
            "AVOID": lambda pref, actual: 0.0 if pref == actual else 0.5,
            "BLOCK": lambda pref, actual: 0.0 if pref == actual else 0.5,  # Blocker if matched
        }

    def evaluate_job_against_profile(
        self, 
        job: Job, 
        profile: Profile,
        role_families: List[RoleFamily] = None,
        role_targets: List[RoleTarget] = None,
        search_prefs: SearchPreferences = None,
        scoring_prefs: ScoringPreferences = None
    ) -> Dict[str, Any]:
        """
        Evaluate a job against a profile using deterministic rules.
        
        Returns:
            Dictionary with evaluation results including dimension scores,
            strengths, gaps, blockers, and explanation.
        """
        # Use provided data or fetch from profile relationships
        if role_families is None:
            role_families = getattr(profile, 'role_families', [])
        if role_targets is None:
            role_targets = getattr(profile, 'role_targets', [])
        if search_prefs is None:
            search_prefs = getattr(profile, 'search_preferences', None)
        if scoring_prefs is None:
            scoring_prefs = getattr(profile, 'scoring_preferences', None)
        
        # Get profile-specific weights or use defaults
        weights = scoring_prefs.weights if scoring_prefs and scoring_prefs.weights else self.default_weights
        
        # Initialize results
        dimension_scores = {}
        strengths = []
        gaps = []
        blockers = []
        
        # 1. Role Alignment (title matching + role family matching)
        role_alignment_score = self._calculate_role_alignment(job, role_families, role_targets)
        dimension_scores["role_alignment"] = role_alignment_score
        
        if role_alignment_score >= 0.8:
            strengths.append(f"Strong role alignment: '{job.title}' matches target role families")
        elif role_alignment_score >= 0.5:
            strengths.append(f"Moderate role alignment: '{job.title}' shows some relevance to target roles")
        else:
            gaps.append(f"Weak role alignment: '{job.title}' doesn't closely match target role families")
            
        # 2. Seniority Alignment (inferred from title)
        seniority_alignment_score = self._calculate_seniority_alignment(job, role_targets)
        dimension_scores["seniority_alignment"] = seniority_alignment_score
        
        # 3. Location Rules
        location_alignment_score, location_blocker = self._calculate_location_alignment(job, search_prefs)
        dimension_scores["location_alignment"] = location_alignment_score
        if location_blocker:
            blockers.append(location_blocker)
        elif location_alignment_score >= 0.8:
            strengths.append(f"Location match: {job.location_text}")
        elif location_alignment_score >= 0.5:
            strengths.append(f"Location acceptable: {job.location_text}")
        else:
            gaps.append(f"Location mismatch: {job.location_text}")
            
        # 4. Remote Rules
        remote_alignment_score, remote_blocker = self._calculate_remote_alignment(job, search_prefs)
        dimension_scores["remote_alignment"] = remote_alignment_score  # Using location_alignment slot for now
        if remote_blocker:
            blockers.append(remote_blocker)
        elif remote_alignment_score >= 0.8:
            strengths.append(f"Remote work preference met: {job.remote_type}")
        elif remote_alignment_score >= 0.5:
            strengths.append(f"Remote work preference partially met: {job.remote_type}")
        else:
            gaps.append(f"Remote work preference not met: {job.remote_type}")
            
        # 5. Compensation Rules
        compensation_alignment_score, compensation_blocker = self._calculate_compensation_alignment(job, search_prefs)
        dimension_scores["compensation_alignment"] = compensation_alignment_score
        if compensation_blocker:
            blockers.append(compensation_blocker)
        elif compensation_alignment_score >= 0.8:
            strengths.append(f"Compensation meets requirements: {job.salary_currency} {job.salary_min}-{job.salary_max} {job.salary_period}")
        elif compensation_alignment_score >= 0.5:
            strengths.append(f"Compensation acceptable: {job.salary_currency} {job.salary_min}-{job.salary_max} {job.salary_period}")
        else:
            gaps.append(f"Compensation below requirements: {job.salary_currency} {job.salary_min}-{job.salary_max} {job.salary_period}")
            
        # 6. Employment Type Rules
        employment_alignment_score, employment_blocker = self._calculate_employment_type_alignment(job, search_prefs)
        dimension_scores["employment_alignment"] = employment_alignment_score
        if employment_blocker:
            blockers.append(employment_blocker)
        elif employment_alignment_score >= 0.8:
            strengths.append(f"Employment type match: {job.employment_type}")
        elif employment_alignment_score >= 0.5:
            strengths.append(f"Employment type acceptable: {job.employment_type}")
        else:
            gaps.append(f"Employment type mismatch: {job.employment_type}")
            
        # 7. Technical/Skill Matching (keyword-based)
        technical_alignment_score = self._calculate_technical_alignment(job, profile)
        dimension_scores["technical_alignment"] = technical_alignment_score
        
        # 8. Other dimensions (simplified for MVP)
        dimension_scores["architecture_alignment"] = technical_alignment_score * 0.9  # Simplified
        dimension_scores["leadership_alignment"] = technical_alignment_score * 0.8   # Simplified
        dimension_scores["domain_alignment"] = role_alignment_score * 0.9              # Simplified
        dimension_scores["interest_alignment"] = role_alignment_score * 0.85           # Simplified
        
        # Calculate weighted overall score
        overall_score = sum(
            dimension_scores.get(dim, 0.0) * weight 
            for dim, weight in weights.items()
        )
        
        # Determine if there are any blockers
        has_blockers = len(blockers) > 0
        
        # Generate explanation
        explanation = self._generate_explanation(
            job, profile, dimension_scores, strengths, gaps, blockers, has_blockers
        )
        
        return {
            "overall_score": max(0.0, min(1.0, overall_score)),  # Clamp to 0-1
            "confidence": 0.85,  # Fixed confidence for deterministic evaluation
            "dimension_scores_json": dimension_scores,
            "strengths": strengths,
            "transferable_matches": [],  # Will be populated by semantic evaluation
            "gaps": gaps,
            "blockers": blockers,
            "unknowns": [],  # Will be populated by semantic evaluation
            "explanation": explanation,
            "evaluator_version": "deterministic-v1.0",
            "model_provider": None,  # Deterministic, no external model
            "model_name": None,
        }
    
    def _calculate_role_alignment(self, job: Job, role_families: List[RoleFamily], role_targets: List[RoleTarget]) -> float:
        """Calculate role alignment based on title matching and role families."""
        if not role_families and not role_targets:
            return 0.5  # Neutral if no preferences set
            
        title_lower = job.title.lower()
        max_score = 0.0
        
        # Check role families
        for rf in role_families:
            if rf.enabled and rf.name.lower() in title_lower:
                max_score = max(max_score, 0.9)
            # Check for partial matches
            rf_words = rf.name.lower().split()
            title_words = title_lower.split()
            matches = sum(1 for word in rf_words if any(word in title_word for title_word in title_words))
            if matches > 0:
                score = min(0.7, matches * 0.2)
                max_score = max(max_score, score)
        
        # Check role targets
        for rt in role_targets:
            # Check title patterns
            if rt.title_pattern:
                pattern = rt.title_pattern.lower()
                if "*" in pattern:
                    # Simple wildcard matching
                    regex_pattern = pattern.replace("*", ".*")
                    if re.search(regex_pattern, title_lower):
                        max_score = max(max_score, 0.95)
                elif pattern in title_lower:
                    max_score = max(max_score, 0.9)
            
            # Check include/exclude keywords
            include_score = 0.0
            if rt.include_keywords:
                include_matches = sum(1 for keyword in rt.include_keywords if keyword.lower() in title_lower)
                include_score = min(1.0, include_matches * 0.3)
            
            exclude_penalty = 0.0
            if rt.exclude_keywords:
                exclude_matches = sum(1 for keyword in rt.exclude_keywords if keyword.lower() in title_lower)
                exclude_penalty = min(0.8, exclude_matches * 0.4)  # Heavy penalty for exclusions
            
            keyword_score = max(0.0, include_score - exclude_penalty)
            max_score = max(max_score, keyword_score)
            
            # Check seniority levels
            if rt.target_seniority:
                seniority_score = self._calculate_seniority_from_title(title_lower, rt.target_seniority)
                max_score = max(max_score, seniority_score)
        
        return min(1.0, max_score)
    
    def _calculate_seniority_from_title(self, title: str, target_seniority: List[str]) -> float:
        """Calculate seniority match from job title."""
        seniority_indicators = {
            "entry": ["entry", "junior", "jr", "associate", "assistant"],
            "mid": ["mid", "intermediate", "regular"],
            "senior": ["senior", "sr", "lead", "principal", "staff"],
            "lead": ["lead", "principal", "staff", "manager", "head"],
            "manager": ["manager", "management", "director", "head"],
            "director": ["director", "vp", "vice president", "head"],
            "executive": ["executive", "ceo", "cfo", "cto", "president"]
        }
        
        title_lower = title.lower()
        matched_levels = []
        
        for level, indicators in seniority_indicators.items():
            if any(indicator in title_lower for indicator in indicators):
                matched_levels.append(level)
        
        if not matched_levels:
            return 0.3  # Default if no seniority detected
        
        # Check if any matched level is in target seniority
        for matched_level in matched_levels:
            if matched_level in target_seniority:
                return 0.9
        
        # Partial match - some overlap
        overlap = len(set(matched_levels) & set(target_seniority))
        if overlap > 0:
            return 0.6
        
        return 0.2  # Low match if no overlap
    
    def _calculate_seniority_alignment(self, job: Job, role_targets: List[RoleTarget]) -> float:
        """Calculate seniority alignment based on role targets."""
        if not role_targets:
            return 0.5  # Neutral
            
        title_lower = job.title.lower()
        best_score = 0.0
        
        for rt in role_targets:
            if rt.target_seniority:
                score = self._calculate_seniority_from_title(title_lower, rt.target_seniority)
                best_score = max(best_score, score)
                
        return best_score
    
    def _calculate_location_alignment(self, job: Job, search_prefs: Optional[SearchPreferences]) -> tuple[float, Optional[str]]:
        """Calculate location alignment and check for blockers."""
        if not search_prefs:
            return 0.5, None  # Neutral if no preferences
        
        job_location = (job.location_text or "").lower()
        
        # Check excluded locations
        if search_prefs.excluded_countries or search_prefs.excluded_regions or search_prefs.excluded_cities:
            # Simple check - in reality would need proper geocoding
            excluded_terms = []
            excluded_terms.extend([c.lower() for c in search_prefs.excluded_countries])
            excluded_terms.extend([r.lower() for r in search_prefs.excluded_regions])
            excluded_terms.extend([c.lower() for c in search_prefs.excluded_cities])
            
            for term in excluded_terms:
                if term in job_location:
                    return 0.0, f"Location blocked: {job.location_text} matches excluded location '{term}'"
        
        # Check preferred locations
        location_score = 0.5  # Default neutral
        preferred_terms = []
        preferred_terms.extend([c.lower() for c in search_prefs.allowed_countries])
        preferred_terms.extend([r.lower() for r in search_prefs.allowed_regions])
        preferred_terms.extend([c.lower() for c in search_prefs.allowed_cities])
        
        if preferred_terms:
            matches = sum(1 for term in preferred_terms if term in job_location)
            if matches > 0:
                location_score = min(1.0, matches * 0.4)
        
        # Relocation allowance
        if search_prefs.relocation_allowed:
            location_score = max(location_score, 0.7)  # Boost if relocation is OK
        
        return location_score, None
    
    def _calculate_remote_alignment(self, job: Job, search_prefs: Optional[SearchPreferences]) -> tuple[float, Optional[str]]:
        """Calculate remote work alignment and check for blockers."""
        if not search_prefs:
            return 0.5, None  # Neutral if no preferences
        
        job_remote = job.remote_type or "ONSITE"
        remote_pref = search_prefs.remote_preference or "NEUTRAL"
        
        # Get score from preference mapping
        score_map = self.remote_preference_scores.get(remote_pref, self.remote_preference_scores["NEUTRAL"])
        score = score_map.get(job_remote, 0.0)
        
        # Check for blocker
        blocker = None
        if remote_pref == "BLOCK" and score == 0.0:
            blocker = f"Remote work blocked: {job_remote} not allowed when remote=BLOCK"
        elif remote_pref == "REQUIRED" and score == 0.0:
            blocker = f"Remote work required but job is {job_remote}"
        
        return score, blocker
    
    def _calculate_compensation_alignment(self, job: Job, search_prefs: Optional[SearchPreferences]) -> tuple[float, Optional[str]]:
        """Calculate compensation alignment and check for blockers."""
        if not search_prefs:
            return 0.5, None  # Neutral if no preferences
        
        blocker = None
        
        # Check minimum base salary
        if search_prefs.minimum_base_salary and job.salary_min:
            if job.salary_min < search_prefs.minimum_base_salary:
                blocker = f"Salary below minimum: {job.salary_currency} {job.salary_min} < {search_prefs.minimum_base_salary} {search_prefs.currency}"
                return 0.0, blocker
            else:
                # Salary meets or exceeds minimum
                excess_ratio = (job.salary_min - search_prefs.minimum_base_salary) / search_prefs.minimum_base_salary
                score = min(1.0, 0.5 + excess_ratio * 0.5)  # 0.5-1.0 range
                return score, blocker
        
        # Check minimum total compensation
        if search_prefs.minimum_total_comp and job.salary_max:
            if job.salary_max < search_prefs.minimum_total_comp:
                blocker = f"Total compensation below minimum: {job.salary_currency} {job.salary_max} < {search_prefs.minimum_total_comp} {search_prefs.currency}"
                return 0.0, blocker
            else:
                # Salary meets or exceeds minimum
                excess_ratio = (job.salary_max - search_prefs.minimum_total_comp) / search_prefs.minimum_total_comp
                score = min(1.0, 0.5 + excess_ratio * 0.5)  # 0.5-1.0 range
                return score, blocker
        
        # No specific compensation requirements
        return 0.5, blocker
    
    def _calculate_employment_type_alignment(selfself, job: Job, search_prefs: Optional[SearchPreferences]) -> tuple[float, Optional[str]]:
        """Calculate employment type alignment and check for blockers."""
        if not search_prefs:
            return 0.5, None  # Neutral if no preferences
        
        job_employment = job.employment_type or "FULL_TIME"
        blocker = None
        
        # Check excluded employment types
        if search_prefs.excluded_employment_types:
            if job_employment in search_prefs.excluded_employment_types:
                blocker = f"Employment type blocked: {job_employment} is in excluded types"
                return 0.0, blocker
        
        # Check preferred employment types
        if search_prefs.preferred_employment_types:
            if job_employment in search_prefs.preferred_employment_types:
                return 1.0, blocker
            else:
                return 0.3, blocker  # Lower score if not in preferred
        
        # Check required employment types (if implemented as preferred_employment_types with REQUIRED policy)
        # For simplicity, we'll treat employment_types as preferred unless we have a separate required field
        
        return 0.5, blocker
    
    def _calculate_technical_alignment(self, job: Job, profile: Profile) -> float:
        """Calculate technical skill alignment using keyword matching."""
        if not hasattr(profile, 'skills') or not profile.skills:
            return 0.3  # Low default if no skills in profile
        
        # Get job requirements text
        job_text_parts = [
            job.title.lower(),
            job.description_text.lower() if job.description_text else "",
            " ".join([req.normalized_text.lower() for req in getattr(job, 'requirements', [])]) if hasattr(job, 'requirements') else ""
        ]
        job_text = " ".join(job_text_parts)
        
        # Get profile skills
        profile_skills = []
        for skill in profile.skills:
            profile_skills.append(skill.canonical_name.lower())
            # Also check aliases if available
            if hasattr(skill, 'aliases'):
                profile_skills.extend([alias.lower() for alias in skill.aliases])
        
        if not profile_skills:
            return 0.3
        
        # Count matches
        matches = 0
        for skill in profile_skills:
            if skill in job_text:
                matches += 1
        
        # Calculate score based on match ratio
        match_ratio = matches / len(profile_skills) if profile_skills else 0
        return min(1.0, match_ratio * 2)  # Boost score since not all skills need to match
    
    def _generate_explanation(
        self, 
        job: Job, 
        profile: Profile, 
        dimension_scores: Dict[str, float],
        strengths: List[str],
        gaps: List[str],
        blockers: List[str],
        has_blockers: bool
    ) -> str:
        """Generate a human-readable explanation of the evaluation."""
        if has_blockers:
            explanation = f"Job '{job.title}' at {job.company} has blockers that prevent recommendation. "
        else:
            explanation = f"Job '{job.title}' at {job.company} evaluated for profile '{getattr(profile, 'display_name', 'Unknown')}'. "
        
        explanation += f"Overall fit score: {dimension_scores.get('overall_score', 0.0):.0%}. "
        
        if strengths:
            explanation += f"Strengths include: {', '.join(strengths[:2])}. "
        
        if gaps:
            explanation += f"Gaps identified: {', '.join(gaps[:2])}. "
        
        if blockers:
            explanation += f"Blockers: {', '.join(blockers)}. "
        
        explanation += "Evaluation based on deterministic rules (role matching, location, compensation, etc.)."
        
        return explanation


# Factory function for easy instantiation
def create_deterministic_evaluator() -> DeterministicEvaluator:
    """Create a deterministic evaluator instance."""
    return DeterministicEvaluator()