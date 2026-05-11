"""Pydantic v2 response models for the HTTP API.

These are the *wire* shapes — distinct from `packages/domain/` models which
describe the conceptual domain. We keep them separate so the API can evolve
its serialization (camelCase, field renaming, deprecation) without tugging on
domain definitions.
"""
