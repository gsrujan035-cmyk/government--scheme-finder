"""
Configuration module for Government Scheme Finder backend.
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))

class Config:
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.path.join(BASE_DIR, 'schemes.db')
    FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'frontend')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1')
    PORT = int(os.environ.get('PORT', 5000))
    HOST = os.environ.get('HOST', '127.0.0.1')
    DISCLAIMER = (
        "Preliminary eligibility match only. Final approval and disbursement are determined "
        "exclusively by the respective government ministry, nodal agency, or bank. This service "
        "does not guarantee sanction."
    )
