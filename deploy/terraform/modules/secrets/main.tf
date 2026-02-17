variable "environment" {
  type = string
}

# In production, use HashiCorp Vault or external secrets operator
# This module defines the Kubernetes secrets structure

# For development: use sealed-secrets or plain k8s secrets
# For production: integrate with Vault via External Secrets Operator

output "note" {
  value = "Secrets are managed via Kubernetes Sealed Secrets (dev) or HashiCorp Vault (prod). See docs/architecture/secrets.md for configuration."
}
