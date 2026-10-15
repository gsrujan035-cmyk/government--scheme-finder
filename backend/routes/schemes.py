"""
API routes for Government Scheme Finder.
Implements:
  - GET /api/schemes
  - GET /api/schemes/<id>
  - POST /api/schemes/search
"""
from flask import Blueprint, request, jsonify
from ..database import query_schemes, query_scheme_by_id
from ..config import Config

schemes_bp = Blueprint('schemes', __name__, url_prefix='/api/schemes')


@schemes_bp.route('', methods=['GET'])
def get_all_schemes():
    """
    Retrieve all government schemes with optional filters.
    Query parameters:
      - category: Filter by category (e.g. agriculture, education, health, business, women, social)
      - state: Filter by applicable state (e.g. Telangana, Andhra Pradesh)
      - search or q: Keyword search term across scheme titles, descriptions, benefits
      - sort: Sort by 'amount', 'name', or 'relevance'
    """
    try:
        category = request.args.get('category', 'all').strip()
        state = request.args.get('state', 'all').strip()
        search = request.args.get('search') or request.args.get('q', '')
        search = search.strip()
        sort = request.args.get('sort', 'relevance').strip()

        schemes = query_schemes(category=category, state=state, search=search, sort=sort)
        
        return jsonify({
            "status": "success",
            "count": len(schemes),
            "filters": {
                "category": category,
                "state": state,
                "search": search,
                "sort": sort
            },
            "data": schemes,
            "disclaimer": Config.DISCLAIMER
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Failed to fetch schemes from database.",
            "detail": str(e)
        }), 500


@schemes_bp.route('/<scheme_id>', methods=['GET'])
def get_scheme_by_id(scheme_id):
    """
    Retrieve full details for a single government scheme by ID.
    """
    try:
        scheme_id = scheme_id.strip()
        scheme = query_scheme_by_id(scheme_id)

        if not scheme:
            return jsonify({
                "status": "error",
                "message": f"Scheme not found with ID '{scheme_id}'."
            }), 404

        return jsonify({
            "status": "success",
            "data": scheme,
            "disclaimer": Config.DISCLAIMER
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Database query error while retrieving scheme.",
            "detail": str(e)
        }), 500


@schemes_bp.route('/search', methods=['POST'])
def search_matching_schemes():
    """
    Evaluate user profile parameters against government scheme eligibility rules.
    Input JSON payload:
      - age (int, required, 0 to 120)
      - state (str, optional, defaults to 'all')
      - occupation (str, optional, e.g. farmer, student, vendor, business, unorganized, senior)
      - income (int/float, optional, family annual income in INR)
      - gender (str, optional: female, male, transgender, any)
      - land (str, optional: none, marginal, small, large)
      - category (str, optional: General, OBC, SC, ST, EWS, Minority)
      - disability (str, optional: yes, no)
      - girl_child (bool, optional)
      - bpl (bool, optional)
    """
    if not request.is_json:
        return jsonify({
            "status": "error",
            "message": "Request payload must be formatted as application/json."
        }), 400

    data = request.get_json() or {}
    errors = []

    # 1. Input Validation
    age_raw = data.get('age')
    age = None
    if age_raw is not None:
        try:
            age = int(age_raw)
            if age < 0 or age > 120:
                errors.append("Field 'age' must be an integer between 0 and 120.")
        except (ValueError, TypeError):
            errors.append("Field 'age' must be a valid number.")

    income_raw = data.get('income')
    income = None
    if income_raw is not None:
        try:
            income = float(income_raw)
            if income < 0:
                errors.append("Field 'income' cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Field 'income' must be a valid number.")

    gender = str(data.get('gender', 'any')).strip().lower()
    state = str(data.get('state', 'all')).strip()
    occupation = str(data.get('occupation', 'any')).strip().lower()
    land = str(data.get('land', 'none')).strip().lower()
    social_category = str(data.get('category', 'General')).strip()
    has_girl_child = bool(data.get('girl_child', data.get('girlChild', False)))
    has_bpl = bool(data.get('bpl', False))

    if errors:
        return jsonify({
            "status": "error",
            "message": "Invalid input parameters.",
            "errors": errors
        }), 400

    try:
        # Retrieve all candidate schemes
        schemes = query_schemes()
        evaluated_results = []

        for s in schemes:
            score = 0
            rule_breakdown = {}

            # --- Rule 1: Occupation Match (30 pts) ---
            occ_list = [o.lower() for o in s.get("occupations", [])]
            occ_matched = False
            if "all" in occ_list or occupation in occ_list:
                score += 30
                occ_matched = True
                occ_note = f"Matches primary occupation: {occupation.title()}"
            else:
                score += 5
                occ_note = f"Targeted primarily for {', '.join(s.get('occupations', []))}"
            
            rule_breakdown["occupation"] = {
                "parameter": "Occupation",
                "requirement": ", ".join(s.get("occupations", [])).title(),
                "user_value": occupation.title() if occupation != 'any' else "Not Specified",
                "status": "matched" if occ_matched else ("neutral" if occupation == 'any' else "unmet"),
                "detail": occ_note
            }

            # --- Rule 2: Age Suitability (20 pts) ---
            min_age = s.get("min_age", 0)
            max_age = s.get("max_age", 100)
            age_matched = False

            if age is not None:
                if min_age <= age <= max_age:
                    score += 20
                    age_matched = True
                    age_note = f"Age {age} falls within {min_age} - {max_age} years."
                elif abs(age - min_age) <= 3 or abs(age - max_age) <= 3:
                    score += 8
                    age_note = f"Age {age} is close to range {min_age} - {max_age} years."
                else:
                    age_note = f"Age {age} is outside the criteria ({min_age} - {max_age} years)."
            else:
                score += 10
                age_note = f"Scheme applies to age {min_age} - {max_age} years."

            rule_breakdown["age"] = {
                "parameter": "Age Limit",
                "requirement": f"{min_age} to {max_age} years",
                "user_value": f"{age} years" if age is not None else "Not Specified",
                "status": "matched" if age_matched else ("neutral" if age is None else "unmet"),
                "detail": age_note
            }

            # --- Rule 3: Income Threshold (20 pts) ---
            income_max = s.get("income_max", 10000000)
            inc_matched = False

            if income is not None:
                if income <= income_max:
                    score += 20
                    inc_matched = True
                    inc_note = f"Annual income ₹{int(income):,} is within maximum cap ₹{income_max:,}."
                elif income <= income_max * 1.25:
                    score += 10
                    inc_note = f"Income slightly exceeds baseline threshold."
                else:
                    inc_note = f"Annual income exceeds scheme maximum threshold (₹{income_max:,})."
            else:
                score += 10
                inc_note = f"Scheme requires income under ₹{income_max:,}."

            rule_breakdown["income"] = {
                "parameter": "Family Income Cap",
                "requirement": f"Up to ₹{income_max:,} / year",
                "user_value": f"₹{int(income):,} / year" if income is not None else "Not Specified",
                "status": "matched" if inc_matched else ("neutral" if income is None else "unmet"),
                "detail": inc_note
            }

            # --- Rule 4: State Applicability (15 pts) ---
            scheme_states = [st.lower() for st in s.get("states", [])]
            state_matched = False

            if state.lower() == 'all' or "all" in scheme_states or state.lower() in scheme_states:
                score += 15
                state_matched = True
                state_note = f"Available in {s.get('scope')}."
            else:
                state_note = f"Specific to {', '.join(s.get('states', []))}."

            rule_breakdown["state"] = {
                "parameter": "State Domicile",
                "requirement": ", ".join(s.get("states", [])),
                "user_value": state if state.lower() != 'all' else "Pan-India",
                "status": "matched" if state_matched else "unmet",
                "detail": state_note
            }

            # --- Rule 5: Special Criteria (15 pts) ---
            special_matched = True
            special_notes = []

            if s.get("requires_land", 0):
                if land != "none":
                    score += 15
                    special_notes.append("Agricultural land ownership verified.")
                else:
                    special_matched = False
                    special_notes.append("Requires cultivable landholding.")
            elif s.get("requires_girl_child", 0):
                if has_girl_child:
                    score += 15
                    special_notes.append("Girl child criteria fulfilled.")
                else:
                    special_matched = False
                    special_notes.append("Requires girl child in family under 10 years.")
            elif s.get("requires_bpl", 0):
                if has_bpl:
                    score += 15
                    special_notes.append("Ration card / BPL entitlement verified.")
                else:
                    special_matched = False
                    special_notes.append("Requires BPL or SECC listed family.")
            else:
                score += 15
                special_notes.append("Standard public inclusion criteria.")

            rule_breakdown["special_inclusion"] = {
                "parameter": "Special Factors",
                "requirement": s.get("criteria_summary", ""),
                "user_value": f"Land: {land.title()} | Girl Child: {has_girl_child} | BPL: {has_bpl}",
                "status": "matched" if special_matched else "unmet",
                "detail": " ".join(special_notes)
            }

            # Bound final match score between 35% and 99%
            final_score = min(max(score, 35), 99)

            if final_score >= 80:
                match_label = "High Potential Match"
            elif final_score >= 55:
                match_label = "Check Eligibility"
            else:
                match_label = "Partial Fit"

            s_copy = dict(s)
            s_copy["match_score"] = final_score
            s_copy["match_label"] = match_label
            s_copy["rule_breakdown"] = rule_breakdown
            evaluated_results.append(s_copy)

        # Sort by match score descending
        evaluated_results.sort(key=lambda x: x["match_score"], reverse=True)

        return jsonify({
            "status": "success",
            "count": len(evaluated_results),
            "user_profile": {
                "age": age,
                "gender": gender,
                "state": state,
                "occupation": occupation,
                "income": income,
                "land": land,
                "category": social_category,
                "girl_child": has_girl_child,
                "bpl": has_bpl
            },
            "results": evaluated_results,
            "disclaimer": Config.DISCLAIMER
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Error while evaluating eligibility rules.",
            "detail": str(e)
        }), 500
