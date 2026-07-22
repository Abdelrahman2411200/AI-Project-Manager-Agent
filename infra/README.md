# Infrastructure boundary

This directory is reserved for vendor-neutral deployment, runtime, backup, and operator assets.

Phase 1 keeps service-specific Dockerfiles beside their build contexts and defines local orchestration in the root `compose.yaml`. CI workflows and production deployment profiles are introduced in later implementation phases; no hosting vendor is assumed here.
