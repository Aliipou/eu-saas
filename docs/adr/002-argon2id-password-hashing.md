# ADR-002: Argon2id for Password Hashing

## Status

Accepted

## Context

Password hashing must resist brute-force attacks. Options:
- bcrypt (widely used, well-understood)
- scrypt (memory-hard)
- Argon2id (winner of Password Hashing Competition, recommended by OWASP)

## Decision

Use **Argon2id** via the `argon2-cffi` library with OWASP-recommended parameters.

## Consequences

### Positive
- OWASP-recommended algorithm for 2024+
- Memory-hard and time-hard (resistant to GPU/ASIC attacks)
- Built-in salt generation
- `argon2-cffi` provides a safe, high-level API

### Negative
- Slightly higher memory usage per hash operation than bcrypt
- Less widespread than bcrypt (though gaining adoption)

## References
- OWASP Password Storage Cheat Sheet
- RFC 9106 (Argon2)
