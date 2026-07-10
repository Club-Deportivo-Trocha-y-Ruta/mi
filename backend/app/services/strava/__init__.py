"""Strava Activity Sync domain services (specs/025-strava-activity-sync).

Modules here own OAuth token handling, activity ingestion, and webhook/
reconcile plumbing for the Strava integration. Access and refresh tokens are
third-party credentials for minors' accounts and are always stored encrypted
at rest (see ``token_store``) — never logged, never persisted in plaintext.
"""
