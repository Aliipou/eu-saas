variable "environment" {
  type = string
}

# Observability storage volumes

resource "hcloud_volume" "prometheus_data" {
  name     = "mt-prometheus-${var.environment}"
  size     = 20  # GB — 15 days retention
  location = "fsn1"
  format   = "ext4"

  labels = {
    environment = var.environment
    purpose     = "prometheus"
    managed-by  = "terraform"
  }
}

resource "hcloud_volume" "loki_data" {
  name     = "mt-loki-${var.environment}"
  size     = 20  # GB — log storage
  location = "fsn1"
  format   = "ext4"

  labels = {
    environment = var.environment
    purpose     = "loki"
    managed-by  = "terraform"
  }
}

output "prometheus_volume_id" {
  value = hcloud_volume.prometheus_data.id
}

output "loki_volume_id" {
  value = hcloud_volume.loki_data.id
}
