variable "environment" {
  type = string
}

variable "network_id" {
  type = number
}

# For production, use Hetzner managed database or dedicated PostgreSQL server
# For development/staging, PostgreSQL runs inside the k3s cluster

resource "hcloud_volume" "db_data" {
  name      = "mt-db-data-${var.environment}"
  size      = 50  # GB
  location  = "fsn1"
  format    = "ext4"

  labels = {
    environment = var.environment
    purpose     = "database"
    managed-by  = "terraform"
  }
}

resource "hcloud_volume" "db_backup" {
  name      = "mt-db-backup-${var.environment}"
  size      = 50  # GB
  location  = "fsn1"
  format    = "ext4"

  labels = {
    environment = var.environment
    purpose     = "database-backup"
    managed-by  = "terraform"
  }
}

output "host" {
  value = "postgres.mt-platform.svc.cluster.local"
}

output "data_volume_id" {
  value = hcloud_volume.db_data.id
}

output "backup_volume_id" {
  value = hcloud_volume.db_backup.id
}
