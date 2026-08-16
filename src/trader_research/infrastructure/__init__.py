"""Contain outer persistence, process, and provider adapters for research.

Infrastructure implements ports owned by inner research contexts and may depend
on Postgres or optional third-party libraries. Domain and application modules
must not import concrete adapters from this package.
"""
